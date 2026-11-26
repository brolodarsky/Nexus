"""
audit_agent_health.py — Deterministic Subagent Health, Cache Integrity & Budget Telemetry Auditor.

Queries persisted execution runs in SQLite `chats.db` (`runs` + `trace_events`) to evaluate subagent
efficiency without requiring any LLM judge calls:
  1. Soft-warning and hard-cap breaker trigger rates (both structured `event_kind` & legacy logs).
  2. Prompt-cache integrity on normal turns vs. budget-capped synthesis turns + normalized cost share.
  3. Runaway signals (duplicate tool calls, error bursts, 429s, timeouts) vs. truncation signals
     (incomplete responses, write-intent with zero staged writes, post-cap Head Agent rework).
  4. Uncapped/cohort percentile distributions (turns, peak context, cumulative uncached/total input, cost).

Usage:
    .venv\\Scripts\\python.exe scripts\\audit_agent_health.py
    .venv\\Scripts\\python.exe scripts\\audit_agent_health.py --days 7
    .venv\\Scripts\\python.exe scripts\\audit_agent_health.py --compare-since 2026-11-19T01:15
    .venv\\Scripts\\python.exe scripts\\audit_agent_health.py --json
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Add `src/` to sys.path so `nexus.core.cost` imports cleanly whether executed directly or as a module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import nexus.core.chats_db as chats_db
from nexus.core.cost import calculate_token_cost

# Regex patterns used for classifying behavioral intent and truncation signals deterministically
_WRITE_INTENT_RE = re.compile(
    r"(modify_file|create_file|move_file|delete_file|stage|update|write|edit|sync|patch|spawn_conversation)",
    re.IGNORECASE,
)
_WRITE_TOOLS = frozenset({"modify_file", "create_file", "move_file", "delete_file", "spawn_conversation"})
_INCOMPLETE_KW_RE = re.compile(
    r"(budget|limit|cut off|incomplete|remaining|not yet|could not|unable to|didn't get to|"
    r"still need|pending|did not finish|only completed|partially|stopped before|was unable)",
    re.IGNORECASE,
)


# `raw_ts: str` is an ISO date (`YYYY-MM-DD`) or datetime (`YYYY-MM-DDTHH:MM[:SS][Z]`).
# `-> datetime` returns a timezone-aware UTC `datetime` for comparing against snapshot timestamps.
def _parse_cutoff_dt(raw_ts: str) -> datetime:
    """Parse CLI `--since` / `--compare-since` strings into UTC-aware `datetime` objects."""
    cleaned = raw_ts.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# `values: List[float | int]` is a list of numeric observations for one metric.
# `-> Dict[str, float]` returns p50, p75, p90, p95, p99, and max using nearest-rank indexing.
def _compute_percentiles(values: List[float]) -> Dict[str, float]:
    """Compute p50/p75/p90/p95/p99/max summary percentiles over a non-empty numeric series."""
    if not values:
        return {"p50": 0.0, "p75": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    ordered = sorted(values)
    n = len(ordered)
    out: Dict[str, float] = {}
    for pct in (50, 75, 90, 95, 99, 100):
        idx = min(n - 1, int(n * pct / 100)) if pct < 100 else n - 1
        key = "max" if pct == 100 else f"p{pct}"
        out[key] = float(ordered[idx])
    return out


# `ev: Dict[str, Any]` is a single trace event dict inside `trace_events`.
# `-> Tuple[Optional[str], Optional[str]]` returns `(cap_kind, reason)` if `ev` marks a hard budget cap.
def _classify_hard_cap_event(ev: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Detect both structured (`event_kind`) and legacy string hard-cap events."""
    d = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    kind = d.get("event_kind")
    if kind == "subagent_budget_cap":
        reason = str(d.get("reason") or "unknown")
        norm_reason = "turn_limit" if "turn" in reason else "token_budget"
        return "hard_cap", norm_reason

    msg = str(ev.get("message") or "")
    if "input token budget" in msg:
        return "hard_cap", "token_budget"
    if "turn limit" in msg:
        return "hard_cap", "turn_limit"
    return None, None


# `events: List[Dict[str, Any]]`, `doc: Dict[str, Any]`, `filename: str`, `run_dt: Optional[datetime]`
# `-> List[Dict[str, Any]]` extracts one normalized telemetry record per `subagent-*` worker in the run.
def _extract_subagent_records(
    filename: str,
    run_dt: Optional[datetime],
    doc: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Reconstruct per-turn usage, cache integrity, truncation, and parent-rework signals for each subagent."""
    events: List[Dict[str, Any]] = doc.get("trace_events") or []
    sub_summaries = {
        s.get("agent_id"): s for s in (doc.get("subagents") or []) if isinstance(s, dict) and s.get("agent_id")
    }

    by_agent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for ev in events:
        aid = str(ev.get("agent_id") or "")
        if aid.startswith("subagent-"):
            by_agent[aid].append(ev)

    if not by_agent:
        return []

    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    parent_model = str(meta.get("model_name") or "unknown")
    parent_tier = str(meta.get("model_tier") or "unknown")

    records: List[Dict[str, Any]] = []
    for aid, evs in by_agent.items():
        sub_meta = sub_summaries.get(aid, {})
        start_ev = next((e for e in evs if e.get("type") == "agent_start"), None)
        start_data = (start_ev.get("data") or {}) if isinstance(start_ev, dict) else {}

        model_name = str(sub_meta.get("model_name") or start_data.get("model_name") or "unknown")
        tier = str(sub_meta.get("model_tier") or start_data.get("model_tier") or "low")
        prompt = str(sub_meta.get("task_prompt") or start_data.get("task_prompt") or "")
        final_resp = str(sub_meta.get("final_response") or "")

        # Fallback if `subagents[]` did not store `final_response`
        if not final_resp:
            resp_ev = next((e for e in reversed(evs) if e.get("type") == "llm_response"), None)
            if resp_ev:
                r_data = resp_ev.get("data") if isinstance(resp_ev.get("data"), dict) else {}
                final_resp = str(r_data.get("response") or resp_ev.get("message") or "")

        normal_turns: List[Tuple[int, int, int, float]] = []
        synth_turns: List[Tuple[int, int, int, float]] = []
        tool_seq: List[str] = []
        tc_sigs: List[Tuple[str, str]] = []
        tool_errors = 0
        soft_warned = False
        hard_cap_reason: Optional[str] = None
        cache_preserved_synth: Optional[bool] = None
        used_unbound_fallback = False
        after_cap = False
        had_429 = False
        had_timeout = False

        for ev in evs:
            et = ev.get("type")
            msg = str(ev.get("message") or "")
            d = ev.get("data") if isinstance(ev.get("data"), dict) else {}

            if et == "info":
                if "429 RESOURCE_EXHAUSTED" in msg or "Rate limit reached" in msg:
                    had_429 = True

                event_kind = d.get("event_kind")
                if event_kind == "subagent_soft_warning":
                    soft_warned = True
                elif event_kind == "subagent_budget_cap_fallback":
                    used_unbound_fallback = True
                    cache_preserved_synth = False

                cap_kind, cap_reason = _classify_hard_cap_event(ev)
                if cap_kind == "hard_cap":
                    hard_cap_reason = cap_reason
                    after_cap = True
                    if "cache_preserved_synthesis" in d:
                        cache_preserved_synth = bool(d.get("cache_preserved_synthesis"))
                    elif cache_preserved_synth is None:
                        # Legacy hard-cap events always used unbound plain-text synthesis (0% cache)
                        cache_preserved_synth = False
                    continue

                if "input_tokens" in d or "output_tokens" in d:
                    t_in = int(d.get("input_tokens") or 0)
                    t_cached = int(d.get("cached_tokens") or 0)
                    t_out = int(d.get("output_tokens") or 0)
                    # Normalize cost to current `nexus.core.cost` catalog so historical pricing shifts don't skew audits
                    norm_cost = calculate_token_cost(
                        input_tokens=t_in,
                        output_tokens=t_out,
                        cached_tokens=t_cached,
                        model_name=model_name,
                        tier=tier,
                    )
                    if after_cap:
                        synth_turns.append((t_in, t_cached, t_out, norm_cost))
                    else:
                        normal_turns.append((t_in, t_cached, t_out, norm_cost))

            elif et == "tool_call":
                tname = str(d.get("tool") or d.get("name") or msg)
                targs = d.get("args") or {}
                tool_seq.append(tname)
                try:
                    sig_args = json.dumps(targs, sort_keys=True)[:120]
                except Exception:
                    sig_args = str(targs)[:120]
                tc_sigs.append((tname, sig_args))

            elif et == "tool_error":
                tool_errors += 1
                if "exceeded wall-clock budget" in msg or "timed out" in msg.lower():
                    had_timeout = True

            elif et == "agent_end":
                if "exceeded wall-clock budget" in msg or "timed out" in msg.lower():
                    had_timeout = True

        # Combine normal + synthesis turns for aggregate context/cost totals
        all_turns = normal_turns + synth_turns
        pre_in = sum(t[0] for t in normal_turns)
        pre_cached = sum(t[1] for t in normal_turns)
        pre_cost = sum(t[3] for t in normal_turns)

        synth_in = sum(t[0] for t in synth_turns)
        synth_cached = sum(t[1] for t in synth_turns)
        synth_cost = sum(t[3] for t in synth_turns)

        total_in = pre_in + synth_in
        total_cached = pre_cached + synth_cached
        total_uncached = sum(max(0, t[0] - t[1]) for t in all_turns)
        peak_ctx = max((t[0] for t in all_turns), default=0)

        dup_calls = len(tc_sigs) - len(set(tc_sigs))
        wants_write = bool(_WRITE_INTENT_RE.search(prompt))
        writes_done = sum(1 for t in tool_seq if t in _WRITE_TOOLS)
        incomplete_resp = bool(_INCOMPLETE_KW_RE.search(final_resp))

        # Inspect Head Agent (`agent_id == "nexus"`) tool calls emitted AFTER this subagent's `agent_end`
        end_idx = next(
            (i for i, e in enumerate(events) if e.get("agent_id") == aid and e.get("type") == "agent_end"),
            len(events),
        )
        parent_after_tools = [
            str((e.get("data") or {}).get("tool") or (e.get("data") or {}).get("name") or "")
            for e in events[end_idx:]
            if e.get("agent_id") == "nexus" and e.get("type") == "tool_call"
        ]
        parent_respawned = any(t == "spawn_subagent" for t in parent_after_tools)
        parent_wrote = any(t in _WRITE_TOOLS for t in parent_after_tools)

        records.append({
            "filename": filename,
            "timestamp": run_dt.isoformat() if run_dt else None,
            "agent_id": aid,
            "model_name": model_name,
            "model_tier": tier,
            "parent_model": f"{parent_model} ({parent_tier})",
            "n_turns": len(normal_turns),
            "peak_context_tokens": peak_ctx,
            "cum_input_tokens": total_in,
            "cum_cached_tokens": total_cached,
            "cum_uncached_tokens": total_uncached,
            "pre_input_tokens": pre_in,
            "pre_cached_tokens": pre_cached,
            "pre_cost_usd": round(pre_cost, 6),
            "synth_input_tokens": synth_in,
            "synth_cached_tokens": synth_cached,
            "synth_cost_usd": round(synth_cost, 6),
            "total_cost_usd": round(pre_cost + synth_cost, 6),
            "soft_warned": soft_warned,
            "hard_cap_reason": hard_cap_reason,
            "cache_preserved_synth": cache_preserved_synth,
            "used_unbound_fallback": used_unbound_fallback,
            "had_429": had_429,
            "had_timeout": had_timeout,
            "dup_tool_calls": dup_calls,
            "tool_errors": tool_errors,
            "wants_write": wants_write,
            "writes_done": writes_done,
            "incomplete_response": incomplete_resp,
            "parent_followup_tools": len(parent_after_tools) > 0,
            "parent_respawned": parent_respawned,
            "parent_wrote": parent_wrote,
        })

    return records


# `records: List[Dict[str, Any]]` is a list of subagent records for one cohort (e.g., `all`, `pre`, or `post`).
# `-> Dict[str, Any]` returns aggregated counts, rates, cache integrity metrics, percentiles, and health alerts.
def _summarize_cohort(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all scorecard metrics, distributions, and automated health alerts for a subagent cohort."""
    n = len(records)
    if n == 0:
        return {
            "subagents_count": 0,
            "alerts": [],
        }

    soft_warned = sum(1 for r in records if r["soft_warned"])
    hard_caps = [r for r in records if r["hard_cap_reason"] is not None]
    turn_caps = sum(1 for r in hard_caps if r["hard_cap_reason"] == "turn_limit")
    token_caps = sum(1 for r in hard_caps if r["hard_cap_reason"] == "token_budget")
    hard_cap_rate = len(hard_caps) / n * 100.0

    r429 = sum(1 for r in records if r["had_429"])
    timeouts = sum(1 for r in records if r["had_timeout"])
    dup_loops = sum(1 for r in records if r["dup_tool_calls"] >= 2)
    error_bursts = sum(1 for r in records if r["tool_errors"] >= 2)

    # Normal-turn cache hit rate across all subagents
    all_pre_in = sum(r["pre_input_tokens"] for r in records)
    all_pre_cached = sum(r["pre_cached_tokens"] for r in records)
    overall_normal_cache_pct = (all_pre_cached / all_pre_in * 100.0) if all_pre_in > 0 else 0.0

    # Cache integrity & synthesis economics on hard-capped subagents
    cap_pre_in = sum(r["pre_input_tokens"] for r in hard_caps)
    cap_pre_cached = sum(r["pre_cached_tokens"] for r in hard_caps)
    cap_pre_cache_pct = (cap_pre_cached / cap_pre_in * 100.0) if cap_pre_in > 0 else 0.0

    cap_synth_in = sum(r["synth_input_tokens"] for r in hard_caps)
    cap_synth_cached = sum(r["synth_cached_tokens"] for r in hard_caps)
    cap_synth_cache_pct = (cap_synth_cached / cap_synth_in * 100.0) if cap_synth_in > 0 else 0.0

    cap_pre_cost = sum(r["pre_cost_usd"] for r in hard_caps)
    cap_synth_cost = sum(r["synth_cost_usd"] for r in hard_caps)
    cap_synth_cost_share_pct = (
        (cap_synth_cost / (cap_pre_cost + cap_synth_cost) * 100.0) if (cap_pre_cost + cap_synth_cost) > 0 else 0.0
    )

    cap_preserved_cnt = sum(1 for r in hard_caps if r["cache_preserved_synth"] is True)
    cap_fallback_cnt = sum(1 for r in hard_caps if r["cache_preserved_synth"] is False)

    # Truncation & downstream rework metrics across hard-capped subagents
    cap_incomp = sum(1 for r in hard_caps if r["incomplete_response"])
    cap_write_wanted = [r for r in hard_caps if r["wants_write"]]
    cap_write_zero = sum(1 for r in cap_write_wanted if r["writes_done"] == 0)
    cap_parent_followup = sum(1 for r in hard_caps if r["parent_followup_tools"])
    cap_parent_respawn = sum(1 for r in hard_caps if r["parent_respawned"])
    cap_parent_wrote = sum(1 for r in hard_caps if r["parent_wrote"])

    # Breakdown by subagent model
    by_model_raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_model_raw[r["model_name"]].append(r)

    by_model: Dict[str, Dict[str, Any]] = {}
    for m_name, m_list in sorted(by_model_raw.items(), key=lambda kv: -len(kv[1])):
        m_n = len(m_list)
        by_model[m_name] = {
            "count": m_n,
            "hard_caps": sum(1 for r in m_list if r["hard_cap_reason"] is not None),
            "turn_caps": sum(1 for r in m_list if r["hard_cap_reason"] == "turn_limit"),
            "token_caps": sum(1 for r in m_list if r["hard_cap_reason"] == "token_budget"),
            "avg_turns": round(sum(r["n_turns"] for r in m_list) / m_n, 2),
            "avg_cum_input": round(sum(r["cum_input_tokens"] for r in m_list) / m_n, 1),
            "avg_uncached": round(sum(r["cum_uncached_tokens"] for r in m_list) / m_n, 1),
            "avg_cost_usd": round(sum(r["total_cost_usd"] for r in m_list) / m_n, 6),
        }

    parent_models_on_cap = dict(Counter(r["parent_model"] for r in hard_caps))

    # Automated health alert evaluation
    alerts: List[str] = []
    if hard_cap_rate > 5.0:
        alerts.append(
            f"HIGH HARD-CAP RATE: {len(hard_caps)}/{n} ({hard_cap_rate:.1f}%) subagents hit hard budget caps (> 5.0% threshold)."
        )
    if hard_caps and cap_synth_in > 0 and cap_synth_cache_pct < 50.0:
        alerts.append(
            f"SYNTHESIS CACHE CLIFF: Hard-cap synthesis turns averaged {cap_synth_cache_pct:.1f}% KV cache hits (< 50.0% threshold)."
        )
    if all_pre_in > 0 and overall_normal_cache_pct < 75.0:
        alerts.append(
            f"LOW NORMAL CACHE HIT RATE: {overall_normal_cache_pct:.1f}% across normal turns (< 75.0% threshold)."
        )
    if r429 > 0:
        alerts.append(f"RATE LIMITS DETECTED: {r429} subagent(s) encountered 429 RESOURCE_EXHAUSTED.")

    return {
        "subagents_count": n,
        "soft_warnings": soft_warned,
        "soft_warning_pct": round(soft_warned / n * 100.0, 2),
        "hard_caps_total": len(hard_caps),
        "hard_cap_pct": round(hard_cap_rate, 2),
        "turn_caps": turn_caps,
        "turn_cap_pct": round(turn_caps / n * 100.0, 2),
        "token_caps": token_caps,
        "token_cap_pct": round(token_caps / n * 100.0, 2),
        "rate_limits_429": r429,
        "timeouts": timeouts,
        "dup_tool_loops_ge2": dup_loops,
        "tool_error_bursts_ge2": error_bursts,
        "avg_turns": round(sum(r["n_turns"] for r in records) / n, 2),
        "avg_cum_input_tokens": round(sum(r["cum_input_tokens"] for r in records) / n, 1),
        "avg_cum_uncached_tokens": round(sum(r["cum_uncached_tokens"] for r in records) / n, 1),
        "avg_cost_usd": round(sum(r["total_cost_usd"] for r in records) / n, 6),
        "overall_normal_cache_pct": round(overall_normal_cache_pct, 2),
        "capped_analysis": {
            "count": len(hard_caps),
            "cache_preserved_count": cap_preserved_cnt,
            "unbound_fallback_count": cap_fallback_cnt,
            "pre_cap_cache_pct": round(cap_pre_cache_pct, 2),
            "synthesis_cache_pct": round(cap_synth_cache_pct, 2),
            "pre_cap_cost_usd": round(cap_pre_cost, 6),
            "synthesis_cost_usd": round(cap_synth_cost, 6),
            "synthesis_cost_share_pct": round(cap_synth_cost_share_pct, 2),
            "incomplete_response_count": cap_incomp,
            "write_wanted_count": len(cap_write_wanted),
            "write_zero_staged_count": cap_write_zero,
            "parent_followup_count": cap_parent_followup,
            "parent_respawn_count": cap_parent_respawn,
            "parent_direct_write_count": cap_parent_wrote,
            "parent_models": parent_models_on_cap,
        },
        "percentiles": {
            "turns": _compute_percentiles([float(r["n_turns"]) for r in records]),
            "peak_context_tokens": _compute_percentiles([float(r["peak_context_tokens"]) for r in records]),
            "cum_uncached_tokens": _compute_percentiles([float(r["cum_uncached_tokens"]) for r in records]),
            "cum_input_tokens": _compute_percentiles([float(r["cum_input_tokens"]) for r in records]),
            "cost_usd": _compute_percentiles([float(r["total_cost_usd"]) for r in records]),
        },
        "by_model": by_model,
        "alerts": alerts,
    }


def _audit_sqlite_runs(
    since_dt: Optional[datetime],
    compare_dt: Optional[datetime],
    db_path: Optional[Path] = None,
) -> tuple[int, int, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Query indexed `runs` and `trace_events` from SQLite `chats.db` without parsing loose JSON files."""
    prev_db = chats_db.DB_PATH
    if db_path is not None:
        chats_db.DB_PATH = db_path
    try:
        runs_scanned = 0
        runs_with_subagents = 0
        all_records: List[Dict[str, Any]] = []
        pre_records: List[Dict[str, Any]] = []
        post_records: List[Dict[str, Any]] = []

        with chats_db._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT run_id, timestamp, agent_name, metadata_json, subagents_count
                FROM runs
                ORDER BY timestamp ASC
                """
            ).fetchall()

            for row in rows:
                ts_str = row["timestamp"]
                run_dt = _parse_cutoff_dt(ts_str) if isinstance(ts_str, str) and ts_str.strip() else None
                if since_dt is not None and run_dt is not None and run_dt < since_dt:
                    continue

                runs_scanned += 1
                run_id = row["run_id"]
                sub_cnt = int(row["subagents_count"] or 0)
                if sub_cnt == 0:
                    has_sub_evt = conn.execute(
                        "SELECT 1 FROM trace_events WHERE run_id = ? AND event_json LIKE '%subagent-%' LIMIT 1",
                        (run_id,),
                    ).fetchone()
                    if not has_sub_evt:
                        continue

                evt_rows = conn.execute(
                    "SELECT event_json FROM trace_events WHERE run_id = ? ORDER BY seq ASC",
                    (run_id,),
                ).fetchall()
                trace_events = []
                for er in evt_rows:
                    try:
                        trace_events.append(json.loads(er["event_json"]))
                    except Exception:
                        continue

                meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                doc = {
                    "run_id": run_id,
                    "timestamp": ts_str,
                    "metadata": meta,
                    "trace_events": trace_events,
                }
                recs = _extract_subagent_records(f"{run_id}.sqlite", run_dt, doc)
                if not recs:
                    continue

                runs_with_subagents += 1
                all_records.extend(recs)
                if compare_dt is not None and run_dt is not None:
                    if run_dt >= compare_dt:
                        post_records.extend(recs)
                    else:
                        pre_records.extend(recs)

        return runs_scanned, runs_with_subagents, all_records, pre_records, post_records
    finally:
        chats_db.DB_PATH = prev_db


def audit_health(
    days: Optional[int] = None,
    since: Optional[str] = None,
    compare_since: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Query SQLite `runs` + `trace_events` in `chats.db` (or `--db-path`) for subagent health metrics."""
    since_dt: Optional[datetime] = None
    if since:
        since_dt = _parse_cutoff_dt(since)
    elif days is not None and days > 0:
        since_dt = datetime.now(timezone.utc) - timedelta(days=days)

    compare_dt: Optional[datetime] = _parse_cutoff_dt(compare_since) if compare_since else None

    target_db = db_path if db_path is not None else chats_db.DB_PATH
    if db_path is not None and not target_db.is_file():
        return {"error": f"SQLite database not found: {target_db}", "runs_scanned": 0}

    runs_scanned, runs_with_subagents, all_records, pre_records, post_records = _audit_sqlite_runs(
        since_dt, compare_dt, db_path=db_path
    )

    result: Dict[str, Any] = {
        "source": f"sqlite:{target_db}",
        "runs_scanned": runs_scanned,
        "runs_with_subagents": runs_with_subagents,
        "since": since_dt.isoformat() if since_dt else None,
        "compare_since": compare_dt.isoformat() if compare_dt else None,
        "overall": _summarize_cohort(all_records),
    }
    if compare_dt is not None:
        result["pre"] = _summarize_cohort(pre_records)
        result["post"] = _summarize_cohort(post_records)
    return result


def _print_cohort_report(label: str, summary: Dict[str, Any]) -> None:
    """Render a compact, readable terminal scorecard for a single cohort summary dict."""
    print(f"\n── {label} (subagents={summary.get('subagents_count', 0)}) " + "─" * 34)
    if summary.get("subagents_count", 0) == 0:
        print("  (No matching subagent runs in cohort)")
        return

    print(
        f"  Breakers:    soft={summary['soft_warnings']} ({summary['soft_warning_pct']:.1f}%) | "
        f"hard_total={summary['hard_caps_total']} ({summary['hard_cap_pct']:.1f}%) "
        f"[turn={summary['turn_caps']}, token={summary['token_caps']}]"
    )
    print(
        f"  Reliability: 429s={summary['rate_limits_429']} | timeouts={summary['timeouts']} | "
        f"dup_loops(>=2)={summary['dup_tool_loops_ge2']} | tool_errors(>=2)={summary['tool_error_bursts_ge2']}"
    )
    print(
        f"  Averages:    turns={summary['avg_turns']:.1f} | cum_in={summary['avg_cum_input_tokens']:,.0f} | "
        f"uncached={summary['avg_cum_uncached_tokens']:,.0f} | norm_cost=${summary['avg_cost_usd']:.4f} | "
        f"normal_cache={summary['overall_normal_cache_pct']:.1f}%"
    )

    cap = summary["capped_analysis"]
    if cap["count"] > 0:
        print(
            f"  Hard-Cap Synthesis ({cap['count']} runs): cache_preserved={cap['cache_preserved_count']} | "
            f"unbound_fallback={cap['unbound_fallback_count']} | "
            f"cache={cap['pre_cap_cache_pct']:.1f}% -> {cap['synthesis_cache_pct']:.1f}% | "
            f"synth_cost_share={cap['synthesis_cost_share_pct']:.1f}% "
            f"(${cap['synthesis_cost_usd']:.4f} / ${cap['pre_cap_cost_usd'] + cap['synthesis_cost_usd']:.4f})"
        )
        print(
            f"  Truncation & Rework: incomplete={cap['incomplete_response_count']}/{cap['count']} | "
            f"zero_writes={cap['write_zero_staged_count']}/{cap['write_wanted_count']} | "
            f"parent_followup={cap['parent_followup_count']}/{cap['count']} "
            f"(respawn={cap['parent_respawn_count']}, direct_write={cap['parent_direct_write_count']})"
        )

    pct = summary["percentiles"]
    print("  Percentiles (p50 / p75 / p90 / p95 / p99 / max):")
    for key, label_str in (
        ("turns", "Turns       "),
        ("peak_context_tokens", "Peak Ctx    "),
        ("cum_uncached_tokens", "Cum Uncached"),
        ("cum_input_tokens", "Cum Total In"),
    ):
        d = pct[key]
        print(
            f"    {label_str}: {d['p50']:,.0f} / {d['p75']:,.0f} / {d['p90']:,.0f} / "
            f"{d['p95']:,.0f} / {d['p99']:,.0f} / {d['max']:,.0f}"
        )

    if summary["by_model"]:
        print("  By Subagent Model:")
        for m_name, m_stats in summary["by_model"].items():
            print(
                f"    - {m_name:<20} n={m_stats['count']:3d} | caps={m_stats['hard_caps']:2d} "
                f"(T={m_stats['turn_caps']}, tok={m_stats['token_caps']}) | "
                f"avg_t={m_stats['avg_turns']:.1f} | avg_unc={m_stats['avg_uncached']:,.0f} | "
                f"avg=${m_stats['avg_cost_usd']:.4f}"
            )

    if summary["alerts"]:
        print("  Alerts:")
        for alert in summary["alerts"]:
            print(f"    ⚠️  {alert}")
    else:
        print("  Alerts: ✅ All automated health thresholds passed.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Audit Nexus subagent health, cache integrity, and budget caps.")
    parser.add_argument("--days", type=int, default=None, help="Only analyze runs from the last N days.")
    parser.add_argument("--since", type=str, default=None, help="ISO start date/time filter (e.g. 2026-11-18).")
    parser.add_argument(
        "--compare-since",
        type=str,
        default=None,
        help="Split subagents into PRE vs POST cohorts at this UTC ISO timestamp (e.g. 2026-11-19T01:15).",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output structured JSON instead of tables.")
    parser.add_argument("--db-path", type=Path, default=None, help="Optional SQLite DB path (defaults to logs/chats.db).")
    args = parser.parse_args()

    report = audit_health(
        days=args.days,
        since=args.since,
        compare_since=args.compare_since,
        db_path=args.db_path,
    )

    if args.as_json:
        print(json.dumps(report, indent=2))
        return

    if report.get("error"):
        print(f"❌ {report['error']}")
        sys.exit(1)

    print("\n" + "═" * 74)
    print(" 🩺 NEXUS SUBAGENT HEALTH & CACHE INTEGRITY AUDIT")
    print("═" * 74)
    print(f"  Runs scanned: {report['runs_scanned']:,} | Runs with subagents: {report['runs_with_subagents']:,}")
    if report.get("since"):
        print(f"  Window since: {report['since']}")
    if report.get("compare_since"):
        print(f"  Cohort split: {report['compare_since']}")

    if "pre" in report and "post" in report:
        _print_cohort_report("PRE-CUTOFF COHORT", report["pre"])
        _print_cohort_report("POST-CUTOFF COHORT", report["post"])
    else:
        _print_cohort_report("OVERALL COHORT", report["overall"])

    print("\n" + "═" * 74 + "\n")


if __name__ == "__main__":
    main()
