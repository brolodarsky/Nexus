"""
test_path_safety.py — Security tests for arbitrary-file-read vulnerability mitigations.

Verifies that path traversal attacks (e.g. '../.env', '..\\.env', 'C:\\Windows\\win.ini',
'/etc/passwd', '3. Operations/../../.env', and escaping symlinks) are strictly rejected
across vault_reader, shared @tool wrappers, FastAPI HTTP endpoints, and run_logger.
"""
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from nexus.api.main import app
from nexus.core.constants import VAULT_PATH
from nexus.core.run_logger import get_run
from nexus.shared_tools.shared import read_file
from nexus.shared_tools.vault_reader import (
    get_directory_tree,
    get_recent_modifications,
    read_note_content,
    resolve_vault_note_path,
    search_within,
)


@pytest.fixture
def client():
    """FastAPI test client instance for testing HTTP security endpoints."""
    return TestClient(app)


# ── 1. Vault Reader Note Path Resolution Safety ──────────────────────────────

@pytest.mark.parametrize(
    "malicious_path",
    [
        "../.env",
        r"..\.env",
        r"C:\Windows\win.ini",
        "/etc/passwd",
        "3. Operations/../../.env",
    ],
)
def test_resolve_vault_note_path_rejects_traversal(malicious_path: str):
    """Assert that relative and absolute path traversal vectors fail resolution with an error.

    Never attempts to read or print file contents; tests containment boundary enforcement only.
    """
    resolved, err = resolve_vault_note_path(malicious_path)
    # resolved must be None whenever an outside path is passed
    assert resolved is None
    # err must clearly state refusal or containment failure
    assert err is not None
    assert "Error:" in err
    assert "Vault" in err or "Restricted" in err


def test_resolve_vault_note_path_rejects_escaping_symlink(tmp_path: Path):
    """Assert that a symlink placed inside the Vault pointing outside the Vault is rejected.

    Handles platforms/environments where symlink creation requires elevated privileges.
    """
    symlink_name = "test_symlink_escape_note.md"
    symlink_path = VAULT_PATH / symlink_name
    target_outside = (VAULT_PATH.parent / "pyproject.toml").resolve()

    try:
        symlink_path.symlink_to(target_outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted in this OS environment (requires Developer Mode or admin privileges)")

    try:
        resolved, err = resolve_vault_note_path(symlink_name)
        assert resolved is None
        assert err is not None
        assert "Error:" in err
    finally:
        # Guarantee teardown of symlink so no leftover test artifacts remain in Vault
        if symlink_path.is_symlink() or symlink_path.exists():
            symlink_path.unlink()


def test_resolve_vault_note_path_resolves_valid_normal_note():
    """Assert that an existing standard note within the Vault resolves successfully to its canonical Path."""
    resolved, err = resolve_vault_note_path("Table of Contents.md")
    assert err is None
    assert resolved is not None
    assert resolved.exists()
    assert resolved.is_relative_to(VAULT_PATH.resolve())
    assert resolved.name == "Table of Contents.md"


def test_resolve_vault_note_path_resolves_unique_basename():
    """Assert that unique basenames (with or without '.md') resolve via the fallback search."""
    resolved, err = resolve_vault_note_path("Table of Contents")
    assert err is None
    assert resolved is not None
    assert resolved.exists()
    assert resolved.is_relative_to(VAULT_PATH.resolve())
    assert resolved.name == "Table of Contents.md"


# ── 2. Vault Reader Directory & Search Containment ───────────────────────────

@pytest.mark.parametrize(
    "malicious_folder",
    [
        "../",
        r"..\..",
        r"C:\Windows",
        "/etc",
        "3. Operations/../../",
    ],
)
def test_vault_reader_folder_functions_reject_traversal(malicious_folder: str):
    """Assert that directory-tree, keyword search, and recent modification scans reject paths outside Vault."""
    tree_out = get_directory_tree(path=malicious_folder)
    assert tree_out.startswith("Error:")

    search_out = search_within(keyword="nexus", root_path=malicious_folder)
    assert search_out.startswith("Error:")

    recent_out = get_recent_modifications(root_path=malicious_folder)
    assert recent_out.startswith("Error:")


# ── 3. LangChain Agent Tool read_file Safety ─────────────────────────────────

@pytest.mark.parametrize(
    "malicious_tool_path",
    [
        "../.env",
        r"..\.env",
        r"C:\Windows\win.ini",
        "/etc/passwd",
        "3. Operations/../../.env",
    ],
)
def test_shared_read_file_tool_rejects_traversal(malicious_tool_path: str):
    """Assert that the LangChain read_file tool wrapper returns an explicit refusal message."""
    output = read_file.invoke({"file_path": malicious_tool_path})
    assert isinstance(output, str)
    assert "Error:" in output
    assert "Vault" in output or "Restricted" in output


# ── 4. Run Logger get_run Path Safety ────────────────────────────────────────

@pytest.mark.parametrize(
    "malicious_run_id",
    [
        "../secret.json",
        r"..\secret.json",
        "foo/bar",
        r"foo\bar",
        "..",
        "subfolder/test",
    ],
)
def test_get_run_rejects_path_separators_and_dotdot(malicious_run_id: str):
    """Assert that get_run raises ValueError when provided run_id values containing path separators or '..'."""
    with pytest.raises(ValueError, match="cannot contain path separators or '..'"):
        get_run(malicious_run_id)


def test_get_run_accepts_clean_absent_id():
    """Assert that clean run_id identifiers without traversal separators return None when not found."""
    result = get_run("nonexistent_run_id_9999")
    assert result is None


# ── 5. FastAPI HTTP Route Security (routers/vault.py) ────────────────────────

@pytest.mark.parametrize(
    "malicious_http_path",
    [
        "../.env",
        r"..\.env",
        r"C:\Windows\win.ini",
        "/etc/passwd",
        "3. Operations/../../.env",
    ],
)
def test_http_get_note_rejects_traversal(client: TestClient, malicious_http_path: str):
    """Assert that GET /api/vault/note returns HTTP 400 Bad Request for traversal paths."""
    resp = client.get(f"/api/vault/note?path={malicious_http_path}")
    assert resp.status_code == 400
    assert "Invalid note path" in resp.json()["detail"] or "Refusing" in resp.json()["detail"]


def test_http_get_note_accepts_valid_note(client: TestClient):
    """Assert that GET /api/vault/note returns HTTP 200 for safe, existing Vault notes."""
    resp = client.get("/api/vault/note?path=Table of Contents.md")
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert "Table of Contents" in data["content"]


@pytest.mark.parametrize(
    "malicious_http_folder",
    [
        "../",
        r"..\..",
        r"C:\Windows",
        "/etc",
        "3. Operations/../../",
    ],
)
def test_http_routes_reject_folder_traversal(client: TestClient, malicious_http_folder: str):
    """Assert that /structure, /search, and /list return HTTP 400 Bad Request when path escapes the Vault."""
    resp_structure = client.get(f"/api/vault/structure?path={malicious_http_folder}")
    assert resp_structure.status_code == 400

    resp_search = client.get(f"/api/vault/search?keyword=test&path={malicious_http_folder}")
    assert resp_search.status_code == 400

    resp_list = client.get(f"/api/vault/list?path={malicious_http_folder}")
    assert resp_list.status_code == 400


def test_http_get_agent_run_rejects_traversal(client: TestClient):
    """Assert that GET /api/agents/runs/{run_id} returns HTTP 400 when run_id contains traversal."""
    resp_dotdot = client.get("/api/agents/runs/test..id")
    assert resp_dotdot.status_code == 400

    resp_backslash = client.get("/api/agents/runs/foo%5Cbar")
    assert resp_backslash.status_code == 400


# ── 6. Root Directory Alias Depth Bound (Prevent Full-Vault File Dumps) ──────

def test_get_directory_structure_root_aliases_are_bounded_depth_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify `get_directory_structure` with root aliases (`""`, `"."`, `"/"`, `"Vault"`) caps at depth 1."""
    from nexus.shared_tools import shared as shared_module, vault_reader

    vault_dir = tmp_path / "Vault"
    (vault_dir / "0. Inbox").mkdir(parents=True, exist_ok=True)
    (vault_dir / "3. Operations" / "3.1. Career").mkdir(parents=True, exist_ok=True)
    (vault_dir / "Master Instructions.md").write_text("# Root", encoding="utf-8")
    (vault_dir / "Gameplan.md").write_text("# Plan", encoding="utf-8")
    (vault_dir / "0. Inbox" / "Capture.md").write_text("# Capture", encoding="utf-8")
    (vault_dir / "3. Operations" / "3.1. Career" / "Mission - Deep.md").write_text("# Deep", encoding="utf-8")

    monkeypatch.setattr(vault_reader, "VAULT_PATH", vault_dir)
    monkeypatch.setattr(shared_module, "VAULT_PATH", vault_dir)

    # 1. `path=None`: folders only across Vault
    folders_only = shared_module.get_directory_structure.invoke({})
    assert "0. Inbox/" in folders_only
    assert "3.1. Career/" in folders_only
    assert "Master Instructions.md" not in folders_only
    assert "Mission - Deep.md" not in folders_only

    # 2. Root aliases: show root files + top-level folders (nested subfolders collapsed inline), NEVER deep files
    for root_alias in ("", ".", "/", "Vault", "Vault/"):
        root_out = shared_module.get_directory_structure.invoke({"path": root_alias})
        assert "Master Instructions.md" in root_out
        assert "Gameplan.md" in root_out
        assert "0. Inbox/" in root_out
        assert "3. Operations/ [3.1. Career]" in root_out
        assert "Capture.md" not in root_out
        assert "Mission - Deep.md" not in root_out

    # 3. Drilling into a specific folder still shows its files
    inbox_out = shared_module.get_directory_structure.invoke({"path": "0. Inbox"})
    assert "Capture.md" in inbox_out

    # 4. Path traversal still rejected
    assert shared_module.get_directory_structure.invoke({"path": "../"}).startswith("Error:")
    assert shared_module.get_directory_structure.invoke({"path": "/etc"}).startswith("Error:")
