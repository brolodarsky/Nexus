"""Tests for HITL commit integrity: stale-base detection, pre-commit snapshots, rollback, and rebase.

Every test runs against an isolated temp project root + temp `hitl.db`, so the real Vault is never touched.
"""
from pathlib import Path

import pytest
# TestClient: Starlette/FastAPI in-process HTTP client; exercises routes without starting uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.core import hitl_queue as hq


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp project root with an empty `Vault/` and a fresh `hitl.db` (DB_PATH is read at call time)."""
    (tmp_path / "Vault").mkdir()
    monkeypatch.setattr(hq, "DB_PATH", tmp_path / "hitl.db")
    hq.init_db()
    return tmp_path


def _write(root: Path, rel: str, text: str) -> Path:
    # newline="": Writes bytes exactly as given (no Windows LF->CRLF translation) so assertions are byte-precise
    path = root / "Vault" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def _read(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _stage(rel: str, original, proposed: str) -> int:
    return hq.add_transaction(
        agent_name="nexus_agent",
        action_type="modify" if original is not None else "create",
        target_file=f"Vault/{rel}",
        original_content=original,
        proposed_content=proposed,
        reasoning="test",
    )


# ── commit_transaction ─────────────────────────────────────────────────────


def test_commit_clean_writes_and_snapshots(root: Path):
    path = _write(root, "Note.md", "a\nb\n")
    tx_id = _stage("Note.md", "a\nb\n", "a\nb\nc\n")

    result = hq.commit_transaction(tx_id, root)

    assert _read(path) == "a\nb\nc\n"
    assert hq.get_transaction(tx_id)["status"] == "approved"
    assert result["forced"] is False
    assert hq.get_recent_revisions()[0]["tx_id"] == tx_id


def test_commit_refuses_when_human_edited_after_staging(root: Path):
    path = _write(root, "Note.md", "a\nb\n")
    tx_id = _stage("Note.md", "a\nb\n", "a\nb\nagent\n")
    _write(root, "Note.md", "a\nb\nhuman\n")  # Human edits in Obsidian while the card sits in the queue

    with pytest.raises(hq.StaleBaseError) as exc:
        hq.commit_transaction(tx_id, root)

    assert exc.value.current_content == "a\nb\nhuman\n"
    assert _read(path) == "a\nb\nhuman\n"  # Human edit survives
    assert hq.get_transaction(tx_id)["status"] == "pending"
    assert hq.get_recent_revisions() == []  # No snapshot row left behind


def test_commit_ignores_crlf_only_differences(root: Path):
    _write(root, "Note.md", "a\r\nb\r\n")
    tx_id = _stage("Note.md", "a\nb\n", "a\nb\nc\n")
    hq.commit_transaction(tx_id, root)  # Must not raise StaleBaseError


def test_commit_detects_deleted_note(root: Path):
    path = _write(root, "Note.md", "a\n")
    tx_id = _stage("Note.md", "a\n", "a\nb\n")
    path.unlink()

    with pytest.raises(hq.StaleBaseError, match="deleted"):
        hq.commit_transaction(tx_id, root)


def test_commit_detects_create_collision(root: Path):
    tx_id = _stage("New.md", None, "agent\n")
    _write(root, "New.md", "human\n")

    with pytest.raises(hq.StaleBaseError, match="created"):
        hq.commit_transaction(tx_id, root)


def test_force_commit_overwrites_but_keeps_snapshot(root: Path):
    path = _write(root, "Note.md", "a\n")
    tx_id = _stage("Note.md", "a\n", "agent\n")
    _write(root, "Note.md", "human\n")

    result = hq.commit_transaction(tx_id, root, force=True)

    assert result["forced"] is True
    assert _read(path) == "agent\n"
    hq.rollback_transaction(tx_id, root)
    assert _read(path) == "human\n"  # Forced overwrite is still recoverable


def test_commit_rejects_path_traversal(root: Path):
    tx_id = _stage("../escape.md", None, "x")
    with pytest.raises(hq.HitlCommitError, match="outside the Vault"):
        hq.commit_transaction(tx_id, root)
    assert not (root / "escape.md").exists()


def test_commit_rejects_non_pending(root: Path):
    _write(root, "Note.md", "a\n")
    tx_id = _stage("Note.md", "a\n", "b\n")
    hq.commit_transaction(tx_id, root)
    with pytest.raises(hq.HitlCommitError, match="not pending"):
        hq.commit_transaction(tx_id, root)


def test_commit_unknown_tx(root: Path):
    with pytest.raises(hq.TransactionNotFoundError):
        hq.commit_transaction(9999, root)


# ── rollback_transaction ───────────────────────────────────────────────────


def test_rollback_restores_byte_identical_prior(root: Path):
    original = "line 1\r\nline 2\r\n"  # CRLF on disk must survive the round-trip exactly
    path = _write(root, "Note.md", original)
    tx_id = _stage("Note.md", "line 1\nline 2\n", "line 1\nline 2\nline 3\n")

    hq.commit_transaction(tx_id, root)
    hq.rollback_transaction(tx_id, root)

    assert path.read_bytes() == original.encode("utf-8")
    assert hq.get_transaction(tx_id)["status"] == "rolled_back"
    assert hq.get_recent_revisions()[0]["rolled_back"] == 1


def test_rollback_of_create_deletes_file(root: Path):
    tx_id = _stage("Fresh.md", None, "hello\n")
    hq.commit_transaction(tx_id, root)
    assert (root / "Vault" / "Fresh.md").exists()

    hq.rollback_transaction(tx_id, root)
    assert not (root / "Vault" / "Fresh.md").exists()


def test_rollback_refuses_if_edited_after_approval(root: Path):
    path = _write(root, "Note.md", "a\n")
    tx_id = _stage("Note.md", "a\n", "a\nagent\n")
    hq.commit_transaction(tx_id, root)
    _write(root, "Note.md", "a\nagent\nhuman later\n")

    with pytest.raises(hq.StaleBaseError):
        hq.rollback_transaction(tx_id, root)
    assert _read(path) == "a\nagent\nhuman later\n"


def test_rollback_twice_fails(root: Path):
    _write(root, "Note.md", "a\n")
    tx_id = _stage("Note.md", "a\n", "b\n")
    hq.commit_transaction(tx_id, root)
    hq.rollback_transaction(tx_id, root)
    with pytest.raises(hq.HitlCommitError, match="no applied revision"):
        hq.rollback_transaction(tx_id, root)


# ── three_way_merge & rebase_transaction ───────────────────────────────────


def test_merge_non_overlapping_edits():
    base = "1\n2\n3\n4\n5\n"
    ours = "1 human\n2\n3\n4\n5\n"
    theirs = "1\n2\n3\n4\n5 agent\n"
    assert hq.three_way_merge(base, ours, theirs) == "1 human\n2\n3\n4\n5 agent\n"


def test_merge_overlapping_edits_conflict():
    base = "1\n2\n3\n"
    assert hq.three_way_merge(base, "1\nhuman\n3\n", "1\nagent\n3\n") is None


def test_merge_identical_edits_apply_once():
    base = "1\n2\n"
    both = "1\n2\nsame\n"
    assert hq.three_way_merge(base, both, both) == both


def test_rebase_then_commit_preserves_both_edits(root: Path):
    path = _write(root, "Note.md", "# Title\n\nalpha\n\nbeta\n\ngamma\n")
    tx_id = _stage("Note.md", "# Title\n\nalpha\n\nbeta\n\ngamma\n", "# Title\n\nalpha\n\nbeta\n\ngamma\n\n- agent task\n")
    _write(root, "Note.md", "# Title (edited)\n\nalpha\n\nbeta\n\ngamma\n")

    assert hq.rebase_transaction(tx_id, root)["rebased"] is True
    hq.commit_transaction(tx_id, root)

    assert _read(path) == "# Title (edited)\n\nalpha\n\nbeta\n\ngamma\n\n- agent task\n"


def test_rebase_conflict_raises(root: Path):
    _write(root, "Note.md", "a\nb\nc\n")
    tx_id = _stage("Note.md", "a\nb\nc\n", "a\nagent\nc\n")
    _write(root, "Note.md", "a\nhuman\nc\n")

    with pytest.raises(hq.MergeConflictError):
        hq.rebase_transaction(tx_id, root)
    assert hq.get_transaction(tx_id)["proposed_content"] == "a\nagent\nc\n"  # Card untouched on failure


# ── HTTP layer (status-code contract the GUI relies on) ────────────────────


@pytest.fixture
def client(root: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from nexus.api.routers import hitl as hitl_router

    monkeypatch.setattr(hitl_router, "PROJECT_ROOT", root)
    app = FastAPI()
    app.include_router(hitl_router.router, prefix="/api/hitl")
    return TestClient(app)


def test_api_stale_approve_returns_409_with_current_content(root: Path, client: TestClient):
    _write(root, "Note.md", "a\n")
    tx_id = _stage("Note.md", "a\n", "agent\n")
    _write(root, "Note.md", "human\n")

    res = client.post(f"/api/hitl/{tx_id}/approve")
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "stale_base"
    assert detail["current_content"] == "human\n"

    res = client.post(f"/api/hitl/{tx_id}/approve", params={"force": "true"})
    assert res.status_code == 200 and res.json()["forced"] is True


def test_api_rollback_and_recent(root: Path, client: TestClient):
    _write(root, "Note.md", "a\n")
    tx_id = _stage("Note.md", "a\n", "b\n")
    assert client.post(f"/api/hitl/{tx_id}/approve").status_code == 200

    recent = client.get("/api/hitl/revisions/recent").json()
    assert recent[0]["tx_id"] == tx_id and recent[0]["rolled_back"] == 0

    assert client.post(f"/api/hitl/{tx_id}/rollback").status_code == 200
    assert _read(root / "Vault" / "Note.md") == "a\n"
    assert client.post("/api/hitl/9999/approve").status_code == 404


# ── Concurrency & Cumulative Overlay Stacking ───────────────────────────────


def test_concurrent_modify_file_stacks_cleanly_into_single_transaction(root: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that concurrent tool calls targeting the same note serialize cleanly via get_file_mutation_lock.

    When an agent emits multiple tool calls in a single turn (e.g. LangGraph ToolNode parallel execution),
    both threads must stack sequentially onto a single review card rather than creating competing sibling
    transactions with stale baselines.
    """
    import concurrent.futures
    import nexus.shared_tools.shared as shared_module
    import nexus.shared_tools.vault_reader as vr_module

    vault = root / "Vault"
    monkeypatch.setattr(shared_module, "VAULT_PATH", vault)
    monkeypatch.setattr(vr_module, "VAULT_PATH", vault)

    # 1. Establish the note on disk with two disjoint sections
    initial_text = "Header\n\nTask 1: Pending\n\nMiddle Section\n\nTask 2: Pending\n\nFooter\n"
    _write(root, "ConcurrentNote.md", initial_text)

    # 2. Define two concurrent worker tasks that would race in an un-locked environment
    def worker1():
        return shared_module.modify_file.invoke({
            "file_path": "ConcurrentNote.md",
            "target": "Task 1: Pending",
            "replacement": "Task 1: Done",
            "reasoning": "Completed task 1",
        })

    def worker2():
        return shared_module.modify_file.invoke({
            "file_path": "ConcurrentNote.md",
            "target": "Task 2: Pending",
            "replacement": "Task 2: In Progress",
            "reasoning": "Started task 2",
        })

    # 3. Execute both workers in parallel across distinct threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker1)
        f2 = executor.submit(worker2)
        r1 = f1.result()
        r2 = f2.result()

    # 4. Exactly one worker stages the card, the second stacks onto it
    results = [r1, r2]
    assert any("staged to HITL queue" in r for r in results)
    assert any("stacked onto existing pending HITL Transaction" in r for r in results)

    # 5. Exactly ONE pending transaction must exist for this file
    pending = hq.get_pending_transactions()
    target_pending = [p for p in pending if p["target_file"] == "Vault/ConcurrentNote.md"]
    assert len(target_pending) == 1

    tx = target_pending[0]
    # The proposal must include BOTH edits
    assert "Task 1: Done" in tx["proposed_content"]
    assert "Task 2: In Progress" in tx["proposed_content"]
    # The reasoning must merge both explanations
    assert "Completed task 1" in tx["reasoning"]
    assert "Started task 2" in tx["reasoning"]
    # Baseline matches original disk text
    assert tx["original_content"] == initial_text

    # 6. Approving the stacked card must succeed cleanly without stale-base error
    commit_res = hq.commit_transaction(tx["id"], root)
    assert commit_res["forced"] is False
    assert _read(vault / "ConcurrentNote.md") == "Header\n\nTask 1: Done\n\nMiddle Section\n\nTask 2: In Progress\n\nFooter\n"


def test_hitl_execution_context_provenance_propagation_and_api(root: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Verifies that conversation_id, thread_id, agent_id, and agent_role propagate through ContextVar into hitl.db and HTTP responses."""
    import nexus.shared_tools.shared as shared_module
    import nexus.shared_tools.vault_reader as vr_module

    vault = root / "Vault"
    monkeypatch.setattr(shared_module, "VAULT_PATH", vault)
    monkeypatch.setattr(vr_module, "VAULT_PATH", vault)

    _write(root, "ProvenanceNote.md", "Initial line\n")

    # 1. Set parent Commander context
    parent_token = hq.set_hitl_execution_context(
        conversation_id="6419ce02-64e7-4da3-a61e-0d78bec044a9",
        thread_id="6419ce02-64e7-4da3-a61e-0d78bec044a9",
        agent_id="nexus",
        agent_role="Commander (strong)",
    )
    try:
        # 2. Simulate nested subagent context override
        sub_token = hq.set_hitl_execution_context(
            conversation_id="6419ce02-64e7-4da3-a61e-0d78bec044a9",
            thread_id="6419ce02-64e7-4da3-a61e-0d78bec044a9:subagent-1",
            agent_id="subagent-1",
            agent_role="Subagent #1 (low)",
        )
        try:
            shared_module.modify_file.invoke({
                "file_path": "ProvenanceNote.md",
                "target": "Initial line",
                "replacement": "Subagent edited line",
                "reasoning": "Subagent provenance check",
            })
        finally:
            hq.reset_hitl_execution_context(sub_token)

        # Verify parent context was restored cleanly after subagent exit
        restored = hq.get_hitl_execution_context()
        assert restored["agent_id"] == "nexus"
        assert restored["agent_role"] == "Commander (strong)"
        assert restored["thread_id"] == "6419ce02-64e7-4da3-a61e-0d78bec044a9"
    finally:
        hq.reset_hitl_execution_context(parent_token)

    # 3. Verify FastAPI /api/hitl/pending returns all 4 provenance fields
    pending_res = client.get("/api/hitl/pending")
    assert pending_res.status_code == 200
    pending_list = pending_res.json()
    assert len(pending_list) == 1
    card = pending_list[0]
    assert card["conversation_id"] == "6419ce02-64e7-4da3-a61e-0d78bec044a9"
    assert card["thread_id"] == "6419ce02-64e7-4da3-a61e-0d78bec044a9:subagent-1"
    assert card["agent_id"] == "subagent-1"
    assert card["agent_role"] == "Subagent #1 (low)"
    assert card["agent_name"] == "Subagent #1 (low)"

    # 4. Approve and verify /api/hitl/revisions/recent also preserves provenance
    approve_res = client.post(f"/api/hitl/{card['id']}/approve")
    assert approve_res.status_code == 200
    revs = client.get("/api/hitl/revisions/recent").json()
    assert revs[0]["conversation_id"] == "6419ce02-64e7-4da3-a61e-0d78bec044a9"
    assert revs[0]["thread_id"] == "6419ce02-64e7-4da3-a61e-0d78bec044a9:subagent-1"
    assert revs[0]["agent_id"] == "subagent-1"
    assert revs[0]["agent_role"] == "Subagent #1 (low)"


# ── Atomic File Move & Delete Support in HITL ───────────────────────────────


def test_commit_and_rollback_file_deletion(root: Path):
    """Verifies that staging action_type='delete' unlinks the file on commit and restores it on rollback."""
    initial_text = "# Obsolete Note\n\nOld content that should be pruned.\n"
    path = _write(root, "TrashNote.md", initial_text)

    # 1. Stage deletion transaction
    tx_id = hq.add_transaction(
        agent_name="nexus_agent",
        action_type="delete",
        target_file="Vault/TrashNote.md",
        proposed_content="",
        original_content=initial_text,
        reasoning="Pruning obsolete note",
    )

    # 2. Approve and commit deletion
    result = hq.commit_transaction(tx_id, root)
    assert not path.exists()
    assert hq.get_transaction(tx_id)["status"] == "approved"
    assert result["forced"] is False

    # 3. Rollback deletion and verify exact restoration
    rollback_res = hq.rollback_transaction(tx_id, root)
    assert path.exists()
    assert _read(path) == initial_text
    assert hq.get_transaction(tx_id)["status"] == "rolled_back"
    assert rollback_res["forced"] is False


def test_commit_delete_refuses_when_human_edited(root: Path):
    """Verifies that approving a staged deletion refuses if the note was edited on disk in Obsidian."""
    path = _write(root, "ActiveNote.md", "Original text\n")
    tx_id = hq.add_transaction(
        agent_name="nexus_agent",
        action_type="delete",
        target_file="Vault/ActiveNote.md",
        proposed_content="",
        original_content="Original text\n",
        reasoning="Delete note",
    )
    # Human edits note on disk
    _write(root, "ActiveNote.md", "Original text\nHuman added important thought\n")

    with pytest.raises(hq.StaleBaseError) as exc:
        hq.commit_transaction(tx_id, root)
    assert "edited on disk" in str(exc.value)
    assert path.exists()
    assert "Human added important thought" in _read(path)

    # Force commit overrides human edits but preserves snapshot
    hq.commit_transaction(tx_id, root, force=True)
    assert not path.exists()
    hq.rollback_transaction(tx_id, root)
    assert path.exists()
    assert "Human added important thought" in _read(path)


def test_rollback_delete_refuses_if_file_recreated(root: Path):
    """Verifies that rolling back a deletion refuses if a new note was created at the target path."""
    path = _write(root, "Recreated.md", "Old\n")
    tx_id = hq.add_transaction(
        agent_name="nexus_agent",
        action_type="delete",
        target_file="Vault/Recreated.md",
        proposed_content="",
        original_content="Old\n",
        reasoning="Delete",
    )
    hq.commit_transaction(tx_id, root)
    assert not path.exists()

    # Recreate note on disk
    _write(root, "Recreated.md", "Freshly created\n")

    with pytest.raises(hq.StaleBaseError, match="created at this path"):
        hq.rollback_transaction(tx_id, root)
    assert _read(path) == "Freshly created\n"

    # Forced rollback overwrites recreated note but preserves it
    hq.rollback_transaction(tx_id, root, force=True)
    assert _read(path) == "Old\n"


def test_commit_and_rollback_file_move(root: Path):
    """Verifies that atomic file moves relocate the note on commit and cleanly revert on rollback."""
    initial_text = "# Mission Note\n\nConcluded mission awaiting archival.\n"
    src_path = _write(root, "Missions/Acme.md", initial_text)
    dst_path = root / "Vault" / "Archive" / "2026" / "Acme.md"

    # 1. Stage move transaction with destination_file
    tx_id = hq.add_transaction(
        agent_name="nexus_agent",
        action_type="move",
        target_file="Vault/Missions/Acme.md",
        destination_file="Vault/Archive/2026/Acme.md",
        proposed_content=initial_text,
        original_content=initial_text,
        reasoning="Mission concluded, archiving to 2026",
    )

    # 2. Approve and commit move
    commit_res = hq.commit_transaction(tx_id, root)
    assert not src_path.exists()
    assert dst_path.exists()
    assert _read(dst_path) == initial_text
    assert hq.get_transaction(tx_id)["status"] == "approved"
    assert commit_res["destination_file"] == "Vault/Archive/2026/Acme.md"

    # 3. Rollback move: destination unlinked and source restored
    rollback_res = hq.rollback_transaction(tx_id, root)
    assert not dst_path.exists()
    assert src_path.exists()
    assert _read(src_path) == initial_text
    assert hq.get_transaction(tx_id)["status"] == "rolled_back"
    assert rollback_res["forced"] is False


def test_commit_move_refuses_when_source_edited_or_dest_exists(root: Path):
    """Verifies that committing a move detects source drift or destination collisions."""
    src_path = _write(root, "Source.md", "Initial\n")
    dst_path = _write(root, "Collision.md", "Existing dest\n")

    # Destination collision check
    tx_id = hq.add_transaction(
        agent_name="nexus_agent",
        action_type="move",
        target_file="Vault/Source.md",
        destination_file="Vault/Collision.md",
        proposed_content="Initial\n",
        original_content="Initial\n",
        reasoning="Move collision",
    )
    with pytest.raises(hq.StaleBaseError, match="destination"):
        hq.commit_transaction(tx_id, root)

    # Source drift check
    dst_path.unlink()  # Clear collision
    _write(root, "Source.md", "Initial\nHuman edits\n")
    with pytest.raises(hq.StaleBaseError, match="source note was edited"):
        hq.commit_transaction(tx_id, root)


def test_move_file_and_delete_file_tools(root: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies move_file and delete_file @tool functions in shared.py and graph.py integration."""
    import nexus.agent.graph as graph_module
    import nexus.shared_tools.shared as shared_module
    import nexus.shared_tools.vault_reader as vr_module

    vault = root / "Vault"
    monkeypatch.setattr(shared_module, "VAULT_PATH", vault)
    monkeypatch.setattr(vr_module, "VAULT_PATH", vault)

    # 1. Verify CORE_TOOLS includes move_file and delete_file
    core_tool_names = [t.name for t in graph_module.CORE_TOOLS]
    assert "move_file" in core_tool_names
    assert "delete_file" in core_tool_names

    # 2. Verify containment guards
    out_of_bounds = shared_module.move_file.invoke({
        "source_path": "Note.md",
        "destination_path": "../escape.md",
        "reasoning": "Escape test",
    })
    assert "Error: Refusing to move file outside the Vault" in out_of_bounds

    # 3. Verify identity move guard
    same_path = shared_module.move_file.invoke({
        "source_path": "Identical.md",
        "destination_path": "Identical.md",
        "reasoning": "Identity test",
    })
    assert "Error: Source and destination paths are identical" in same_path

    # 4. Stage legitimate move_file
    note_content = "# Active Pursuit\n\nTarget data.\n"
    _write(root, "Active.md", note_content)
    move_res = shared_module.move_file.invoke({
        "source_path": "Active.md",
        "destination_path": "Archive/2026/Active.md",
        "reasoning": "Archiving finished note",
    })
    assert "✅ File move staged to HITL queue" in move_res
    assert "Vault/Active.md" in move_res
    assert "Vault/Archive/2026/Active.md" in move_res

    # 5. Read staged move note via read_file
    staged_read = shared_module.read_file.invoke({"file_path": "Active.md"})
    assert "[STAGED TO MOVE IN HITL QUEUE" in staged_read
    assert "Target data." in staged_read

    # 6. Delete file tool
    del_note_text = "# Redundant File\n\nNo longer needed.\n"
    _write(root, "Redundant.md", del_note_text)
    del_res = shared_module.delete_file.invoke({
        "file_path": "Redundant.md",
        "reasoning": "Pruning redundant file",
    })
    assert "✅ File deletion staged to HITL queue" in del_res

    # Read staged delete note via read_file
    del_read = shared_module.read_file.invoke({"file_path": "Redundant.md"})
    assert "[STAGED FOR DELETION IN HITL QUEUE" in del_read
    assert "Redundant File" in del_read

    # 7. Discard pending create via delete_file
    shared_module.create_file.invoke({
        "file_path": "PendingOnly.md",
        "content": "Not on disk yet\n",
        "reasoning": "Staged create",
    })
    discard_res = shared_module.delete_file.invoke({
        "file_path": "PendingOnly.md",
        "reasoning": "Changed mind, discard staged note",
    })
    assert "Discarded pending staged note creation" in discard_res

