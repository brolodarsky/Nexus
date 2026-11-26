"""Unit tests for `scripts/audit_agent_health.py` covering legacy/structured traces, cohorts, and JSON CLI."""

import json
from pathlib import Path
import subprocess
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from audit_agent_health import audit_health  # noqa: E402


def _write_run(
    runs_dir: Path,
    filename: str,
    trace_events: list[dict],
    subagents: list[dict] | None = None,
    parent_model: str = "gemini-4-argon",
    parent_tier: str = "strong",
) -> None:
    payload = {
        "run_id": filename[:8],
        "timestamp": "2026-11-25T12:00:00+00:00",
        "metadata": {"model_name": parent_model, "model_tier": parent_tier},
        "subagents": subagents or [],
        "trace_events": trace_events,
    }
    (runs_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_audit_health_pre_post_cohorts_legacy_and_structured(tmp_path: Path) -> None:
    """Verify audit_health parses both legacy string caps and structured event_kind traces across pre/post cohorts."""
    # Pre-cohort run: 1 legacy 400k-capped subagent with 0% synthesis cache + parent respawn rework
    _write_run(
        tmp_path,
        "20261118T120000Z_nexus_pre00001.json",
        trace_events=[
            {
                "type": "agent_start",
                "agent_id": "subagent-1",
                "data": {"model_name": "gemini-3.8-flash", "model_tier": "low", "task_prompt": "Update Notes.md via modify_file"},
            },
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "Tokens",
                "data": {"input_tokens": 50_000, "cached_tokens": 40_000, "output_tokens": 200},
            },
            {
                "type": "tool_call",
                "agent_id": "subagent-1",
                "data": {"tool": "read_file", "args": {"file_path": "Notes.md"}},
            },
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "⚠️ Subagent #1 reached input token budget (410,000/400,000). Requesting final tool-free synthesis...",
                "data": {"turn": 9},
            },
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "Tokens",
                "data": {"input_tokens": 50_000, "cached_tokens": 0, "output_tokens": 300},
            },
            {"type": "agent_end", "agent_id": "subagent-1", "message": "Completed at budget cap"},
            {
                "type": "tool_call",
                "agent_id": "nexus",
                "data": {"tool": "spawn_subagent", "args": {"task_prompt": "Finish Notes.md"}},
            },
        ],
        subagents=[
            {
                "agent_id": "subagent-1",
                "model_name": "gemini-3.8-flash",
                "model_tier": "low",
                "task_prompt": "Update Notes.md via modify_file",
                "final_response": "Budget reached; edits still pending.",
            }
        ],
    )

    # Post-cohort run: 1 soft-warned + cache-preserved hard-capped subagent (no alerts if clean, or clean synthesis cache)
    _write_run(
        tmp_path,
        "20261125T150000Z_nexus_post0001.json",
        trace_events=[
            {
                "type": "agent_start",
                "agent_id": "subagent-1",
                "data": {"model_name": "gemini-3.8-flash", "model_tier": "low", "task_prompt": "Audit Health Summary.md"},
            },
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "Tokens",
                "data": {"input_tokens": 100_000, "cached_tokens": 85_000, "output_tokens": 400},
            },
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "⏳ Subagent #1 approaching budget",
                "data": {"event_kind": "subagent_soft_warning", "turn": 23},
            },
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "⚠️ Subagent #1 reached turn limit (25/25).",
                "data": {
                    "event_kind": "subagent_budget_cap",
                    "reason": "turn_limit",
                    "turn": 25,
                    "cache_preserved_synthesis": True,
                },
            },
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "Tokens",
                "data": {"input_tokens": 102_000, "cached_tokens": 90_000, "output_tokens": 250},
            },
            {"type": "agent_end", "agent_id": "subagent-1", "message": "Completed at budget cap"},
        ],
        subagents=[
            {
                "agent_id": "subagent-1",
                "model_name": "gemini-3.8-flash",
                "model_tier": "low",
                "task_prompt": "Audit Health Summary.md",
                "final_response": "Completed full audit summary cleanly.",
            }
        ],
    )

    report = audit_health(runs_dir=tmp_path, compare_since="2026-11-19T01:15")
    assert report["runs_scanned"] == 2
    assert report["runs_with_subagents"] == 2

    pre = report["pre"]
    assert pre["subagents_count"] == 1
    assert pre["token_caps"] == 1
    assert pre["capped_analysis"]["unbound_fallback_count"] == 1
    assert pre["capped_analysis"]["synthesis_cache_pct"] == 0.0
    assert pre["capped_analysis"]["write_zero_staged_count"] == 1
    assert pre["capped_analysis"]["parent_respawn_count"] == 1
    assert any("SYNTHESIS CACHE CLIFF" in a for a in pre["alerts"])

    post = report["post"]
    assert post["subagents_count"] == 1
    assert post["soft_warnings"] == 1
    assert post["turn_caps"] == 1
    assert post["capped_analysis"]["cache_preserved_count"] == 1
    assert post["capped_analysis"]["synthesis_cache_pct"] > 80.0
    assert not any("SYNTHESIS CACHE CLIFF" in a for a in post["alerts"])


def test_audit_health_cli_json_output(tmp_path: Path) -> None:
    """Verify scripts/audit_agent_health.py --json executes cleanly as a standalone CLI."""
    _write_run(
        tmp_path,
        "20261125T160000Z_nexus_cli00001.json",
        trace_events=[
            {"type": "agent_start", "agent_id": "subagent-1", "data": {"model_name": "gemini-3.8-flash"}},
            {
                "type": "info",
                "agent_id": "subagent-1",
                "message": "Tokens",
                "data": {"input_tokens": 20_000, "cached_tokens": 16_000, "output_tokens": 100},
            },
            {"type": "agent_end", "agent_id": "subagent-1", "message": "Completed"},
        ],
    )

    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "audit_agent_health.py"), "--runs-dir", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    parsed = json.loads(proc.stdout)
    assert parsed["overall"]["subagents_count"] == 1
    assert parsed["overall"]["hard_caps_total"] == 0
    assert parsed["overall"]["alerts"] == []
