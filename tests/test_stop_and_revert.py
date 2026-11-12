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
from nexus.agent.graph import (
    MEMORY_DB_PATH,
    get_latest_checkpoint_id,
    is_thread_cancelled,
    register_cancel_event,
    rollback_checkpoints_for_thread,
    unregister_cancel_event,
)
import nexus.core.chats_db as chats_db
from nexus.core.chats_db import (
    create_conversation,
    delete_conversation,
    get_chat_history,
    log_message,
    revert_last_turn,
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


def test_rollback_checkpoints_for_thread(temp_conv):
    """Verify that rollback_checkpoints_for_thread prunes newer checkpoints and writes from memory.sqlite."""
    if not MEMORY_DB_PATH.exists():
        pytest.skip("memory.sqlite not present")

    try:
        with sqlite3.connect(MEMORY_DB_PATH) as conn:
            # Insert baseline checkpoint
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                VALUES (?, '', 'cp-001', '', 'state', '{}', ?)
                """,
                (temp_conv, json.dumps({"source": "loop", "step": 1})),
            )
            # Insert turn 2 input checkpoint
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                VALUES (?, '', 'cp-002', 'cp-001', 'state', '{}', ?)
                """,
                (temp_conv, json.dumps({"source": "input", "step": 2})),
            )
            # Insert turn 2 tool loop checkpoint
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                VALUES (?, '', 'cp-003', 'cp-002', 'state', '{}', ?)
                """,
                (temp_conv, json.dumps({"source": "loop", "step": 3})),
            )
            conn.commit()

        # Rollback turn 2
        deleted = rollback_checkpoints_for_thread(temp_conv, pre_turn_checkpoint_id="cp-001")
        assert deleted >= 1

        with sqlite3.connect(MEMORY_DB_PATH) as conn:
            remaining = conn.execute(
                "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id ASC",
                (temp_conv,),
            ).fetchall()
            cids = [r[0] for r in remaining]
            assert "cp-001" in cids
            assert "cp-002" not in cids
            assert "cp-003" not in cids
    finally:
        # Rollback all checkpoints for this temp thread to clean up even if assertions fail
        rollback_checkpoints_for_thread(temp_conv, pre_turn_checkpoint_id=None)


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
