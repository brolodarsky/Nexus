"""
audit_run_costs.py — Observability script for auditing and backfilling LLM run costs.

Queries persisted execution runs from SQLite `chats.db` (`runs` + `trace_events`),
computes token costs and context-caching savings based on provider pricing tables,
displays formatted aggregate summaries, and optionally backfills `cost_usd`.

Usage:
    .venv\\Scripts\\python.exe scripts\\audit_run_costs.py
    .venv\\Scripts\\python.exe scripts\\audit_run_costs.py --top 10
    .venv\\Scripts\\python.exe scripts\\audit_run_costs.py --backfill
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

# Add src to sys.path so nexus core modules can be imported directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import nexus.core.chats_db as chats_db
from nexus.core.cost import calculate_cache_savings, calculate_token_cost


def _infer_model_from_fields(
    raw_model_name: Optional[str],
    raw_model_tier: Optional[str],
    reasoning: Optional[str],
) -> tuple[str, str]:
    reasoning_str = str(reasoning or "").lower()
    if raw_model_name and raw_model_tier and raw_model_name != "unknown":
        return raw_model_name, raw_model_tier
    if "claude-opus" in reasoning_str or "opus" in reasoning_str:
        return raw_model_name or "claude-opus-5-5", raw_model_tier or "strong"
    if "claude-sonnet" in reasoning_str or "sonnet" in reasoning_str:
        return raw_model_name or "claude-sonnet-5-5", raw_model_tier or "medium"
    if "claude-haiku" in reasoning_str or "haiku" in reasoning_str:
        return raw_model_name or "claude-haiku-5-5", raw_model_tier or "low"
    if "gemini-4-argon" in reasoning_str or "strong" in reasoning_str:
        return raw_model_name or "gemini-4-argon", raw_model_tier or "strong"
    if "gemini-4-hydrogen" in reasoning_str or "hydrogen" in reasoning_str:
        return raw_model_name or "gemini-4-hydrogen", raw_model_tier or "low"
    if "gemini-3.8-flash" in reasoning_str or "flash" in reasoning_str or "low" in reasoning_str:
        return raw_model_name or "gemini-3.8-flash", raw_model_tier or "low"
    if "gemini-2.5-pro" in reasoning_str or "medium" in reasoning_str:
        return raw_model_name or "gemini-2.5-pro", raw_model_tier or "medium"
    return raw_model_name or "gemini-4-argon", raw_model_tier or "strong"


def audit_runs(
    backfill: bool = False,
    top_n: int = 5,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Audit LLM run costs and prompt-cache savings from SQLite `chats.db` (or explicit `--db-path`).
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    total_runs = 0
    total_in_tokens = 0
    total_out_tokens = 0
    total_cached_tokens = 0
    total_cost_usd = 0.0
    total_savings_usd = 0.0
    backfilled_count = 0

    cost_by_model: Dict[str, float] = defaultdict(float)
    tokens_by_model: Dict[str, int] = defaultdict(int)
    runs_record: List[Dict[str, Any]] = []

    prev_db = chats_db.DB_PATH
    if db_path is not None:
        if not db_path.is_file():
            print(f"❌ SQLite database not found: {db_path}")
            return {}
        chats_db.DB_PATH = db_path

    try:
        with chats_db._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT run_id, timestamp, reasoning, input_query, model_tier, model_name,
                       input_tokens, output_tokens, cached_tokens, cost_usd, cache_savings_usd, metadata_json
                FROM runs
                ORDER BY timestamp DESC
                """
            ).fetchall()

            for row in rows:
                total_runs += 1
                run_id = row["run_id"]
                meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                tok = meta.get("token_usage") or {}

                model_name, model_tier = _infer_model_from_fields(
                    row["model_name"] or meta.get("model_name"),
                    row["model_tier"] or meta.get("model_tier"),
                    row["reasoning"],
                )

                in_tok = int(row["input_tokens"] or tok.get("input_tokens") or 0)
                out_tok = int(row["output_tokens"] or tok.get("output_tokens") or 0)
                cached_tok = int(row["cached_tokens"] or tok.get("cached_tokens") or 0)

                if in_tok == 0 and out_tok == 0:
                    evt_rows = conn.execute(
                        "SELECT event_json FROM trace_events WHERE run_id = ? ORDER BY seq ASC",
                        (run_id,),
                    ).fetchall()
                    for er in evt_rows:
                        try:
                            evt = json.loads(er["event_json"])
                        except Exception:
                            continue
                        if evt.get("type") != "info":
                            continue
                        ed = evt.get("data") or {}
                        if isinstance(ed, dict) and ("input_tokens" in ed or "output_tokens" in ed):
                            in_tok += int(ed.get("input_tokens", 0) or 0)
                            out_tok += int(ed.get("output_tokens", 0) or 0)
                            cached_tok += int(ed.get("cached_tokens", 0) or 0)
                        elif in_tok == 0 and isinstance(evt.get("message"), str):
                            m = re.search(
                                r"Tokens:\s*([\d,]+)\s*in\s*\(([\d,]+)\s*cached.*?\)\s*\|\s*([\d,]+)\s*out",
                                evt["message"],
                            )
                            if m:
                                in_tok += int(m.group(1).replace(",", ""))
                                cached_tok += int(m.group(2).replace(",", ""))
                                out_tok += int(m.group(3).replace(",", ""))

                has_valid_meta = (row["model_name"] or meta.get("model_name")) not in (None, "unknown", "")
                existing_cost = row["cost_usd"] if has_valid_meta else None
                if existing_cost is None or existing_cost == 0.0:
                    existing_cost = tok.get("cost_usd") if has_valid_meta else None

                cost_usd = (
                    float(existing_cost)
                    if existing_cost is not None and existing_cost > 0.0
                    else calculate_token_cost(
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        cached_tokens=cached_tok,
                        model_name=model_name,
                        tier=model_tier,
                        as_of=row["timestamp"],
                    )
                )

                existing_savings = row["cache_savings_usd"] if has_valid_meta else None
                if existing_savings is None:
                    existing_savings = tok.get("cache_savings_usd") if has_valid_meta else None
                savings_usd = (
                    float(existing_savings)
                    if existing_savings is not None and existing_savings > 0.0
                    else calculate_cache_savings(
                        input_tokens=in_tok,
                        cached_tokens=cached_tok,
                        model_name=model_name,
                        tier=model_tier,
                        as_of=row["timestamp"],
                    )
                )

                needs_backfill = (
                    row["cost_usd"] in (None, 0.0)
                    or not has_valid_meta
                    or not row["input_tokens"]
                )
                if backfill and needs_backfill:
                    meta["model_name"] = model_name
                    meta["model_tier"] = model_tier
                    meta["token_usage"] = {
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "cached_tokens": cached_tok,
                        "total_tokens": in_tok + out_tok,
                        "cost_usd": cost_usd,
                        "cache_savings_usd": savings_usd,
                    }
                    conn.execute(
                        """
                        UPDATE runs
                        SET model_name = ?, model_tier = ?, input_tokens = ?, output_tokens = ?,
                            cached_tokens = ?, cost_usd = ?, cache_savings_usd = ?, metadata_json = ?
                        WHERE run_id = ?
                        """,
                        (
                            model_name,
                            model_tier,
                            in_tok,
                            out_tok,
                            cached_tok,
                            cost_usd,
                            savings_usd,
                            json.dumps(meta, ensure_ascii=False),
                            run_id,
                        ),
                    )
                    backfilled_count += 1

                total_in_tokens += in_tok
                total_out_tokens += out_tok
                total_cached_tokens += cached_tok
                total_cost_usd += cost_usd
                total_savings_usd += savings_usd
                cost_by_model[model_name] += cost_usd
                tokens_by_model[model_name] += in_tok + out_tok
                runs_record.append({
                    "run_id": run_id,
                    "filename": f"{run_id}.sqlite",
                    "timestamp": row["timestamp"] or "",
                    "model": model_name,
                    "cost_usd": cost_usd,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cached_tokens": cached_tok,
                    "query": (row["input_query"] or "")[:80].replace("\n", " "),
                })

            if backfill and backfilled_count > 0:
                conn.commit()
    finally:
        chats_db.DB_PATH = prev_db

    total_tokens = total_in_tokens + total_out_tokens
    cache_pct = (total_cached_tokens / total_in_tokens * 100) if total_in_tokens > 0 else 0.0

    print("\n" + "═" * 70)
    print(" 📊 NEXUS LLM RUN COST & USAGE AUDIT")
    print("═" * 70)
    print(f"  • Total Run Snapshots:   {total_runs:,}")
    print(f"  • Total Tokens:          {total_tokens:,}")
    print(f"    - Input Tokens:        {total_in_tokens:,}")
    print(f"    - Cached Tokens:       {total_cached_tokens:,} ({cache_pct:.1f}% cache hit rate)")
    print(f"    - Output Tokens:       {total_out_tokens:,}")
    print("─" * 70)
    print(f"  • Total Estimated Spend: ${total_cost_usd:,.4f} USD")
    print(f"  • Cache Savings (Saved): ${total_savings_usd:,.4f} USD")
    if backfill:
        print(f"  • Snapshots Backfilled:  {backfilled_count:,}")
    print("─" * 70)

    print(" 🏷️  COST BREAKDOWN BY MODEL:")
    for model, cost in sorted(cost_by_model.items(), key=lambda x: x[1], reverse=True):
        tok_cnt = tokens_by_model[model]
        print(f"    - {model:<24} ${cost:>8.4f} ({tok_cnt:>10,d} tokens)")

    if runs_record and top_n > 0:
        print("\n" + "─" * 70)
        print(f" 🏆 TOP {min(top_n, len(runs_record))} HIGHEST-COST RUNS:")
        top_runs = sorted(runs_record, key=lambda x: x["cost_usd"], reverse=True)[:top_n]
        for idx, r in enumerate(top_runs, 1):
            print(f"    {idx}. [#{r['run_id']}] ${r['cost_usd']:.4f} · {r['model']} · {r['query']}...")

    print("═" * 70 + "\n")

    return {
        "total_runs": total_runs,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "total_savings_usd": total_savings_usd,
        "backfilled_count": backfilled_count,
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Audit and backfill LLM execution costs in Nexus.")
    parser.add_argument("--backfill", action="store_true", help="Write computed cost_usd back to SQLite runs.")
    parser.add_argument("--top", type=int, default=5, help="Number of highest-cost runs to display (default: 5).")
    parser.add_argument("--db-path", type=Path, default=None, help="Optional SQLite DB path (defaults to logs/chats.db).")
    args = parser.parse_args()

    audit_runs(backfill=args.backfill, top_n=args.top, db_path=args.db_path)


if __name__ == "__main__":
    main()
