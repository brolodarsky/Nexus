"""
test_agent_tracking_and_graph.py — Unit tests for lossless agent tracking, subagent lineage, and run logging.

Tests:
  1. AgentTracer emits untruncated messages, tool args, and results with hierarchical agent_id & parent_id.
  2. Subagent serial allocation assigns sequential serial numbers and reset_subagent_counter resets properly.
  3. log_run persists structured subagent run records, token usage, and trace events without truncation.
  4. list_runs returns uncut query and response previews along with accurate subagents_count.
"""
import json
import shutil
from pathlib import Path
import pytest

from nexus.core.trace import AgentTracer, trace_bus
from nexus.agent.graph import _next_subagent_tracer, reset_subagent_counter
from nexus.core.run_logger import log_run, list_runs, get_run, RUNS_DIR


def test_agent_tracer_lossless_emission():
    """Verify AgentTracer emits 100% untruncated trace events with agent_id, parent_id, and step numbers."""
    emitted = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt))

    try:
        tracer = AgentTracer("Subagent #1 (low)", color="magenta", agent_id="subagent-1", parent_id="nexus")
        long_prompt = "A" * 5000
        tracer.agent_start(f"Starting — {long_prompt}", metadata={"task_prompt": long_prompt})

        assert len(emitted) == 1
        evt = emitted[0]
        assert evt["agent"] == "Subagent #1 (low)"
        assert evt["agent_id"] == "subagent-1"
        assert evt["parent_id"] == "nexus"
        assert evt["step"] == 1
        assert evt["data"]["task_prompt"] == long_prompt
        assert len(evt["message"]) >= 5000  # Not truncated!

        long_arg = "B" * 3000
        tracer.tool_call("modify_file", args={"target": "old", "replacement": long_arg}, call_id="call_123")
        assert len(emitted) == 2
        call_evt = emitted[1]
        assert call_evt["data"]["tool"] == "modify_file"
        assert call_evt["data"]["args"]["replacement"] == long_arg
        assert call_evt["data"]["call_id"] == "call_123"

        long_result = "C" * 8000
        tracer.tool_result("modify_file", result=long_result, call_id="call_123")
        assert len(emitted) == 3
        res_evt = emitted[2]
        assert res_evt["data"]["result"] == long_result
    finally:
        unsub()


def test_subagent_serial_allocation_and_reset():
    """Verify sequential allocation of subagent serial numbers and lineage."""
    reset_subagent_counter()
    s1, id1, t1 = _next_subagent_tracer("low")
    s2, id2, t2 = _next_subagent_tracer("medium")

    assert s1 == 1
    assert id1 == "subagent-1"
    assert t1.agent_name == "Subagent #1 (low)"
    assert t1.parent_id == "nexus"

    assert s2 == 2
    assert id2 == "subagent-2"
    assert t2.agent_name == "Subagent #2 (medium)"
    assert t2.parent_id == "nexus"

    # Reset clears back to #1
    reset_subagent_counter()
    s3, id3, _ = _next_subagent_tracer("low")
    assert s3 == 1
    assert id3 == "subagent-1"


def test_log_run_persists_subagents_and_token_telemetry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify log_run structures subagent breakdowns and token counts into logs/runs/ snapshots."""
    test_runs_dir = tmp_path / "runs"
    monkeypatch.setattr("nexus.core.run_logger.RUNS_DIR", test_runs_dir)

    long_subagent_prompt = "Inspect all 5 career files and draft a 5000 word proposal: " + ("X" * 2000)
    mock_events = [
        {
            "step": 1,
            "type": "agent_start",
            "agent": "NexusAgent",
            "agent_id": "nexus",
            "parent_id": None,
            "color": "cyan",
            "message": "Starting query",
            "timestamp": "2026-10-26T22:00:00Z",
            "data": {},
        },
        {
            "step": 2,
            "type": "agent_start",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": f"Starting — {long_subagent_prompt}",
            "timestamp": "2026-10-26T22:00:01Z",
            "data": {"task_prompt": long_subagent_prompt, "model_tier": "low"},
        },
        {
            "step": 3,
            "type": "info",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": "Tokens: 1,500 in (500 cached, 33%) | 200 out",
            "timestamp": "2026-10-26T22:00:02Z",
            "data": {"input_tokens": 1500, "output_tokens": 200, "cached_tokens": 500},
        },
        {
            "step": 4,
            "type": "llm_response",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": "Subagent distilled report text",
            "timestamp": "2026-10-26T22:00:03Z",
            "data": {"response": "Subagent distilled report text"},
        },
        {
            "step": 5,
            "type": "agent_end",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": "Done",
            "timestamp": "2026-10-26T22:00:04Z",
            "data": {},
        },
    ]

    file_path = log_run(
        agent_name="nexus",
        query="Research career files",
        response="Here is the finalized synthesis",
        thread_id="test-thread-abc",
        trace_events=mock_events,
        latency_seconds=4.5,
    )

    assert file_path.is_file()
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["subagents_count"] == 1
    assert len(data["subagents"]) == 1
    sub = data["subagents"][0]
    assert sub["agent_id"] == "subagent-1"
    assert sub["agent_name"] == "Subagent #1 (low)"
    assert sub["task_prompt"] == long_subagent_prompt
    assert sub["final_response"] == "Subagent distilled report text"
    assert data["metadata"]["token_usage"]["input_tokens"] == 1500
    assert data["metadata"]["token_usage"]["cached_tokens"] == 500

    # Test list_runs
    summaries = list_runs(limit=10)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["subagents_count"] == 1
    assert summary["input_query"] == "Research career files"
