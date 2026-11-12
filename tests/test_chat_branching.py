"""
test_chat_branching.py — Unit and integration tests for Universal Conversation Branching (`chats.db` DAG)
and Subroutine Distillation & Merge (`src/nexus/core/chat_branching.py`, `src/nexus/api/routers/chat_branches.py`).

Tests:
  1. Full History Fork (`branch_mode="fork"`) at an intermediate message ID (`parent_message_id`).
  2. Context-Sliced Tangent Branch (`branch_mode="tangent"`) with proportional `Parent Context Brief` + focal turn preservation.
  3. First-turn Tangent Branch optimization (no redundant brief when branching on Turn 1).
  4. Subroutine Return (`POST /api/agents/ask/conversations/{id}/merge`) distilling child work into parent thread (`chats.db` + LangGraph state).
  5. Safe parent deletion promoting child branches to root level (`parent_conversation_id = None`).
  6. Error guards for missing conversations (HTTP 404) and root merge attempts (HTTP 400).
"""

from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from nexus.api.main import app
from nexus.agent.graph import rollback_checkpoints_for_thread
import nexus.core.chats_db as chats_db
from nexus.core.chats_db import (
    create_conversation,
    delete_conversation,
    get_chat_history,
    get_conversation,
    log_message,
)


@pytest.fixture(autouse=True)
def isolated_chats_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect `chats_db.DB_PATH` to an isolated temporary SQLite database per test."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    chats_db.init_db()


@pytest.fixture
def client():
    """FastAPI TestClient fixture for invoking branching and merge HTTP routes."""
    return TestClient(app)


@pytest.fixture
def seeded_parent_conv():
    """Creates a multi-turn parent conversation and cleans up both parent and any spawned branches on teardown."""
    created_ids: list[str] = []
    parent_id = create_conversation(title="Distributed SQLite Architecture")
    created_ids.append(parent_id)

    m1 = log_message(
        role="user",
        content="Let's design the SQLite schema for conversation threads and messages.",
        conversation_id=parent_id,
    )
    m2 = log_message(
        role="assistant",
        content="We should use a `conversations` table and a `messages` table with foreign key cascade.",
        agent="nexus",
        conversation_id=parent_id,
    )
    m3 = log_message(
        role="user",
        content="Now how should we handle DAG conversation branching and context slicing?",
        conversation_id=parent_id,
    )
    m4 = log_message(
        role="assistant",
        content="We can model each branch as an isolated stack frame with `parent_conversation_id` and `parent_message_id`.",
        agent="nexus",
        conversation_id=parent_id,
    )

    try:
        yield {
            "parent_id": parent_id,
            "message_ids": [m1, m2, m3, m4],
            "created_ids": created_ids,
        }
    finally:
        for cid in created_ids:
            rollback_checkpoints_for_thread(cid)
            delete_conversation(cid)


def test_full_history_fork_at_intermediate_turn(client, seeded_parent_conv):
    """Verify `branch_mode='fork'` at Turn 1 (`m2`) clones only messages m1..m2 and records DAG lineage."""
    parent_id = seeded_parent_conv["parent_id"]
    m1, m2, _, _ = seeded_parent_conv["message_ids"]

    res = client.post(
        f"/api/agents/ask/conversations/{parent_id}/branch",
        json={
            "parent_message_id": m2,
            "branch_mode": "fork",
            "title": "Schema Indexing Spike",
        },
    )
    assert res.status_code == 200
    data = res.json()

    child_id = data["conversation_id"]
    seeded_parent_conv["created_ids"].append(child_id)

    assert data["parent_conversation_id"] == parent_id
    assert data["parent_message_id"] == m2
    assert data["branch_mode"] == "fork"
    assert data["conversation"]["title"] == "🌿 Schema Indexing Spike"

    # Child history should contain exactly the first 2 messages (up to m2)
    child_history = get_chat_history(child_id)
    assert len(child_history) == 2
    assert child_history[0]["content"] == "Let's design the SQLite schema for conversation threads and messages."
    assert child_history[1]["content"] == "We should use a `conversations` table and a `messages` table with foreign key cascade."
    assert child_history[0]["id"] != m1  # Isolated row IDs in child partition


def test_tangent_branch_with_proportional_parent_brief(client, seeded_parent_conv):
    """Verify `branch_mode='tangent'` at Turn 2 (`m4`) synthesizes a proportional Parent Context Brief + preserves focal turn."""
    parent_id = seeded_parent_conv["parent_id"]
    _, _, _, m4 = seeded_parent_conv["message_ids"]

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content=(
            "- Established `conversations` and `messages` tables in SQLite `chats.db`.\n"
            "- Enforced foreign key cascade and chronological ordering."
        )
    )

    with patch("nexus.core.chat_branching.get_chat_model", return_value=mock_llm):
        res = client.post(
            f"/api/agents/ask/conversations/{parent_id}/branch",
            json={
                "parent_message_id": m4,
                "branch_mode": "tangent",
            },
        )

    assert res.status_code == 200
    data = res.json()
    child_id = data["conversation_id"]
    seeded_parent_conv["created_ids"].append(child_id)

    assert data["branch_mode"] == "tangent"
    assert data["parent_conversation_id"] == parent_id
    assert data["parent_message_id"] == m4

    # Child history should have: [0] Parent Context Brief (`branch_context`), [1] focal user msg (m3), [2] focal assistant msg (m4)
    child_history = get_chat_history(child_id)
    assert len(child_history) == 3
    assert child_history[0]["agent"] == "branch_context"
    assert "Parent Context Brief" in child_history[0]["content"]
    assert "Established `conversations` and `messages` tables" in child_history[0]["content"]
    assert child_history[1]["role"] == "user"
    assert "DAG conversation branching" in child_history[1]["content"]
    assert child_history[2]["role"] == "assistant"
    assert "isolated stack frame" in child_history[2]["content"]


def test_distill_and_merge_branch_to_parent(client, seeded_parent_conv):
    """Verify `POST /api/agents/ask/conversations/{id}/merge` distills branch findings and injects them into parent."""
    parent_id = seeded_parent_conv["parent_id"]
    _, _, _, m4 = seeded_parent_conv["message_ids"]

    # 1. Create a fork branch
    branch_res = client.post(
        f"/api/agents/ask/conversations/{parent_id}/branch",
        json={"parent_message_id": m4, "branch_mode": "fork", "title": "Merge Protocol Design"},
    )
    assert branch_res.status_code == 200
    branch_id = branch_res.json()["conversation_id"]
    seeded_parent_conv["created_ids"].append(branch_id)

    # 2. Simulate work inside the child branch
    log_message(
        role="user",
        content="How should we merge the branch conclusions back into the parent thread?",
        conversation_id=branch_id,
    )
    log_message(
        role="assistant",
        content="Synthesize a proportional distillation and append it to the parent conversation + LangGraph checkpointer.",
        agent="nexus",
        conversation_id=branch_id,
    )

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content=(
            "#### Key Decisions\n"
            "- Implemented `distill_and_merge_branch` in `src/nexus/core/chat_branching.py`.\n"
            "- Synchronized both `chats.db` and `memory.sqlite` (`nexus_graph.update_state`)."
        )
    )

    with patch("nexus.core.chat_branching.get_chat_model", return_value=mock_llm):
        merge_res = client.post(
            f"/api/agents/ask/conversations/{branch_id}/merge",
            json={"guidance": "Include exact module names and checkpointer synchronization details."},
        )

    assert merge_res.status_code == 200
    merge_data = merge_res.json()
    assert merge_data["status"] == "merged"
    assert merge_data["parent_conversation_id"] == parent_id
    assert merge_data["branch_conversation_id"] == branch_id
    assert merge_data["merged_at"] is not None

    # Verify child branch row has `merged_at` populated
    updated_branch = get_conversation(branch_id)
    assert updated_branch is not None
    assert updated_branch["merged_at"] == merge_data["merged_at"]

    # Verify parent conversation history now ends with the injected `branch_merge` message
    parent_history = get_chat_history(parent_id)
    assert len(parent_history) == 5
    last_msg = parent_history[-1]
    assert last_msg["role"] == "assistant"
    assert last_msg["agent"] == "branch_merge"
    assert "Distilled Merge from Branch" in last_msg["content"]
    assert "distill_and_merge_branch" in last_msg["content"]


def test_delete_parent_promotes_child_branch_to_root(client, seeded_parent_conv):
    """Verify deleting a parent conversation promotes its child branches to root (`parent_conversation_id = None`)."""
    parent_id = seeded_parent_conv["parent_id"]
    m1 = seeded_parent_conv["message_ids"][0]

    branch_res = client.post(
        f"/api/agents/ask/conversations/{parent_id}/branch",
        json={"parent_message_id": m1, "branch_mode": "fork"},
    )
    assert branch_res.status_code == 200
    branch_id = branch_res.json()["conversation_id"]
    seeded_parent_conv["created_ids"].append(branch_id)

    # Delete parent conversation
    delete_conversation(parent_id)

    # Child branch must still exist and have `parent_conversation_id` set to None
    child_conv = get_conversation(branch_id)
    assert child_conv is not None
    assert child_conv["parent_conversation_id"] is None


def test_tangent_branch_on_first_turn_skips_redundant_brief(client, seeded_parent_conv):
    """Verify `branch_mode='tangent'` on Turn 1 (`m2`, no prior turns) copies Turn 1 directly without LLM brief call."""
    parent_id = seeded_parent_conv["parent_id"]
    _, m2, _, _ = seeded_parent_conv["message_ids"]

    res = client.post(
        f"/api/agents/ask/conversations/{parent_id}/branch",
        json={"parent_message_id": m2, "branch_mode": "tangent"},
    )
    assert res.status_code == 200
    data = res.json()
    child_id = data["conversation_id"]
    seeded_parent_conv["created_ids"].append(child_id)

    child_history = get_chat_history(child_id)
    assert len(child_history) == 2
    assert child_history[0]["role"] == "user"
    assert child_history[1]["role"] == "assistant"
    assert all(m["agent"] != "branch_context" for m in child_history)


def test_branch_and_merge_error_guards(client, seeded_parent_conv):
    """Verify 404 on non-existent conversation branch and 400 when attempting to merge a root conversation."""
    res_404 = client.post(
        "/api/agents/ask/conversations/non-existent-conv-id/branch",
        json={"branch_mode": "tangent"},
    )
    assert res_404.status_code == 404

    parent_id = seeded_parent_conv["parent_id"]
    res_root_merge = client.post(
        f"/api/agents/ask/conversations/{parent_id}/merge",
        json={},
    )
    assert res_root_merge.status_code == 400
    assert "root conversation" in res_root_merge.json()["detail"]
