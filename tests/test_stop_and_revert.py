"""
test_stop_and_revert.py — Unit and integration tests for Nexus chat Stop & Revert functionality.

Tests:
  1. chats_db.py: revert_last_turn for mid-turn aborts (user prompt only)
  2. chats_db.py: revert_last_turn for completed turns (assistant + user messages)
  3. chats_db.py: revert_last_turn for empty threads (graceful None handling)
  4. hitl_queue.py: cancel_pending_transactions_for_conversation transitions pending items to 'cancelled'
  5. graph.py: rollback_checkpoints_for_thread prunes SQLite checkpoint DAG
  6. graph.py: is_thread_cancelled and cancel event lifecycle
  7. API: POST /api/agents/stop-and-revert halts active in-flight worker runs
  8. API: POST /api/agents/stop-and-revert rolls back completed turns and returns prompt
  9. API: POST /api/agents/stop-and-revert input validation
"""

import json
from pathlib import Path
import queue
import sqlite3
import threading
import pytest
from fastapi.testclient import TestClient

from nexus.api.main import app
from nexus.api.routers.agents import (
    ActiveRun,
    _active_runs,
    _active_runs_lock,
)
from nexus.agent.runtime import (
    is_thread_cancelled,
    register_cancel_event,
    unregister_cancel_event,
)
import nexus.core.chats_db as chats_db
from nexus.core.chats_db import (
    append_thread_lc_messages,
    create_conversation,
    delete_conversation,
    get_chat_history,
    load_thread_lc_messages,
    log_message,
    revert_last_turn,
    start_run_record,
)
import nexus.core.hitl_queue as hitl_queue
from nexus.core.hitl_queue import (
    add_transaction,
    cancel_pending_transactions_for_conversation,
    get_db_connection,
    get_pending_transactions,
)


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect `chats_db.DB_PATH` and `hitl_queue.DB_PATH` to isolated temporary SQLite DBs per test."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    chats_db.init_db()
    monkeypatch.setattr(hitl_queue, "DB_PATH", tmp_path / "test_hitl.db")
    hitl_queue.init_db()


@pytest.fixture
def client():
    """FastAPI TestClient fixture for invoking HTTP routes without binding a physical port."""
    return TestClient(app)


@pytest.fixture
def temp_conv():
    """Pytest fixture yielding a freshly initialized conversation thread and deleting it upon teardown."""
    conv_id = create_conversation(title="Stop and Revert Test Thread")
    try:
        yield conv_id
    finally:
        delete_conversation(conv_id)
        # Ensure active runs registry is cleaned up
        with _active_runs_lock:
            _active_runs.pop(conv_id, None)


def test_revert_last_turn_mid_turn_abort(temp_conv):
    """Verify that revert_last_turn cleans up a solitary user message logged during an aborted turn."""
    # Simulate mid-turn state: user sent query and image, but agent was stopped before answering
    log_message(
        role="user",
        content="What is my current net worth?",
        conversation_id=temp_conv,
        images=["/api/agents/uploads/receipt.png"],
    )

    history_before = get_chat_history(temp_conv)
    assert len(history_before) == 1

    revert_data = revert_last_turn(temp_conv)
    assert revert_data is not None
    assert revert_data["restored_query"] == "What is my current net worth?"
    assert revert_data["images"] == ["/api/agents/uploads/receipt.png"]
    assert revert_data["deleted_count"] == 1

    history_after = get_chat_history(temp_conv)
    assert len(history_after) == 0


def test_revert_last_turn_completed_turn(temp_conv):
    """Verify that revert_last_turn prunes both assistant and user messages for a completed turn."""
    # Turn 1: Completed
    log_message(role="user", content="Turn 1 prompt", conversation_id=temp_conv)
    log_message(role="assistant", content="Turn 1 reply", conversation_id=temp_conv)

    # Turn 2: Completed
    log_message(
        role="user",
        content="Turn 2 prompt with details",
        conversation_id=temp_conv,
        images=["/api/agents/uploads/chart.png"],
    )
    log_message(role="assistant", content="Turn 2 reply with analysis", conversation_id=temp_conv)

    history_before = get_chat_history(temp_conv)
    assert len(history_before) == 4

    revert_data = revert_last_turn(temp_conv)
    assert revert_data is not None
    assert revert_data["restored_query"] == "Turn 2 prompt with details"
    assert revert_data["images"] == ["/api/agents/uploads/chart.png"]
    assert revert_data["deleted_count"] == 2

    # Verify Turn 1 is untouched
    history_after = get_chat_history(temp_conv)
    assert len(history_after) == 2
    assert history_after[0]["content"] == "Turn 1 prompt"
    assert history_after[1]["content"] == "Turn 1 reply"


def test_revert_last_turn_empty_thread(temp_conv):
    """Verify that revert_last_turn returns None safely when invoked on an empty conversation."""
    revert_data = revert_last_turn(temp_conv)
    assert revert_data is None


def test_cancel_pending_transactions_for_conversation(temp_conv):
    """Verify that cancel_pending_transactions_for_conversation marks all staged edits as 'cancelled'."""
    # Add two staged transactions tied to this conversation
    tx1 = add_transaction(
        agent_name="nexus_agent",
        action_type="modify",
        target_file="Vault/1. Core/Plan.md",
        proposed_content="Proposed edit 1",
        original_content="Original text 1",
        reasoning="Test edit 1",
        conversation_id=temp_conv,
        thread_id=temp_conv,
    )
    tx2 = add_transaction(
        agent_name="nexus_agent",
        action_type="create",
        target_file="Vault/6. Engineering/NewNote.md",
        proposed_content="Proposed edit 2",
        original_content=None,
        reasoning="Test edit 2",
        conversation_id=temp_conv,
        thread_id=temp_conv,
    )

    pending_before = [tx["id"] for tx in get_pending_transactions()]
    assert tx1 in pending_before
    assert tx2 in pending_before

    # Cancel pending transactions for this conversation
    cancelled = cancel_pending_transactions_for_conversation(temp_conv)
    assert tx1 in cancelled
    assert tx2 in cancelled

    # Verify they are no longer in pending status
    pending_after = [tx["id"] for tx in get_pending_transactions()]
    assert tx1 not in pending_after
    assert tx2 not in pending_after

    # Verify their status is now 'cancelled' in hitl.db
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, status FROM transactions WHERE id IN (?, ?)",
        (tx1, tx2),
    ).fetchall()
    conn.close()
    for row in rows:
        assert row["status"] == "cancelled"


def test_checkpoint_cancellation_lifecycle(temp_conv):
    """Verify registration, query, and deregistration of thread cancellation events."""
    assert not is_thread_cancelled(temp_conv)

    evt = threading.Event()
    register_cancel_event(temp_conv, evt)
    assert not is_thread_cancelled(temp_conv)

    evt.set()
    assert is_thread_cancelled(temp_conv)
    # Also matches subagent child threads:
    assert is_thread_cancelled(f"{temp_conv}:subagent-1")

    unregister_cancel_event(temp_conv)
    assert not is_thread_cancelled(temp_conv)


def test_revert_last_turn_rolls_back_thread_messages_and_preserves_restored_images(
    temp_conv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Verify revert_last_turn prunes canonical thread_messages + run telemetry while keeping restored upload files on disk."""
    from langchain_core.messages import AIMessage, HumanMessage

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    img_file = uploads_dir / "keep_me.png"
    img_file.write_bytes(b"fake-png-bytes")
    monkeypatch.setattr(chats_db, "UPLOADS_DIR", uploads_dir)

    # Turn 1
    log_message(role="user", content="Turn 1", conversation_id=temp_conv)
    log_message(role="assistant", content="Reply 1", conversation_id=temp_conv, run_id="run_t1")
    append_thread_lc_messages(
        temp_conv,
        [HumanMessage(content="Turn 1"), AIMessage(content="Reply 1")],
        turn_id="run_t1",
    )

    # Turn 2 with uploaded image + run record
    start_run_record(
        run_id="run_t2",
        thread_id=temp_conv,
        query="Turn 2",
        image_refs=["/api/agents/uploads/keep_me.png"],
    )
    log_message(
        role="user",
        content="Turn 2",
        conversation_id=temp_conv,
        images=["/api/agents/uploads/keep_me.png"],
    )
    log_message(role="assistant", content="Reply 2", conversation_id=temp_conv, run_id="run_t2")
    append_thread_lc_messages(
        temp_conv,
        [HumanMessage(content="Turn 2"), AIMessage(content="Reply 2")],
        turn_id="run_t2",
        image_refs=["/api/agents/uploads/keep_me.png"],
    )

    revert_data = revert_last_turn(temp_conv)
    assert revert_data is not None
    assert revert_data["deleted_count"] == 2
    assert revert_data["images"] == ["/api/agents/uploads/keep_me.png"]
    # Restored image must remain on disk so the user can re-submit from composer
    assert img_file.exists()

    remaining_lc = load_thread_lc_messages(temp_conv)
    assert len(remaining_lc) == 2
    assert remaining_lc[0].content == "Turn 1"
    assert remaining_lc[1].content == "Reply 1"


def test_api_stop_and_revert_in_flight_run(client, temp_conv):
    """Verify that POST /api/agents/stop-and-revert signals active in-flight worker runs to halt."""
    cancel_evt = threading.Event()
    eq = queue.Queue()
    mock_run = ActiveRun(
        conversation_id=temp_conv,
        query="Research all job listings in New York",
        images=["/api/agents/uploads/job.png"],
        cancel_event=cancel_evt,
        pre_turn_checkpoint_id=None,
        event_queue=eq,
    )
    with _active_runs_lock:
        _active_runs[temp_conv] = mock_run

    # Log user query as if run had just commenced
    log_message(
        role="user",
        content="Research all job listings in New York",
        conversation_id=temp_conv,
        images=["/api/agents/uploads/job.png"],
    )

    response = client.post(
        "/api/agents/stop-and-revert",
        json={"conversation_id": temp_conv},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "stopped_and_reverted"
    assert payload["restored_query"] == "Research all job listings in New York"
    assert payload["restored_images"] == ["/api/agents/uploads/job.png"]

    # Verify mock active run was signalled
    assert mock_run.cancel_event.is_set()
    assert mock_run.is_stopped is True

    # Verify terminal notice was queued onto SSE stream queue
    queued_events = []
    while not eq.empty():
        queued_events.append(eq.get_nowait())
    assert any(e.get("type") == "done" and e.get("stopped") for e in queued_events)


def test_api_stop_and_revert_completed_turn(client, temp_conv):
    """Verify that POST /api/agents/stop-and-revert cleanly rolls back a completed turn and restores prompt."""
    log_message(role="user", content="Draft my cover letter", conversation_id=temp_conv)
    log_message(role="assistant", content="Here is your tailored cover letter...", conversation_id=temp_conv)

    response = client.post(
        "/api/agents/stop-and-revert",
        json={"conversation_id": temp_conv},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "stopped_and_reverted"
    assert payload["restored_query"] == "Draft my cover letter"
    assert payload["reverted_messages_count"] == 2

    history = get_chat_history(temp_conv)
    assert len(history) == 0


def test_api_stop_and_revert_validation(client):
    """Verify input validation for empty conversation_id."""
    response = client.post(
        "/api/agents/stop-and-revert",
        json={"conversation_id": "   "},
    )
    assert response.status_code == 400
