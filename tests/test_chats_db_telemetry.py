"""
test_chats_db_telemetry.py — Unit tests for decoupled chat telemetry and lazy trace loading.
Validates:
  1. `message_traces` table schema isolation and `messages` metadata columns.
  2. `log_message` keeps `messages.trace` NULL and writes diagnostic telemetry to `message_traces`.
  3. `get_chat_history` returns lean payloads (~1KB/turn) by default without trace blobs.
  4. `get_message_trace` retrieves full untruncated telemetry arrays on demand.
  5. Cascade deletion in `delete_conversation` and `revert_last_turn` cleans up `message_traces`.
  6. Bounded string summaries in `AgentTracer` prevent multi-megabyte string duplication.
  7. `GET /api/agents/messages/{message_id}/trace` API endpoint returns on-demand telemetry.
"""
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

import nexus.core.chats_db as chats_db
from nexus.core.chats_db import (
    _get_conn,
    create_conversation,
    delete_conversation,
    get_chat_history,
    get_message_trace,
    init_db,
    log_message,
    revert_last_turn,
)
from nexus.core.trace import AgentTracer, trace_bus
from nexus.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_chats_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect `chats_db.DB_PATH` to an isolated temporary SQLite database per test."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    init_db()


@pytest.fixture
def temp_conv():
    """Provides a fresh temporary conversation thread for testing and cleans it up afterward."""
    conv_id = create_conversation(title="Test Telemetry Decoupling")
    yield conv_id
    delete_conversation(conv_id)


def test_messages_table_schema_and_columns():
    """Verify that messages table includes model_tier, model_name, cost_usd, and has_trace columns."""
    init_db()
    with _get_conn() as conn:
        cols = [col[1] for col in conn.execute("PRAGMA table_info(messages)").fetchall()]
        assert "model_tier" in cols
        assert "model_name" in cols
        assert "cost_usd" in cols
        assert "has_trace" in cols

        trace_cols = [col[1] for col in conn.execute("PRAGMA table_info(message_traces)").fetchall()]
        assert "message_id" in trace_cols
        assert "trace" in trace_cols


def test_log_message_decouples_trace_into_message_traces(temp_conv):
    """Verify log_message stores trace in message_traces and keeps messages.trace NULL."""
    mock_trace = [
        {"id": "step1", "type": "agent_start", "message": "Starting turn"},
        {"id": "step2", "type": "info", "data": {"cost_usd": 0.0042, "input_tokens": 100, "output_tokens": 50}},
        {"id": "step3", "type": "tool_result", "data": {"tool": "read_file", "result": "sample content"}},
    ]

    msg_id = log_message(
        role="assistant",
        content="Here is the retrieved answer.",
        agent="nexus",
        domain="engineering",
        confidence=0.98,
        trace=mock_trace,
        conversation_id=temp_conv,
        model_tier="flash",
        model_name="gemini-2.5-flash",
        cost_usd=0.0042,
    )
    assert msg_id is not None

    with _get_conn() as conn:
        # Verify primary messages row has trace = NULL to prevent B-tree overflow
        msg_row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        assert msg_row["trace"] is None
        assert msg_row["has_trace"] == 1
        assert msg_row["model_tier"] == "flash"
        assert msg_row["model_name"] == "gemini-2.5-flash"
        assert abs(msg_row["cost_usd"] - 0.0042) < 1e-6

        # Verify dedicated message_traces row has the complete trace array
        trace_row = conn.execute("SELECT * FROM message_traces WHERE message_id = ?", (msg_id,)).fetchone()
        assert trace_row is not None
        assert "read_file" in trace_row["trace"]


def test_get_chat_history_is_lean_by_default(temp_conv):
    """Verify get_chat_history excludes trace blobs by default, keeping payloads tiny."""
    mock_trace = [{"id": "evt1", "type": "tool_call", "message": "Heavy tool invocation" * 50}]
    log_message(
        role="assistant",
        content="Summary output",
        trace=mock_trace,
        conversation_id=temp_conv,
        model_tier="pro",
        model_name="gemini-2.5-pro",
        cost_usd=0.0125,
    )

    # Default fetch: trace must be empty array, but metadata flags present
    history = get_chat_history(temp_conv)
    assert len(history) == 1
    entry = history[0]
    assert entry["content"] == "Summary output"
    assert entry["trace"] == []
    assert entry["has_trace"] is True
    assert entry["model_tier"] == "pro"
    assert entry["model_name"] == "gemini-2.5-pro"
    assert abs(entry["cost_usd"] - 0.0125) < 1e-6

    # Explicit eager-load fetch: trace is populated
    eager_history = get_chat_history(temp_conv, include_trace=True)
    assert len(eager_history) == 1
    assert len(eager_history[0]["trace"]) == 1
    assert eager_history[0]["trace"][0]["id"] == "evt1"


def test_get_message_trace_on_demand(temp_conv):
    """Verify get_message_trace fetches the full untruncated trace array for a message ID."""
    mock_trace = [
        {"id": "stepA", "type": "tool_result", "data": {"tool": "web_search", "result": "Search hits"}},
    ]
    msg_id = log_message(
        role="assistant",
        content="Search answer",
        trace=mock_trace,
        conversation_id=temp_conv,
    )

    fetched_trace = get_message_trace(msg_id)
    assert len(fetched_trace) == 1
    assert fetched_trace[0]["id"] == "stepA"
    assert fetched_trace[0]["data"]["result"] == "Search hits"


def test_message_trace_endpoint(temp_conv):
    """Verify GET /api/agents/messages/{message_id}/trace returns on-demand telemetry."""
    mock_trace = [
        {"id": "stepX", "type": "llm_call", "message": "Invoking model..."},
    ]
    msg_id = log_message(
        role="assistant",
        content="Final response",
        trace=mock_trace,
        conversation_id=temp_conv,
    )

    response = client.get(f"/api/agents/messages/{msg_id}/trace")
    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == msg_id
    assert len(data["trace"]) == 1
    assert data["trace"][0]["id"] == "stepX"


def test_delete_conversation_cleans_message_traces(temp_conv):
    """Verify delete_conversation purges both messages and message_traces rows."""
    msg_id = log_message(
        role="assistant",
        content="Response to delete",
        trace=[{"id": "e1"}],
        conversation_id=temp_conv,
    )

    with _get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM message_traces WHERE message_id = ?", (msg_id,)).fetchone()[0] == 1

    delete_conversation(temp_conv)

    with _get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM message_traces WHERE message_id = ?", (msg_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE id = ?", (msg_id,)).fetchone()[0] == 0


def test_revert_last_turn_cleans_message_traces(temp_conv):
    """Verify revert_last_turn purges message_traces along with deleted messages."""
    log_message(role="user", content="User prompt to revert", conversation_id=temp_conv)
    msg_id = log_message(
        role="assistant",
        content="Assistant response to revert",
        trace=[{"id": "t1"}],
        conversation_id=temp_conv,
    )

    with _get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM message_traces WHERE message_id = ?", (msg_id,)).fetchone()[0] == 1

    revert_result = revert_last_turn(temp_conv)
    assert revert_result is not None
    assert revert_result["deleted_count"] == 2

    with _get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM message_traces WHERE message_id = ?", (msg_id,)).fetchone()[0] == 0


def test_agent_tracer_bounded_string_summaries():
    """Verify AgentTracer preserves full data payloads while bounding string summary bloat."""
    emitted = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt))

    try:
        tracer = AgentTracer("TestAgent", color="cyan", agent_id="test_agent")

        # Huge result string (e.g. 5000 chars)
        big_result = "R" * 5000
        tracer.tool_result("read_file", result=big_result, call_id="c1")

        assert len(emitted) == 1
        res_evt = emitted[0]
        # Data payload retains 100% untruncated content for DAG/audit inspection
        assert res_evt["data"]["result"] == big_result
        # Event message summary is bounded to prevent duplicate multi-megabyte string serialization
        assert "5,000 chars output" in res_evt["message"]
        assert len(res_evt["message"]) < 200

        # Huge args dict (e.g. 3000 chars replacement)
        big_arg = "A" * 3000
        tracer.tool_call("modify_file", args={"target": "old", "replacement": big_arg}, call_id="c2")

        assert len(emitted) == 2
        call_evt = emitted[1]
        assert call_evt["data"]["args"]["replacement"] == big_arg
        assert len(call_evt["message"]) < 500
    finally:
        unsub()
