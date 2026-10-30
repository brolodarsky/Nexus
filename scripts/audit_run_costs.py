"""
audit_run_costs.py — Observability script for auditing and backfilling LLM run costs.

Scans all persisted run execution snapshots in `logs/runs/*.json`, computes token costs
and context-caching savings based on provider pricing tables, displays formatted aggregate
summaries, and optionally backfills `cost_usd` into legacy snapshots.

Usage:
    .venv\\Scripts\\python.exe scripts\\audit_run_costs.py
    .venv\\Scripts\\python.exe scripts\\audit_run_costs.py --top 10
    .venv\\Scripts\\python.exe scripts\\audit_run_costs.py --backfill
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Add src to sys.path so nexus core modules can be imported directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nexus.core.cost import calculate_cache_savings, calculate_token_cost

RUNS_DIR = PROJECT_ROOT / "logs" / "runs"


def audit_runs(backfill: bool = False, top_n: int = 5) -> Dict[str, Any]:
    """
    Parses all JSON run snapshots in logs/runs/, calculates financial and token metrics,
    and optionally writes computed cost_usd back to disk.

    Args:
        backfill: If True, writes missing cost_usd and cache_savings_usd back into JSON files.
        top_n: Number of highest-cost runs to highlight in summary.

    Returns:
        Dictionary of aggregated metrics.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not RUNS_DIR.is_dir():
        print(f"❌ Runs directory not found: {RUNS_DIR}")
        return {}

    run_files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not run_files:
        print(f"ℹ️ No run snapshots found in {RUNS_DIR}")
        return {}

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

    for file_path in run_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading {file_path.name}: {e}")
            continue

        total_runs += 1
        meta = data.get("metadata") or {}
        tok = meta.get("token_usage") or {}

        # 1. Resolve model name and capability tier
        # Prioritize explicit metadata; fall back to inspecting agent reasoning strings or default to "strong"
        raw_model_name = meta.get("model_name")
        raw_model_tier = meta.get("model_tier")
        reasoning_str = str(data.get("reasoning") or "").lower()

        if raw_model_name and raw_model_tier and raw_model_name != "unknown":
            model_name = raw_model_name
            model_tier = raw_model_tier
        elif "gemini-4-argon" in reasoning_str or "strong" in reasoning_str:
            model_name = raw_model_name or "gemini-4-argon"
            model_tier = raw_model_tier or "strong"
        elif "gemini-3.8-flash" in reasoning_str or "flash" in reasoning_str or "low" in reasoning_str:
            model_name = raw_model_name or "gemini-3.8-flash"
            model_tier = raw_model_tier or "low"
        elif "gemini-2.5-pro" in reasoning_str or "medium" in reasoning_str:
            model_name = raw_model_name or "gemini-2.5-pro"
            model_tier = raw_model_tier or "medium"
        else:
            # Nexus default primary agent tier is "strong" (gemini-4-argon)
            model_name = raw_model_name or "gemini-4-argon"
            model_tier = raw_model_tier or "strong"

        # 2. Extract token usage (from token_usage metadata, or fall back to parsing trace telemetry)
        in_tok = int(tok.get("input_tokens", 0) or 0)
        out_tok = int(tok.get("output_tokens", 0) or 0)
        cached_tok = int(tok.get("cached_tokens", 0) or 0)

        # Legacy run recovery: parse tokens from trace info events or formatted message strings
        if in_tok == 0 and out_tok == 0:
            for evt in data.get("trace_events") or []:
                e_type = evt.get("type")
                e_data = evt.get("data") or {}
                if e_type == "info" and isinstance(e_data, dict):
                    in_tok += int(e_data.get("input_tokens", 0) or 0)
                    out_tok += int(e_data.get("output_tokens", 0) or 0)
                    cached_tok += int(e_data.get("cached_tokens", 0) or 0)
                elif in_tok == 0 and e_type == "info" and isinstance(evt.get("message"), str):
                    m = re.search(
                        r"Tokens:\s*([\d,]+)\s*in\s*\(([\d,]+)\s*cached.*?\)\s*\|\s*([\d,]+)\s*out",
                        evt["message"],
                    )
                    if m:
                        in_tok += int(m.group(1).replace(",", ""))
                        cached_tok += int(m.group(2).replace(",", ""))
                        out_tok += int(m.group(3).replace(",", ""))

        # 3. Check if cost is already persisted with valid non-zero metadata, or needs recalculation
        has_valid_meta = meta.get("model_name") not in (None, "unknown", "")
        existing_cost = data.get("cost_usd") if has_valid_meta else None
        if existing_cost is None or existing_cost == 0.0:
            existing_cost = tok.get("cost_usd") if has_valid_meta else None

        if existing_cost is not None and existing_cost > 0.0:
            cost_usd = float(existing_cost)
        else:
            cost_usd = calculate_token_cost(
                input_tokens=in_tok,
                output_tokens=out_tok,
                cached_tokens=cached_tok,
                model_name=model_name,
                tier=model_tier,
            )

        existing_savings = tok.get("cache_savings_usd") if has_valid_meta else None
        if existing_savings is not None and existing_savings > 0.0:
            savings_usd = float(existing_savings)
        else:
            savings_usd = calculate_cache_savings(
                input_tokens=in_tok,
                cached_tokens=cached_tok,
                model_name=model_name,
                tier=model_tier,
            )

        # 4. Optional in-place backfill
        needs_backfill = (
            data.get("cost_usd") in (None, 0.0)
            or tok.get("cost_usd") in (None, 0.0)
            or not has_valid_meta
            or not tok.get("input_tokens")
        )
        if backfill and needs_backfill:
            data["cost_usd"] = cost_usd
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
            data["metadata"] = meta
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                backfilled_count += 1
            except Exception as e:
                print(f"⚠️ Failed to backfill {file_path.name}: {e}")

        total_in_tokens += in_tok
        total_out_tokens += out_tok
        total_cached_tokens += cached_tok
        total_cost_usd += cost_usd
        total_savings_usd += savings_usd

        cost_by_model[model_name] += cost_usd
        tokens_by_model[model_name] += in_tok + out_tok

        runs_record.append({
            "run_id": data.get("run_id", file_path.stem),
            "filename": file_path.name,
            "timestamp": data.get("timestamp", ""),
            "model": model_name,
            "cost_usd": cost_usd,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cached_tokens": cached_tok,
            "query": (data.get("input_query") or "")[:80].replace("\n", " "),
        })

    # Terminal output rendering
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
    parser.add_argument("--backfill", action="store_true", help="Write cost_usd back to legacy run snapshots on disk.")
    parser.add_argument("--top", type=int, default=5, help="Number of highest-cost runs to display (default: 5).")
    args = parser.parse_args()

    audit_runs(backfill=args.backfill, top_n=args.top)


if __name__ == "__main__":
    main()
