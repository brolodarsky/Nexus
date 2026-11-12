"""
test_chat_stream_reattach.py — Integration tests for background ActiveRun tracking and SSE stream re-attachment.

Verifies that leaving a chat mid-turn and returning (or reloading) recovers all prior trace steps
and resumes live Thinking Panel streaming without dropping or duplicating events:
  1. GET /api/agents/ask/active and GET /api/agents/ask/active/{conversation_id} status discovery.
  2. GET /api/agents/ask/stream/{conversation_id} replays buffered trace backlog + streams remaining live steps.
  3. Post-completion re-attach gracefully emits `sync_required` so the UI reconciles with SQLite history.
  4. Duplicate concurrent POST /api/agents/ask/stream on the same active conversation returns HTTP 409.
  5. Deleting an in-flight conversation cleanly halts its ActiveRun and notifies attached subscribers.
"""

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import nexus.core.chats_db as chats_db
import nexus.core.hitl_queue as hitl_queue
from nexus.api.main import app
from nexus.api.routers.agents import ActiveRun, _active_runs, _active_runs_lock
from nexus.core.chats_db import create_conversation, delete_conversation, get_chat_history
from nexus.core.trace import AgentTracer


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect SQLite databases to temporary per-test files so live logs/chats.db is untouched."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    chats_db.init_db()
    monkeypatch.setattr(hitl_queue, "DB_PATH", tmp_path / "test_hitl.db")
    hitl_queue.init_db()


@pytest.fixture
def client():
    """FastAPI TestClient fixture for invoking HTTP and SSE streaming endpoints."""
    return TestClient(app)


@pytest.fixture
def temp_conv():
    """Creates a disposable conversation thread and guarantees cleanup of DB and _active_runs registry."""
    conv_id = create_conversation(title="Stream Reattach Test Thread")
    try:
        yield conv_id
    finally:
        with _active_runs_lock:
            _active_runs.pop(conv_id, None)
        delete_conversation(conv_id)


def _parse_sse_events(lines: list[str]) -> list[dict]:
    """Parses raw SSE `data: {...}` lines into decoded JSON event dicts."""
    events: list[dict] = []
    for line in lines:
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_active_run_backlog_and_live_reattach(client: TestClient, temp_conv: str):
    """Verify returning to an in-flight conversation replays prior steps and streams remaining live steps."""
    first_steps_emitted = threading.Event()
    allow_completion = threading.Event()

    def simulated_agent(query: str, thread_id: str, model_tier=None, images=None):
        tracer = AgentTracer("NexusAgent", color="cyan", agent_id="nexus", thread_id=thread_id)
        tracer.agent_start(f"Query: {query}", metadata={"model_tier": model_tier or "strong"})
        tracer.tool_call("vault_reader", args={"query": "flush"})
        first_steps_emitted.set()

        # Pause mid-turn so the test can inspect /ask/active and attach a second SSE client
        assert allow_completion.wait(timeout=5.0), "Timed out waiting for re-attach signal"
        tracer.tool_result("vault_reader", result="Loaded 3 files")
        tracer.agent_end("Completed")
        return {
            "response": "Flush complete.",
            "domain": "engineering",
            "confidence": 0.99,
            "reasoning": "Simulated flush",
            "model_tier": model_tier or "strong",
            "model_name": "gemini-4-argon",
            "tool_calls": [],
        }

    # Keep the original POST stream open in a background thread (or disconnect early after first steps)
    post_done = threading.Event()
    post_error: list[Exception] = []

    def run_initial_post():
        try:
            with client.stream(
                "POST",
                "/api/agents/ask/stream",
                json={
                    "query": "sent. let's do a flush on this thread",
                    "conversation_id": temp_conv,
                    "model_tier": "strong",
                },
            ) as resp:
                assert resp.status_code == 200
                for _ in resp.iter_lines():
                    pass
        except Exception as exc:
            post_error.append(exc)
        finally:
            post_done.set()

    with patch("nexus.agent.api.run_nexus_agent_with_trace", side_effect=simulated_agent):
        post_thread = threading.Thread(target=run_initial_post, daemon=True)
        post_thread.start()

        assert first_steps_emitted.wait(timeout=5.0), "Agent did not emit initial trace steps"

        # 1. Verify /ask/active and /ask/active/{conv_id} report the in-flight run
        list_res = client.get("/api/agents/ask/active")
        assert list_res.status_code == 200
        active_list = list_res.json()["active_runs"]
        assert any(r["conversation_id"] == temp_conv for r in active_list)

        status_res = client.get(f"/api/agents/ask/active/{temp_conv}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["active"] is True
        assert status_data["model_tier"] == "strong"
        assert status_data["step_count"] >= 2
        assert isinstance(status_data["user_message_id"], int)

        # 2. Re-attach via GET /api/agents/ask/stream/{conv_id} while the turn is mid-execution
        def release_agent():
            # Briefly delay so re-attach client snapshots backlog before final steps fire
            threading.Event().wait(0.15)
            allow_completion.set()

        threading.Thread(target=release_agent, daemon=True).start()

        with client.stream("GET", f"/api/agents/ask/stream/{temp_conv}") as reattach_resp:
            assert reattach_resp.status_code == 200
            raw_lines = [line for line in reattach_resp.iter_lines() if line]

        assert post_done.wait(timeout=5.0)
        assert not post_error

    events = _parse_sse_events(raw_lines)
    event_types = [e.get("type") for e in events]
    # Re-attached client must receive backlog steps (agent_start, tool_call) AND live steps (tool_result, agent_end, done)
    assert "agent_start" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "agent_end" in event_types
    assert event_types[-1] == "done"
    assert events[-1]["response"] == "Flush complete."

    # Verify zero duplicate event IDs between backlog replay and live delivery
    ids = [e["id"] for e in events if e.get("id")]
    assert len(ids) == len(set(ids))

    # 3. Verify active run registry cleared after completion and assistant reply persisted with trace
    after_res = client.get(f"/api/agents/ask/active/{temp_conv}")
    assert after_res.status_code == 200
    assert after_res.json()["active"] is False

    history = get_chat_history(temp_conv, include_trace=True)
    assert len(history) == 2
    assert history[1]["role"] == "assistant"
    assert history[1]["has_trace"] is True
    assert len(history[1]["trace"]) >= 4


def test_reattach_when_inactive_emits_sync_required(client: TestClient, temp_conv: str):
    """Verify GET /ask/stream/{conv_id} emits sync_required when no active run exists."""
    with client.stream("GET", f"/api/agents/ask/stream/{temp_conv}") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line]

    events = _parse_sse_events(lines)
    assert len(events) == 1
    assert events[0]["type"] == "sync_required"
    assert events[0]["conversation_id"] == temp_conv


def test_duplicate_stream_request_returns_409(client: TestClient, temp_conv: str):
    """Verify starting a second POST /ask/stream on an already active conversation fails cleanly with 409."""
    mock_run = ActiveRun(
        conversation_id=temp_conv,
        query="Already running",
        images=None,
        cancel_event=threading.Event(),
        pre_turn_checkpoint_id=None,
    )
    with _active_runs_lock:
        _active_runs[temp_conv] = mock_run

    resp = client.post(
        "/api/agents/ask/stream",
        json={"query": "Duplicate turn", "conversation_id": temp_conv},
    )
    assert resp.status_code == 409


def test_delete_conversation_cancels_active_run(client: TestClient, temp_conv: str):
    """Verify deleting a running conversation signals cancellation and notifies attached SSE subscribers."""
    cancel_evt = threading.Event()
    mock_run = ActiveRun(
        conversation_id=temp_conv,
        query="Long running task",
        images=None,
        cancel_event=cancel_evt,
        pre_turn_checkpoint_id=None,
    )
    _, _, sub_q = mock_run.subscribe()
    assert sub_q is not None

    with _active_runs_lock:
        _active_runs[temp_conv] = mock_run

    resp = client.delete(f"/api/agents/ask/conversations/{temp_conv}")
    assert resp.status_code == 200
    assert cancel_evt.is_set()
    assert mock_run.is_stopped is True

    queued = []
    while not sub_q.empty():
        queued.append(sub_q.get_nowait())
    assert any(evt.get("type") == "done" and evt.get("stopped") for evt in queued)


def test_safe_json_dumps_sanitizes_non_finite_floats_and_paths():
    """Verify SSE serialization never emits NaN/Infinity or fails on non-JSON objects."""
    import json
    from pathlib import Path
    from nexus.api.routers.agents import _safe_json_dumps

    payload = {
        "type": "trace",
        "event": {
            "event_type": "tool_result",
            "score": float("nan"),
            "upper": float("inf"),
            "lower": float("-inf"),
            "nested": [{"confidence": float("nan"), "path": Path("Vault/note.md")}],
        },
    }
    raw = _safe_json_dumps(payload)
    assert "NaN" not in raw
    assert "Infinity" not in raw

    def _reject_nonfinite(token: str):
        raise ValueError(f"Non-standard JSON constant emitted: {token}")

    parsed = json.loads(raw, parse_constant=_reject_nonfinite)
    assert parsed["event"]["score"] is None
    assert parsed["event"]["upper"] is None
    assert parsed["event"]["lower"] is None
    assert parsed["event"]["nested"][0]["confidence"] is None
    assert parsed["event"]["nested"][0]["path"] == str(Path("Vault/note.md"))

