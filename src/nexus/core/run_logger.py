"""
run_logger.py — SQLite-Backed Run Snapshot Logger & Live Telemetry Subscriber.

Persists complete agent execution telemetry (`runs`, `trace_events`, `run_blob_refs`) into
`logs/chats.db` without writing duplicate loose `.json` files on every turn.
Also provides CLI maintenance commands for one-time legacy migration, reference-counted GC,
on-demand JSON snapshot export, and optional user-confirmed legacy file cleanup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Optional
import uuid

from nexus.core.chats_db import (
    PROJECT_ROOT,
    append_trace_event_record,
    finalize_run_record,
    gc_unreferenced_telemetry,
    get_latest_run_record,
    get_run_record,
    get_trace_blobs_batch,
    list_run_records,
    migrate_legacy_telemetry_if_needed,
)
from nexus.core.cost import calculate_cache_savings, calculate_token_cost
from nexus.core.trace import trace_bus

# Legacy runs directory retained strictly for `--migrate-legacy` and `--purge-legacy-files`
RUNS_DIR = PROJECT_ROOT / "logs" / "runs"


# ── Live Incremental SQLite Subscriber ───────────────────────────────────────

def _live_trace_subscriber(event: dict[str, Any]) -> None:
    """Persist any emitted trace event carrying `run_id` directly into `trace_events` in real time."""
    run_id = event.get("run_id") if isinstance(event, dict) else None
    if not run_id or not isinstance(run_id, str):
        return
    try:
        append_trace_event_record(run_id, event)
    except Exception:
        # Never allow a telemetry write issue to interrupt live agent execution or SSE streaming
        pass


# Register once at module import so every active run streams steps to SQLite immediately
_live_unsub = trace_bus.subscribe(_live_trace_subscriber)


# ── Subagent Fleet Aggregation Helper ────────────────────────────────────────

def build_subagent_summaries_from_events(
    events_list: list[dict[str, Any]],
    parent_metadata: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate isolated subagent breakdowns and token/cost totals from an ordered `trace_events` list."""
    subagents_map: dict[str, dict[str, Any]] = {}
    total_in_tokens = 0
    total_out_tokens = 0
    total_cached_tokens = 0
    total_reasoning_tokens = 0

    for evt in events_list:
        evt_type = evt.get("type")
        evt_agent_id = evt.get("agent_id") or evt.get("agent", "")
        evt_data = evt.get("data") or {}

        in_tok = 0
        out_tok = 0
        cached_tok = 0
        reasoning_tok = 0
        if evt_type == "info" and isinstance(evt_data, dict) and ("input_tokens" in evt_data or "output_tokens" in evt_data):
            in_tok = int(evt_data.get("input_tokens", 0) or 0)
            out_tok = int(evt_data.get("output_tokens", 0) or 0)
            cached_tok = int(evt_data.get("cached_tokens", 0) or 0)
            reasoning_tok = int(evt_data.get("reasoning_tokens", 0) or 0)
            total_in_tokens += in_tok
            total_out_tokens += out_tok
            total_cached_tokens += cached_tok
            total_reasoning_tokens += reasoning_tok

        is_sub = str(evt_agent_id).startswith("subagent") or str(evt.get("agent", "")).lower().startswith("subagent")
        if is_sub:
            sub_key = str(evt_agent_id) if str(evt_agent_id).startswith("subagent-") else str(evt.get("agent", "subagent"))
            if sub_key not in subagents_map:
                subagents_map[sub_key] = {
                    "agent_id": sub_key,
                    "agent_name": evt.get("agent", sub_key),
                    "parent_id": evt.get("parent_id", "nexus"),
                    "color": evt.get("color", "magenta"),
                    "model_tier": evt_data.get("model_tier", "low") if isinstance(evt_data, dict) else "low",
                    "model_name": evt_data.get("model_name") if isinstance(evt_data, dict) else None,
                    "task_prompt": evt_data.get("task_prompt") or evt_data.get("context") or evt.get("message", ""),
                    "started_at": evt.get("timestamp"),
                    "ended_at": None,
                    "final_response": None,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "cost_usd": 0.0,
                    "tool_calls": [],
                    "steps": [],
                }
            sub_entry = subagents_map[sub_key]
            sub_entry["steps"].append(evt)
            if in_tok or out_tok:
                sub_entry["input_tokens"] += in_tok
                sub_entry["output_tokens"] += out_tok
                sub_entry["cached_tokens"] += cached_tok
            if evt_type == "agent_start" and isinstance(evt_data, dict):
                if evt_data.get("task_prompt"):
                    sub_entry["task_prompt"] = evt_data["task_prompt"]
                if evt_data.get("model_tier"):
                    sub_entry["model_tier"] = evt_data["model_tier"]
                if evt_data.get("model_name"):
                    sub_entry["model_name"] = evt_data["model_name"]
            elif evt_type == "tool_call" and isinstance(evt_data, dict):
                sub_entry["tool_calls"].append({
                    "call_id": evt_data.get("call_id"),
                    "tool": evt_data.get("tool"),
                    "args": evt_data.get("args", {}),
                    "timestamp": evt.get("timestamp"),
                })
            elif evt_type == "tool_result" and isinstance(evt_data, dict):
                c_id = evt_data.get("call_id")
                t_name = evt_data.get("tool")
                matched = False
                for tc_item in reversed(sub_entry["tool_calls"]):
                    if (c_id and tc_item.get("call_id") == c_id) or (not c_id and tc_item.get("tool") == t_name and "result" not in tc_item):
                        tc_item["result"] = evt_data.get("result")
                        matched = True
                        break
                if not matched:
                    sub_entry["tool_calls"].append({
                        "call_id": c_id,
                        "tool": t_name,
                        "result": evt_data.get("result"),
                        "timestamp": evt.get("timestamp"),
                    })
            elif evt_type == "llm_response":
                resp_str = evt_data.get("response") if isinstance(evt_data, dict) else None
                sub_entry["final_response"] = resp_str or evt.get("message")
            elif evt_type == "agent_end":
                sub_entry["ended_at"] = evt.get("timestamp")

    meta = dict(parent_metadata or {})
    for sub in subagents_map.values():
        sub["cost_usd"] = calculate_token_cost(
            input_tokens=sub.get("input_tokens", 0),
            output_tokens=sub.get("output_tokens", 0),
            cached_tokens=sub.get("cached_tokens", 0),
            model_name=sub.get("model_name"),
            tier=sub.get("model_tier", "low"),
        )

    sub_in = sum(s.get("input_tokens", 0) for s in subagents_map.values())
    sub_out = sum(s.get("output_tokens", 0) for s in subagents_map.values())
    sub_cached = sum(s.get("cached_tokens", 0) for s in subagents_map.values())

    root_in = max(0, total_in_tokens - sub_in)
    root_out = max(0, total_out_tokens - sub_out)
    root_cached = max(0, total_cached_tokens - sub_cached)

    root_cost = calculate_token_cost(
        input_tokens=root_in,
        output_tokens=root_out,
        cached_tokens=root_cached,
        model_name=meta.get("model_name"),
        tier=meta.get("model_tier"),
    )
    total_run_cost = round(root_cost + sum(s.get("cost_usd", 0.0) for s in subagents_map.values()), 6)
    total_cache_savings = round(
        calculate_cache_savings(
            root_in,
            root_cached,
            model_name=meta.get("model_name"),
            tier=meta.get("model_tier"),
        )
        + sum(
            calculate_cache_savings(
                s.get("input_tokens", 0),
                s.get("cached_tokens", 0),
                model_name=s.get("model_name"),
                tier=s.get("model_tier", "low"),
            )
            for s in subagents_map.values()
        ),
        6,
    )

    stats = {
        "input_tokens": total_in_tokens,
        "output_tokens": total_out_tokens,
        "cached_tokens": total_cached_tokens,
        "reasoning_tokens": total_reasoning_tokens,
        "cost_usd": total_run_cost,
        "cache_savings_usd": total_cache_savings,
    }
    return list(subagents_map.values()), stats


# ── Public Run Logger API (SQLite-Backed) ────────────────────────────────────

def log_run(
    agent_name: str,
    query: str,
    response: str,
    thread_id: Optional[str] = None,
    domain: Optional[str] = None,
    confidence: Optional[float] = None,
    reasoning: Optional[str] = None,
    dpfh_injected_files: Optional[list[str]] = None,
    tool_calls: Optional[list[dict[str, Any]]] = None,
    trace_events: Optional[list[dict[str, Any]]] = None,
    latency_seconds: Optional[float] = None,
    metadata: Optional[dict[str, Any]] = None,
    run_id: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    """
    Finalize and persist an agent execution run snapshot directly into SQLite `chats.db` (`runs` + `trace_events`).

    Returns:
      The unique `run_id` string stored in `runs`.
    """
    effective_run_id = run_id or str(uuid.uuid4())[:8]
    now_iso = datetime.now(timezone.utc).isoformat()
    events_list = trace_events or []
    merged_metadata = dict(metadata or {})

    subagents_list, stats = build_subagent_summaries_from_events(events_list, merged_metadata)
    total_in_tokens = stats["input_tokens"]
    total_out_tokens = stats["output_tokens"]
    total_cached_tokens = stats["cached_tokens"]
    total_reasoning_tokens = stats["reasoning_tokens"]
    total_run_cost = stats["cost_usd"]
    total_cache_savings = stats["cache_savings_usd"]

    if total_in_tokens or total_out_tokens:
        token_usage_summary: dict[str, Any] = {
            "input_tokens": total_in_tokens,
            "output_tokens": total_out_tokens,
            "cached_tokens": total_cached_tokens,
            "total_tokens": total_in_tokens + total_out_tokens,
            "cost_usd": total_run_cost,
            "cache_savings_usd": total_cache_savings,
        }
        if total_reasoning_tokens > 0:
            token_usage_summary["reasoning_tokens"] = total_reasoning_tokens
        merged_metadata["token_usage"] = token_usage_summary

    effective_source = source or str(
        merged_metadata.get("source")
        or ("telegram" if str(agent_name).lower() == "telegram" else "chat")
    )
    status = "error" if merged_metadata.get("error") else "done"

    finalize_run_record(
        run_id=effective_run_id,
        timestamp=now_iso,
        ended_at=now_iso,
        status=status,
        source=effective_source,
        thread_id=thread_id or "unspecified",
        agent_name=agent_name,
        domain=domain,
        confidence=confidence,
        reasoning=reasoning,
        input_query=query,
        output_response=response,
        model_tier=merged_metadata.get("model_tier"),
        model_name=merged_metadata.get("model_name"),
        input_tokens=total_in_tokens,
        output_tokens=total_out_tokens,
        cached_tokens=total_cached_tokens,
        reasoning_tokens=total_reasoning_tokens,
        cost_usd=total_run_cost,
        cache_savings_usd=total_cache_savings,
        latency_seconds=latency_seconds,
        dpfh_injected_files=dpfh_injected_files or [],
        tool_calls=tool_calls or [],
        subagents_count=len(subagents_list),
        trace_events=events_list,
        metadata=merged_metadata,
    )
    return effective_run_id


def list_runs(limit: int = 50, agent: Optional[str] = None) -> list[dict[str, Any]]:
    """Lists recent run summaries ordered from newest to oldest from SQLite `runs`."""
    return list_run_records(limit=limit, agent=agent)


def _enrich_snapshot_with_subagents(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach dynamically reconstructed `subagents` list and ensure `cost_usd` is populated."""
    events = snapshot.get("trace_events") or []
    meta = snapshot.get("metadata") or {}
    subagents_list, stats = build_subagent_summaries_from_events(events, meta)
    snapshot["subagents"] = subagents_list
    snapshot["subagents_count"] = len(subagents_list)
    if snapshot.get("cost_usd") is None:
        tok = meta.get("token_usage") or {}
        if tok.get("cost_usd") is not None:
            snapshot["cost_usd"] = tok.get("cost_usd")
        elif stats["input_tokens"] or stats["output_tokens"]:
            snapshot["cost_usd"] = stats["cost_usd"]
    return snapshot


def get_run(run_id: str) -> Optional[dict[str, Any]]:
    """
    Retrieves full run snapshot dictionary from SQLite `runs` + `trace_events` by `run_id`.

    Raises:
      ValueError: If `run_id` contains path separators ('/' or '\\') or '..'
    """
    if not run_id or not isinstance(run_id, str):
        return None
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise ValueError(f"Invalid run_id '{run_id}': cannot contain path separators or '..'")

    rec = get_run_record(run_id)
    if rec is None:
        return None
    return _enrich_snapshot_with_subagents(rec)


def get_latest_run() -> Optional[dict[str, Any]]:
    """Retrieves the most recent run snapshot from SQLite `runs`."""
    rec = get_latest_run_record()
    if rec is None:
        return None
    return _enrich_snapshot_with_subagents(rec)


def export_run_snapshot(run_id: str, hydrate_blobs: bool = False) -> Optional[dict[str, Any]]:
    """Export a run snapshot dict, optionally hydrating referenced SHA-256 `trace_blobs` inline."""
    snap = get_run(run_id)
    if snap is None:
        return None
    if not hydrate_blobs:
        return snap

    hashes: list[str] = []
    for evt in snap.get("trace_events") or []:
        data = evt.get("data") if isinstance(evt.get("data"), dict) else {}
        manifest = data.get("context_manifest")
        if isinstance(manifest, list):
            for item in manifest:
                if isinstance(item, dict) and isinstance(item.get("hash"), str):
                    hashes.append(item["hash"])

    if hashes:
        blobs = get_trace_blobs_batch(hashes)
        for evt in snap.get("trace_events") or []:
            data = evt.get("data") if isinstance(evt.get("data"), dict) else {}
            manifest = data.get("context_manifest")
            if isinstance(manifest, list):
                for item in manifest:
                    if isinstance(item, dict) and isinstance(item.get("hash"), str):
                        blob = blobs.get(item["hash"])
                        if blob is not None:
                            item["content"] = blob["content"]
    return snap


# ── Maintenance CLI ──────────────────────────────────────────────────────────

def _purge_legacy_files(dry_run: bool = False) -> dict[str, Any]:
    """Delete legacy `logs/runs/*.json` and `src/nexus/agent/memory.sqlite*` files after migration."""
    removed_json = 0
    removed_mem = 0
    if RUNS_DIR.is_dir():
        for jf in RUNS_DIR.glob("*.json"):
            if dry_run:
                removed_json += 1
            else:
                jf.unlink()
                removed_json += 1

    mem_base = PROJECT_ROOT / "src" / "nexus" / "agent" / "memory.sqlite"
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{mem_base}{suffix}")
        if p.is_file():
            if dry_run:
                removed_mem += 1
            else:
                p.unlink()
                removed_mem += 1
    return {"removed_json_files": removed_json, "removed_memory_sqlite_files": removed_mem}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Nexus unified SQLite run logger & telemetry maintenance CLI.")
    parser.add_argument("--migrate-legacy", action="store_true", help="Import active memory.sqlite threads and logs/runs/*.json into chats.db.")
    parser.add_argument("--gc", action="store_true", help="Sweep unreferenced trace_blobs and orphaned upload files.")
    parser.add_argument("--dry-run", action="store_true", help="Preview GC or purge counts without deleting.")
    parser.add_argument("--export", type=str, default=None, help="Export a run_id to JSON.")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output file path for --export (defaults to stdout).")
    parser.add_argument("--hydrate-blobs", action="store_true", help="Inline trace_blobs content when exporting a run.")
    parser.add_argument("--purge-legacy-files", action="store_true", help="Delete legacy logs/runs/*.json and memory.sqlite* files.")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive --purge-legacy-files operation.")
    args = parser.parse_args()

    if args.migrate_legacy:
        res = migrate_legacy_telemetry_if_needed(force=True)
        print(json.dumps({"migration": res}, indent=2))

    if args.gc:
        res = gc_unreferenced_telemetry(dry_run=args.dry_run)
        print(json.dumps({"gc": res, "dry_run": args.dry_run}, indent=2))

    if args.export:
        snap = export_run_snapshot(args.export, hydrate_blobs=args.hydrate_blobs)
        if snap is None:
            print(f"❌ Run '{args.export}' not found.", file=sys.stderr)
            sys.exit(1)
        rendered = json.dumps(snap, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
            print(f"✅ Exported run '{args.export}' to {args.output}")
        else:
            print(rendered)

    if args.purge_legacy_files:
        if not args.yes and not args.dry_run:
            print("❌ Refusing to purge legacy files without --yes (pass --dry-run to preview).", file=sys.stderr)
            sys.exit(2)
        res = _purge_legacy_files(dry_run=args.dry_run)
        print(json.dumps({"purge": res, "dry_run": args.dry_run}, indent=2))


if __name__ == "__main__":
    main()
