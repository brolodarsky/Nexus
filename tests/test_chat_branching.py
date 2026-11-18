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
from langchain_core.messages import AIMessage, HumanMessage

from nexus.api.main import app
from nexus.agent.graph import CORE_TOOLS, TOOLS, nexus_graph, rollback_checkpoints_for_thread
from nexus.core.chat_branching import spawn_seeded_conversation
from nexus.core.hitl_queue import reset_hitl_execution_context, set_hitl_execution_context
from nexus.shared_tools.shared import spawn_conversation
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


def test_spawn_seeded_conversation_nested_under_parent(seeded_parent_conv):
    """Verify `spawn_seeded_conversation(nest_under_parent=True)` nests under parent, preserves manual title, and seeds memory.sqlite."""
    parent_id = seeded_parent_conv["parent_id"]
    _, _, _, m4 = seeded_parent_conv["message_ids"]

    result = spawn_seeded_conversation(
        title="Taxes & CPA Follow-ups",
        context_brief="Exact Gmail thread_id: `18f4a9c`, sender: cpa@firm.example, action: review W-2 discrepancy.",
        parent_conversation_id=parent_id,
        nest_under_parent=True,
    )
    child_id = result["conversation_id"]
    seeded_parent_conv["created_ids"].append(child_id)

    assert result["parent_conversation_id"] == parent_id
    assert result["parent_message_id"] == m4
    assert result["branch_mode"] == "tangent"
    assert result["title"] == "🌿 Taxes & CPA Follow-ups"

    conv = get_conversation(child_id)
    assert conv is not None
    assert conv["parent_conversation_id"] == parent_id
    assert conv["parent_message_id"] == m4
    assert conv["branch_mode"] == "tangent"
    assert conv["title_source"] == "manual"

    history = get_chat_history(child_id)
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["agent"] == "branch_context"
    assert "Context Brief" in history[0]["content"]
    assert "18f4a9c" in history[0]["content"]

    # Verify LangGraph SqliteSaver checkpoint was hydrated with HumanMessage anchor + AIMessage brief
    lg_state = nexus_graph.get_state({"configurable": {"thread_id": child_id, "conversation_id": child_id}})
    seeded_msgs = lg_state.values.get("messages", [])
    assert len(seeded_msgs) == 2
    assert isinstance(seeded_msgs[0], HumanMessage)
    assert isinstance(seeded_msgs[1], AIMessage)
    assert "18f4a9c" in seeded_msgs[1].content


def test_spawn_seeded_conversation_standalone_root(seeded_parent_conv):
    """Verify `spawn_seeded_conversation(nest_under_parent=False)` creates an unnested root thread with manual title provenance."""
    parent_id = seeded_parent_conv["parent_id"]

    result = spawn_seeded_conversation(
        title="Ongoing House Remodel Project",
        context_brief="Contractor quotes and permit links gathered during inbox sweep.",
        parent_conversation_id=parent_id,
        nest_under_parent=False,
    )
    root_id = result["conversation_id"]
    seeded_parent_conv["created_ids"].append(root_id)

    assert result["parent_conversation_id"] is None
    assert result["parent_message_id"] is None
    assert result["branch_mode"] is None
    assert result["title"] == "Ongoing House Remodel Project"

    conv = get_conversation(root_id)
    assert conv is not None
    assert conv["parent_conversation_id"] is None
    assert conv["branch_mode"] is None
    assert conv["title_source"] == "manual"

    lg_state = nexus_graph.get_state({"configurable": {"thread_id": root_id, "conversation_id": root_id}})
    seeded_msgs = lg_state.values.get("messages", [])
    assert len(seeded_msgs) == 2
    assert isinstance(seeded_msgs[0], HumanMessage)
    assert isinstance(seeded_msgs[1], AIMessage)
    assert "Contractor quotes" in seeded_msgs[1].content


def test_spawn_conversation_tool_from_parent_and_subagent_context(seeded_parent_conv):
    """Verify `spawn_conversation` is bound in both `CORE_TOOLS` and `TOOLS`, and inherits parent `conversation_id` inside subagent context."""
    core_names = {t.name for t in CORE_TOOLS}
    parent_names = {t.name for t in TOOLS}
    assert "spawn_conversation" in core_names
    assert "spawn_conversation" in parent_names

    parent_id = seeded_parent_conv["parent_id"]

    # Simulate execution inside a spawned subagent worker whose `thread_id` is scoped to `:subagent-1`
    # while `conversation_id` points to the active parent UI thread
    sub_token = set_hitl_execution_context(
        conversation_id=parent_id,
        thread_id=f"{parent_id}:subagent-1",
        agent_id="subagent-1",
        agent_role="Subagent #1 (low)",
    )
    try:
        receipt = spawn_conversation.invoke(
            {
                "title": "Recruiter Thread — Acme Corp",
                "context_brief": "Thread ID `abc-999` from jane@acme.example requesting Thursday interview slots.",
                "nest_under_current": True,
            }
        )
    finally:
        reset_hitl_execution_context(sub_token)

    assert "🌿 Recruiter Thread — Acme Corp" in receipt
    assert parent_id in receipt

    # Locate the newly created branch in `chats.db` and register for teardown cleanup
    all_convs = chats_db.get_conversations()
    spawned_nested = [c for c in all_convs if c.get("parent_conversation_id") == parent_id]
    assert len(spawned_nested) == 1
    seeded_parent_conv["created_ids"].append(spawned_nested[0]["id"])
    assert spawned_nested[0]["id"] in receipt

    # Verify fallback to standalone root conversation when running under synthetic `"nexus_primary"` CLI/eval context
    cli_token = set_hitl_execution_context(
        conversation_id="nexus_primary",
        thread_id="nexus_primary",
        agent_id="nexus",
        agent_role="Head Agent",
    )
    try:
        cli_receipt = spawn_conversation.invoke(
            {
                "title": "CLI Standalone Thread",
                "context_brief": "Seeded from headless CLI run.",
                "nest_under_current": True,
            }
        )
    finally:
        reset_hitl_execution_context(cli_token)

    assert "standalone root conversation" in cli_receipt
    cli_matches = [c for c in chats_db.get_conversations() if c.get("title") == "CLI Standalone Thread"]
    assert len(cli_matches) == 1
    seeded_parent_conv["created_ids"].append(cli_matches[0]["id"])
    assert cli_matches[0]["parent_conversation_id"] is None


def test_spawn_conversation_target_section_and_broken_path_lint_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seeded_parent_conv,
):
    """Verify Tune-Up B: `target_section` snapshot, broken path/wiki-link warnings, and explicit handoff header."""
    import nexus.shared_tools.vault_reader as vault_reader_mod
    import nexus.shared_tools.shared as shared_mod

    # Build an isolated temporary Vault fixture so tests never depend on personal Vault contents
    fake_vault = tmp_path / "Vault"
    career_dir = fake_vault / "3. Operations" / "3.1. Career Strategy & Revenue"
    eng_dir = fake_vault / "6. Engineering"
    career_dir.mkdir(parents=True)
    eng_dir.mkdir(parents=True)

    (career_dir / "Section Instructions.md").write_text("# Career Rules", encoding="utf-8")
    (career_dir / "Resume - Master.md").write_text("# Master Resume\nBS in CS", encoding="utf-8")
    (career_dir / "Job Hunt War Room.md").write_text("# War Room", encoding="utf-8")
    (eng_dir / "Log.md").write_text("---\naliases: [Engineering Log]\n---\n# Log", encoding="utf-8")

    monkeypatch.setattr(vault_reader_mod, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(shared_mod, "VAULT_PATH", fake_vault)

    parent_id = seeded_parent_conv["parent_id"]
    ctx_token = set_hitl_execution_context(
        conversation_id=parent_id,
        thread_id=parent_id,
        agent_id="nexus",
        agent_role="Head Agent",
    )
    try:
        # 1. Phantom filenames + missing wiki-link trigger deterministic [SYSTEM WARNING] on both brief and receipt
        bad_receipt = spawn_conversation.invoke(
            {
                "title": "Job Sprint — Bad Refs",
                "context_brief": (
                    "Review [[Job Hunt War Room]], [[Engineering Log]], and [[Nonexistent Mission]].\n"
                    "Use Resume - Applied AI & Forward Deployed Engineer.md and `Offer.docx`, "
                    "plus 6. Engineering/Resume - Master.md (wrong folder). "
                    "Ignore external https://example.com/guide.pdf and template Mission - *.md."
                ),
                "nest_under_current": True,
                "target_section": "3. Operations/3.1. Career Strategy & Revenue",
            }
        )
    finally:
        reset_hitl_execution_context(ctx_token)

    assert "[SYSTEM WARNING:" in bad_receipt
    assert "Nonexistent Mission" in bad_receipt
    assert "Resume - Applied AI & Forward Deployed Engineer.md" in bad_receipt
    assert "Offer.docx" in bad_receipt
    assert "6. Engineering/Resume - Master.md" in bad_receipt
    # Real on-disk notes, frontmatter aliases, external URLs, and glob templates must NOT trigger false positives
    assert "Job Hunt War Room" not in bad_receipt.split("[SYSTEM WARNING:")[1]
    assert "Engineering Log" not in bad_receipt.split("[SYSTEM WARNING:")[1]
    assert "guide.pdf" not in bad_receipt
    assert "Mission - *.md" not in bad_receipt

    nested_convs = [c for c in chats_db.get_conversations() if c.get("parent_conversation_id") == parent_id]
    assert len(nested_convs) == 1
    bad_child_id = nested_convs[0]["id"]
    seeded_parent_conv["created_ids"].append(bad_child_id)

    # Verify target_section live snapshot + warning are persisted in chats.db AND LangGraph memory.sqlite
    history = get_chat_history(bad_child_id)
    assert len(history) == 1
    brief_content = history[0]["content"]
    assert "Target Section Directory Snapshot (`3. Operations/3.1. Career Strategy & Revenue`)" in brief_content
    assert "Resume - Master.md" in brief_content
    assert "Section Instructions.md" in brief_content
    assert "[SYSTEM WARNING:" in brief_content

    lg_state = nexus_graph.get_state({"configurable": {"thread_id": bad_child_id, "conversation_id": bad_child_id}})
    seeded_msgs = lg_state.values.get("messages", [])
    assert len(seeded_msgs) == 2
    assert isinstance(seeded_msgs[0], HumanMessage)
    assert (
        seeded_msgs[0].content
        == "[Session initialized from parent conversation branch context — Note: Section Instructions and living notes are NOT yet loaded in this thread. Hydrate target section files from disk before mutating state or delegating.]"
    )
    assert isinstance(seeded_msgs[1], AIMessage)
    assert "Resume - Master.md" in seeded_msgs[1].content
    assert "[SYSTEM WARNING:" in seeded_msgs[1].content

    # 2. Valid brief with real files produces zero [SYSTEM WARNING]
    ctx_token = set_hitl_execution_context(conversation_id=parent_id, thread_id=parent_id)
    try:
        clean_receipt = spawn_conversation.invoke(
            {
                "title": "Job Sprint — Verified Refs",
                "context_brief": (
                    "Hydrate [[Job Hunt War Room|War Room]], [[Engineering Log]], "
                    "and `3. Operations/3.1. Career Strategy & Revenue/Resume - Master.md`."
                ),
                "nest_under_current": True,
                "target_section": "Vault/3. Operations/3.1. Career Strategy & Revenue",
            }
        )
    finally:
        reset_hitl_execution_context(ctx_token)

    assert "[SYSTEM WARNING:" not in clean_receipt
    clean_convs = [c for c in chats_db.get_conversations() if c.get("title") == "🌿 Job Sprint — Verified Refs"]
    assert len(clean_convs) == 1
    seeded_parent_conv["created_ids"].append(clean_convs[0]["id"])
