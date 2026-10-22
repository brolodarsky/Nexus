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
