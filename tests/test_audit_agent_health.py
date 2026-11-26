"""Unit tests for `scripts/audit_agent_health.py` covering legacy/structured traces, cohorts, and JSON CLI."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from audit_agent_health import audit_health  # noqa: E402
import nexus.core.chats_db as chats_db  # noqa: E402
from nexus.core.chats_db import finalize_run_record, init_db  # noqa: E402


def _seed_sqlite_run(
    run_id: str,
    timestamp: str,
    trace_events: list[dict],
    subagents_count: int = 0,
    parent_model: str = "gemini-4-argon",
    parent_tier: str = "strong",
) -> None:
    finalize_run_record(
        run_id=run_id,
        timestamp=timestamp,
        ended_at=timestamp,
        status="done",
        source="chat",
        thread_id="audit-test-thread",
        agent_name="nexus",
        domain=None,
        confidence=None,
        reasoning=None,
        input_query="audit test",
        output_response="done",
        model_tier=parent_tier,
        model_name=parent_model,
        input_tokens=0,
        output_tokens=0,
        cached_tokens=0,
        reasoning_tokens=0,
        cost_usd=0.0,
        cache_savings_usd=0.0,
        latency_seconds=1.0,
        tool_calls=[],
        subagents_count=subagents_count,
        trace_events=trace_events,
        metadata={"model_name": parent_model, "model_tier": parent_tier},
    )


def test_audit_health_pre_post_cohorts_legacy_and_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify audit_health parses both legacy string caps and structured event_kind traces across pre/post cohorts."""
    test_db = tmp_path / "audit_health.db"
    monkeypatch.setattr(chats_db, "DB_PATH", test_db)
    init_db()

    # Pre-cohort run: 1 legacy 400k-capped subagent with 0% synthesis cache + parent respawn rework
    _seed_sqlite_run(
        run_id="pre00001",
        timestamp="2026-11-18T12:00:00+00:00",
        subagents_count=1,
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
            {
                "type": "llm_response",
                "agent_id": "subagent-1",
                "data": {"response": "Budget reached; edits still pending."},
            },
            {"type": "agent_end", "agent_id": "subagent-1", "message": "Completed at budget cap"},
            {
                "type": "tool_call",
                "agent_id": "nexus",
                "data": {"tool": "spawn_subagent", "args": {"task_prompt": "Finish Notes.md"}},
            },
        ],
    )

    # Post-cohort run: 1 soft-warned + cache-preserved hard-capped subagent
    _seed_sqlite_run(
        run_id="post0001",
        timestamp="2026-11-25T15:00:00+00:00",
        subagents_count=1,
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
            {
                "type": "llm_response",
                "agent_id": "subagent-1",
                "data": {"response": "Completed full audit summary cleanly."},
            },
            {"type": "agent_end", "agent_id": "subagent-1", "message": "Completed at budget cap"},
        ],
    )

    report = audit_health(db_path=test_db, compare_since="2026-11-19T01:15")
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


def test_audit_health_cli_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify scripts/audit_agent_health.py --json executes cleanly as a standalone CLI against SQLite."""
    test_db = tmp_path / "cli_health.db"
    monkeypatch.setattr(chats_db, "DB_PATH", test_db)
    init_db()
    _seed_sqlite_run(
        run_id="cli00001",
        timestamp="2026-11-25T16:00:00+00:00",
        subagents_count=1,
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
        [sys.executable, str(SCRIPTS_DIR / "audit_agent_health.py"), "--db-path", str(test_db), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    parsed = json.loads(proc.stdout)
    assert parsed["overall"]["subagents_count"] == 1
    assert parsed["overall"]["hard_caps_total"] == 0
    assert parsed["overall"]["alerts"] == []
