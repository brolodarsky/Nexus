"""
test_conversation_cache.py — Comprehensive tests for the Universal Per-Conversation External Capture Cache.

Covers:
  1. Per-conversation SQLite WAL storage, normalized URL upsert, and slug collision disambiguation.
  2. Strict per-conversation isolation across `get_capture`, `list_captures`, `read_file`,
     `hydrate_subagent_context_files`, `create_file`, and `modify_file`.
  3. Cache inheritance across `fork_conversation` (`fork` and `tangent`) and `spawn_seeded_conversation`
     (`nest_under_parent=True` and `False`), plus snapshot isolation after fork.
  4. `delete_conversation` cleanup of `conversation_captures` without touching siblings or promoted children.
  5. `read_browser_tabs` (`browser_bridge.read_tabs`), universal `read_webpage.scrape_url`, `run_shared_tool_cli`
     subprocess `NEXUS_CONVERSATION_ID` propagation, and `fetch_emails` untruncated full-body caching.
  6. `read_file` + `hydrate_subagent_context_files` `cache://` resolution & fail-fast error diagnostics.
  7. Universal deterministic `{{cache:<key>}}` splicing in `create_file` and `modify_file` (backslashes,
     non-recursive expansion, multiple placeholders, fail-fast missing key).
  8. Chrome Extension (`background.js`) DOM deduplication verification via Node.js.
  9. KV prompt-cache invariant (`inject_root_instructions()` stays byte-identical across captures).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest
from langchain_core.messages import AIMessage

from nexus.core import chat_branching, chats_db, conversation_cache, hitl_queue as hq
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import reset_hitl_execution_context, set_hitl_execution_context
from nexus.shared_tools import browser_bridge, gmail_engine, read_webpage, shared as shared_module, vault_reader


# ── Isolated Temp Workspace Fixture ──────────────────────────────────────────

@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Isolates `chats.db`, `hitl.db`, and `VAULT_PATH` inside `tmp_path` per test."""
    vault_dir = tmp_path / "Vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "chats.db"
    hitl_path = tmp_path / "hitl.db"

    monkeypatch.setattr(chats_db, "DB_PATH", db_path)
    monkeypatch.setattr(hq, "DB_PATH", hitl_path)
    monkeypatch.setattr(shared_module, "VAULT_PATH", vault_dir)
    monkeypatch.setattr(vault_reader, "VAULT_PATH", vault_dir)

    chats_db.init_db()
    hq.init_db()
    return {"tmp": tmp_path, "vault": vault_dir, "chats_db": db_path, "hitl_db": hitl_path}


# ── 1. URL Normalization, Upsert & Per-Conversation Isolation ────────────────

def test_normalize_capture_url_and_upsert_collision_safety(isolated_env: dict[str, Path]) -> None:
    """Verify tracking params strip universally, matching URLs upsert, and duplicate titles disambiguate."""
    u1 = "HTTPS://Example.COM/jobs/123/?utm_source=linkedin&gh_src=abc&role=ai#apply"
    u2 = "https://example.com/jobs/123?role=ai&trk=xyz"
    assert conversation_cache.normalize_capture_url(u1) == "https://example.com/jobs/123?role=ai"
    assert conversation_cache.normalize_capture_url(u1) == conversation_cache.normalize_capture_url(u2)

    k1 = conversation_cache.put_capture(
        conversation_id="conv-a",
        source_type="web",
        title="Applied AI Engineer",
        content="Initial capture v1",
        source_url=u1,
    )
    assert k1 == "cache://web/applied-ai-engineer"

    # Re-capturing same normalized URL updates existing row in-place and retains its cache_key
    k1_again = conversation_cache.put_capture(
        conversation_id="conv-a",
        source_type="web",
        title="Applied AI Engineer (Updated)",
        content="Updated capture v2",
        source_url=u2,
    )
    assert k1_again == k1
    fetched = conversation_cache.get_capture("conv-a", k1)
    assert fetched is not None
    assert fetched["content"] == "Updated capture v2"
    assert fetched["title"] == "Applied AI Engineer (Updated)"

    # A distinct URL sharing the exact same slug ("Applied AI Engineer") gets a `-2` suffix instead of overwriting
    k2 = conversation_cache.put_capture(
        conversation_id="conv-a",
        source_type="web",
        title="Applied AI Engineer",
        content="Different company posting",
        source_url="https://other.example.org/careers/456",
    )
    assert k2 == f"{k1}-2"
    assert len(conversation_cache.list_captures("conv-a")) == 2


def test_per_conversation_isolation_across_reads_hydration_and_splice(isolated_env: dict[str, Path]) -> None:
    """Conversation A must never read, pre-hydrate, or splice Conversation B's captures."""
    key_b = conversation_cache.put_capture(
        conversation_id="conv-b",
        source_type="tab",
        title="Confidential Spec",
        content="Secret content owned strictly by Conversation B.",
        source_url="https://internal.example.com/spec",
    )
    conversation_cache.put_capture(
        conversation_id="conv-a",
        source_type="web",
        title="Public Docs",
        content="Public docs owned by Conversation A.",
        source_url="https://docs.example.com/public",
    )

    assert conversation_cache.get_capture("conv-a", key_b) is None
    assert conversation_cache.get_capture("conv-a", "https://internal.example.com/spec") is None

    # Switch active execution context to Conversation A and confirm all tool paths enforce isolation
    tok = set_hitl_execution_context(conversation_id="conv-a", thread_id="conv-a")
    try:
        read_err = shared_module.read_file.invoke({"file_path": key_b})
        assert "not found in conversation `conv-a`" in read_err
        assert "cache://web/public-docs" in read_err

        prehydrated, hydr_err = shared_module.hydrate_subagent_context_files([key_b])
        assert prehydrated is None
        assert hydr_err is not None
        assert "cache://web/public-docs" in hydr_err

        short_b = key_b[len("cache://") :]
        create_err = shared_module.create_file.invoke(
            {
                "file_path": "0. Inbox/Attempt.md",
                "content": f"# Test\n\n{{{{cache:{short_b}}}}}\n",
                "reasoning": "Test cross-conversation splice isolation",
            }
        )
        assert create_err.startswith("Error: Unresolved cache placeholder(s)")
        assert "cache://web/public-docs" in create_err
    finally:
        reset_hitl_execution_context(tok)


# ── 2. Branch Inheritance & Delete Cleanup ───────────────────────────────────

def test_fork_and_spawn_inherit_captures_and_delete_purges_cleanly(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `fork_conversation`, `spawn_seeded_conversation`, and `delete_conversation` cache lifecycles."""
    # Prevent seed_langgraph_thread_from_messages from touching repo memory.sqlite during unit tests
    monkeypatch.setattr(chat_branching, "seed_langgraph_thread_from_messages", lambda *_a, **_kw: None)

    parent_id = chats_db.create_conversation(title="Parent Thread")
    sibling_id = chats_db.create_conversation(title="Sibling Thread")
    m1 = chats_db.log_message(role="user", content="Read these docs", conversation_id=parent_id)
    m2 = chats_db.log_message(role="assistant", content="Done reading", agent="nexus", conversation_id=parent_id)
    chats_db.log_message(role="user", content="Second turn", conversation_id=parent_id)
    m4 = chats_db.log_message(role="assistant", content="Branch point", agent="nexus", conversation_id=parent_id)

    parent_key = conversation_cache.put_capture(
        conversation_id=parent_id,
        source_type="tab",
        title="Parent Capture",
        content="Verbatim parent text.",
        source_url="https://example.com/parent-doc",
    )
    sibling_key = conversation_cache.put_capture(
        conversation_id=sibling_id,
        source_type="web",
        title="Sibling Capture",
        content="Sibling text.",
        source_url="https://example.com/sibling-doc",
    )

    # 1. Full fork (`branch_mode="fork"`) inherits parent's captures
    fork_res = chat_branching.fork_conversation(
        parent_conversation_id=parent_id,
        parent_message_id=m2,
        branch_mode="fork",
        title="Forked Child",
    )
    fork_id = fork_res["conversation_id"]
    fork_cap = conversation_cache.get_capture(fork_id, parent_key)
    assert fork_cap is not None and fork_cap["content"] == "Verbatim parent text."

    # 2. Tangent branch (`branch_mode="tangent"`) inherits parent's captures
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="Parent brief summary.")
    with patch("nexus.core.chat_branching.get_chat_model", return_value=mock_llm):
        tangent_res = chat_branching.fork_conversation(
            parent_conversation_id=parent_id,
            parent_message_id=m4,
            branch_mode="tangent",
        )
    tangent_id = tangent_res["conversation_id"]
    tangent_cap = conversation_cache.get_capture(tangent_id, parent_key)
    assert tangent_cap is not None and tangent_cap["content"] == "Verbatim parent text."

    # 3. `spawn_seeded_conversation` inherits captures (nested AND standalone root spawned from parent)
    nested_res = chat_branching.spawn_seeded_conversation(
        title="Nested Spawn",
        context_brief="Inspect the parent capture.",
        parent_conversation_id=parent_id,
        nest_under_parent=True,
    )
    nested_id = nested_res["conversation_id"]
    assert conversation_cache.get_capture(nested_id, parent_key) is not None

    root_spawn_res = chat_branching.spawn_seeded_conversation(
        title="Standalone Spawn",
        context_brief="Standalone follow-up from parent capture.",
        parent_conversation_id=parent_id,
        nest_under_parent=False,
    )
    root_spawn_id = root_spawn_res["conversation_id"]
    assert conversation_cache.get_capture(root_spawn_id, parent_key) is not None

    # Child captures added post-fork must NOT leak back into parent
    child_only_key = conversation_cache.put_capture(
        conversation_id=fork_id,
        source_type="web",
        title="Child Only Capture",
        content="Only exists in forked child.",
        source_url="https://example.com/child-only",
    )
    assert conversation_cache.get_capture(parent_id, child_only_key) is None

    # 4. Deleting parent purges ONLY parent's rows, leaving promoted children and sibling intact
    chats_db.delete_conversation(parent_id)
    assert conversation_cache.list_captures(parent_id) == []
    assert conversation_cache.get_capture(fork_id, parent_key) is not None
    assert conversation_cache.get_capture(tangent_id, parent_key) is not None
    assert conversation_cache.get_capture(nested_id, parent_key) is not None
    assert conversation_cache.get_capture(root_spawn_id, parent_key) is not None
    assert conversation_cache.get_capture(sibling_id, sibling_key) is not None


# ── 3. Auto-Capture in browser_bridge, read_webpage, CLI & fetch_emails ──────

def test_browser_bridge_read_tabs_auto_caches_and_exposes_handle(isolated_env: dict[str, Path]) -> None:
    """`read_tabs()` stores captures in active conversation cache and renders `Cache Key` in Markdown."""
    jd_md = "# Staff AI Engineer\n\nBuild agentic workflows with deterministic verification."
    mock_dispatch = {
        "ok": True,
        "transport": "fastapi:8000",
        "data": {
            "requested_count": 1,
            "succeeded_count": 1,
            "tabs": [
                {
                    "tab_id": 12,
                    "title": "Staff AI Engineer @ Acme",
                    "url": "https://careers.acme.example/roles/42?utm_source=x",
                    "ok": True,
                    "char_count": len(jd_md),
                    "truncated": False,
                    "markdown": jd_md,
                }
            ],
        },
    }

    tok = set_hitl_execution_context(conversation_id="conv-tabs", thread_id="conv-tabs")
    try:
        with patch.object(browser_bridge, "_dispatch_browser_command", return_value=mock_dispatch):
            res = browser_bridge.read_tabs(tab_ids=[12])
        formatted = browser_bridge.format_tab_reads_as_markdown(res)
    finally:
        reset_hitl_execution_context(tok)

    expected_key = "cache://tab/staff-ai-engineer-acme"
    assert res["data"]["tabs"][0]["cache_key"] == expected_key
    assert f"- **Cache Key:** `{expected_key}`" in formatted
    assert "{{cache:tab/staff-ai-engineer-acme}}" in formatted

    stored = conversation_cache.get_capture("conv-tabs", "https://careers.acme.example/roles/42")
    assert stored is not None and stored["content"] == jd_md


def test_read_webpage_universal_cache_hit_trafilatura_and_spa_jsonld_fallback(
    isolated_env: dict[str, Path],
) -> None:
    """Verify `read_webpage.scrape_url` hits cache first, falls back to trafilatura & JSON-LD, and caches."""
    cached_url = "https://example.org/already-open-tab?utm_medium=email"
    conversation_cache.put_capture(
        conversation_id="conv-web",
        source_type="tab",
        title="Open Tab Capture",
        content="Cached verbatim tab content from Chrome extension.",
        source_url=cached_url,
    )

    tok = set_hitl_execution_context(conversation_id="conv-web", thread_id="conv-web")
    try:
        # 1. Cache-hit short-circuit: never hits network when normalized URL is already in this conversation
        with patch.object(read_webpage.trafilatura, "fetch_url", side_effect=AssertionError("Should hit cache!")):
            out = read_webpage.scrape_url("https://example.org/already-open-tab")
        assert out == "Cached verbatim tab content from Chrome extension."

        # 2. Generic `trafilatura` fetch + auto-cache
        article_body = "This is a clean long-form technical article covering distributed consensus and WAL SQLite design. " * 5
        with (
            patch.object(read_webpage.trafilatura, "fetch_url", return_value="<html><head><title>WAL SQLite</title></head></html>"),
            patch.object(read_webpage.trafilatura, "extract", return_value=article_body),
        ):
            web_out, web_key = read_webpage.scrape_url_with_cache("https://blog.example.com/wal-sqlite")
        assert web_out == article_body.strip()
        assert web_key == "cache://web/wal-sqlite"
        assert conversation_cache.get_capture("conv-web", web_key)["content"] == article_body.strip()

        # 3. Universal JSON-LD fallback when static HTML is an SPA JS shell
        desc = "<p>" + ("Generic schema fallback for SPA applications without vendor-specific regexes. " * 6) + "</p>"
        spa_html = (
            "<html><head><title>SPA Page</title>"
            f'<script type="application/ld+json">{json.dumps({"@type": "JobPosting", "title": "Platform Engineer", "hiringOrganization": {"name": "BetaCo"}, "description": desc})}</script>'
            "</head><body>You need to enable JavaScript to run this app.</body></html>"
        )
        with (
            patch.object(read_webpage.trafilatura, "fetch_url", return_value=spa_html),
            patch.object(read_webpage.trafilatura, "extract", return_value="You need to enable JavaScript to run this app."),
        ):
            spa_out, spa_key = read_webpage.scrape_url_with_cache("https://jobs.example.io/roles/platform")
        assert spa_out is not None
        assert "# Platform Engineer" in spa_out
        assert "**Company:** BetaCo" in spa_out
        assert spa_key == "cache://web/spa-page"
    finally:
        reset_hitl_execution_context(tok)


def test_run_shared_tool_cli_propagates_conversation_id(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`run_shared_tool_cli` forwards active `conversation_id` as `NEXUS_CONVERSATION_ID` to subprocesses."""
    captured_env: dict[str, str] = {}

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        proc = MagicMock()
        proc.stdout = "ok"
        proc.stderr = ""
        proc.returncode = 0
        return proc

    monkeypatch.setattr(shared_module.subprocess, "run", fake_run)
    tok = set_hitl_execution_context(conversation_id="conv-cli-prop", thread_id="conv-cli-prop")
    try:
        res = shared_module.run_shared_tool_cli.invoke(
            {"module": "nexus.shared_tools.read_webpage", "cli_args": ["--help"]}
        )
    finally:
        reset_hitl_execution_context(tok)

    assert res == "ok"
    assert captured_env.get("NEXUS_CONVERSATION_ID") == "conv-cli-prop"

    # Verify child process helper reads NEXUS_CONVERSATION_ID when ContextVar is unset
    monkeypatch.setenv("NEXUS_CONVERSATION_ID", "conv-from-env")
    assert conversation_cache.get_active_conversation_id() == "conv-from-env"


def test_fetch_emails_caches_full_untruncated_body_and_splices_cleanly(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`fetch_emails` stores full (>4,000 char) bodies under `cache://email/<id>` for verbatim splicing."""
    huge_email_body = ("Recruiter interview packet details and coding prep syllabus. " * 90).strip()
    assert len(huge_email_body) > shared_module._BODY_CHAR_LIMIT

    monkeypatch.setattr(
        gmail_engine,
        "list_messages",
        lambda **_kw: [{"id": "msg_long_99", "account": "default", "thread_id": "th_99", "subject": "Onsite Schedule"}],
    )
    monkeypatch.setattr(gmail_engine, "get_gmail_service", lambda account="default": MagicMock())
    monkeypatch.setattr(
        gmail_engine,
        "get_message",
        lambda *_a, **_kw: {
            "id": "msg_long_99",
            "account": "default",
            "thread_id": "th_99",
            "subject": "Onsite Schedule",
            "sender": "recruiter@example.com",
            "date": "2026-11-18",
            "labels": ["INBOX"],
            "body": huge_email_body,
        },
    )

    tok = set_hitl_execution_context(conversation_id="conv-email", thread_id="conv-email")
    try:
        payload = json.loads(shared_module.fetch_emails.invoke({"count": 1}))
        assert len(payload) == 1
        assert len(payload[0]["body"]) == shared_module._BODY_CHAR_LIMIT
        assert payload[0]["cache_key"] == "cache://email/msg_long_99"

        # Splicing {{cache:email/msg_long_99}} writes the FULL untruncated body into Vault
        stage_res = shared_module.create_file.invoke(
            {
                "file_path": "0. Inbox/Onsite Packet.md",
                "content": "# Packet\n\n{{cache:email/msg_long_99}}\n",
                "reasoning": "Archive full email verbatim",
            }
        )
        assert "✅ File creation staged to HITL queue" in stage_res
        pending = hq.get_pending_for_file("Vault/0. Inbox/Onsite Packet.md")
        assert pending is not None
        assert huge_email_body in pending["proposed_content"]
    finally:
        reset_hitl_execution_context(tok)


# ── 4. read_file, hydrate_subagent_context_files & Deterministic Splice ──────

def test_read_file_and_subagent_hydration_resolve_cache_refs_and_fail_fast(
    isolated_env: dict[str, Path],
) -> None:
    """Verify `read_file` and `hydrate_subagent_context_files` support `cache://`, URLs, slicing, and typos."""
    vault_dir = isolated_env["vault"]
    (vault_dir / "Notes.md").write_text("# Local Vault Note\nBaseline context.", encoding="utf-8")

    multiline_capture = "Line A\nLine B\nLine C\nLine D"
    key = conversation_cache.put_capture(
        conversation_id="conv-hydr",
        source_type="web",
        title="Architecture Paper",
        content=multiline_capture,
        source_url="https://papers.example.org/arch?utm_source=hn",
    )

    tok = set_hitl_execution_context(conversation_id="conv-hydr", thread_id="conv-hydr")
    try:
        # 1. `read_file("cache://")` returns lightweight manifest without blowing context
        manifest = shared_module.read_file.invoke({"file_path": "cache://"})
        assert "Cached External Captures (1 item(s)" in manifest
        assert key in manifest
        assert "Line D" not in manifest

        # 2. `read_file` with `cache://...` key, line slice, and normalized URL
        sliced = shared_module.read_file.invoke({"file_path": key, "start_line": 2, "end_line": 3})
        assert "2: Line B" in sliced
        assert "3: Line C" in sliced
        assert "Line D" not in sliced

        by_url = shared_module.read_file.invoke({"file_path": "https://papers.example.org/arch"})
        assert "Line A" in by_url and "Line D" in by_url

        # 3. `read_file` typo fails fast and lists valid keys
        typo_read = shared_module.read_file.invoke({"file_path": "cache://web/wrong-slug"})
        assert "not found in conversation `conv-hydr`" in typo_read
        assert key in typo_read

        # 4. `hydrate_subagent_context_files` mixes Vault notes + cache key + deduplicates URL referring to same entry
        prehydrated, err = shared_module.hydrate_subagent_context_files(
            [
                "Notes.md",
                key,
                "https://papers.example.org/arch",
            ]
        )
        assert err is None
        assert prehydrated is not None
        assert prehydrated.startswith("# Pre-Hydrated Disk Context")
        assert "Baseline context." in prehydrated
        assert prehydrated.count(f"## `{key}`") == 1
        assert "Line D" in prehydrated

        # 5. Missing cache ref in `context_files` aborts with fail-fast report listing valid keys
        bad_prehydrated, bad_err = shared_module.hydrate_subagent_context_files(["cache://tab/nonexistent"])
        assert bad_prehydrated is None
        assert bad_err is not None
        assert "Fail-Fast Context Hydration Error" in bad_err
        assert key in bad_err
    finally:
        reset_hitl_execution_context(tok)


def test_create_file_and_modify_file_deterministic_cache_splice_universal(
    isolated_env: dict[str, Path],
) -> None:
    """Verify `{{cache:<key>}}` works in any folder, handles backslashes & non-recursion, and fails fast on missing keys."""
    vault_dir = isolated_env["vault"]
    target_note = vault_dir / "5. Reference" / "Article Note.md"
    target_note.parent.mkdir(parents=True, exist_ok=True)
    target_note.write_text("# Article\n\n## Excerpt\n\nPLACEHOLDER\n", encoding="utf-8")

    # Include regex-like backreferences (\1, \n), Windows paths, AND literal {{cache:...}} text inside capture!
    tricky_capture = (
        r"Regex group \1 and Windows path C:\new\tab\1\2."
        "\nLiteral token inside webpage: {{cache:web/does-not-exist}}."
    )
    k_tab = conversation_cache.put_capture(
        conversation_id="conv-splice",
        source_type="tab",
        title="Systems Paper",
        content=tricky_capture,
        source_url="https://sys.example.com/paper",
    )
    k_web = conversation_cache.put_capture(
        conversation_id="conv-splice",
        source_type="web",
        title="Appendix",
        content="Appendix verbatim table.",
        source_url="https://sys.example.com/appendix",
    )

    tok = set_hitl_execution_context(conversation_id="conv-splice", thread_id="conv-splice")
    try:
        # 1. `create_file` in an arbitrary folder accepts both `{{cache:tab/...}}` and `{{cache:cache://web/...}}`
        short_tab = k_tab[len("cache://") :]
        create_res = shared_module.create_file.invoke(
            {
                "file_path": "5. Reference/Saved Paper.md",
                "content": f"# Saved Paper\n\n{{{{cache:{short_tab}}}}}\n\n{{{{cache:{k_web}}}}}\n",
                "reasoning": "Archive paper and appendix verbatim",
            }
        )
        assert "✅ File creation staged to HITL queue" in create_res
        assert "spliced 2 cached capture(s) verbatim" in create_res

        staged_create = hq.get_pending_for_file("Vault/5. Reference/Saved Paper.md")
        assert staged_create is not None
        assert tricky_capture in staged_create["proposed_content"]
        assert "Appendix verbatim table." in staged_create["proposed_content"]

        # 2. `modify_file` also resolves `{{cache:<key>}}` cleanly in `replacement`
        mod_res = shared_module.modify_file.invoke(
            {
                "file_path": "5. Reference/Article Note.md",
                "target": "PLACEHOLDER",
                "replacement": f"{{{{cache:{short_tab}}}}}",
                "reasoning": "Splice systems paper excerpt",
            }
        )
        assert "✅ Surgical modification staged to HITL queue" in mod_res
        staged_mod = hq.get_pending_for_file("Vault/5. Reference/Article Note.md")
        assert staged_mod is not None
        assert tricky_capture in staged_mod["proposed_content"]

        # 3. Missing key fails fast and does NOT stage transaction
        bad_res = shared_module.create_file.invoke(
            {
                "file_path": "5. Reference/Should Not Exist.md",
                "content": "# Bad\n\n{{cache:tab/missing-key}}\n",
                "reasoning": "Should fail fast",
            }
        )
        assert bad_res.startswith("Error: Unresolved cache placeholder(s)")
        assert k_tab in bad_res
        assert hq.get_pending_for_file("Vault/5. Reference/Should Not Exist.md") is None
    finally:
        reset_hitl_execution_context(tok)


# ── 5. Extension DOM Deduplication & KV Prompt-Cache Invariant ───────────────

def test_chrome_extension_dom_deduplication_via_node() -> None:
    """Runs the Node.js `extractTabMarkdownReadOnly` suite validating DOM deduplication & `/application` fallback."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js not available on system PATH; skipping JS DOM simulation test.")
    script_path = Path(__file__).resolve().parent / "test_browser_extension_dom.js"
    proc = subprocess.run([node_bin, str(script_path)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, f"Node DOM test failed:\n{proc.stderr}\n{proc.stdout}"
    assert "All Node.js browser extension DOM tests passed successfully!" in proc.stdout


def test_kv_prompt_cache_system_prompt_unaffected_by_captures(isolated_env: dict[str, Path]) -> None:
    """Storing per-conversation captures must NEVER alter static `inject_root_instructions()` output."""
    before = inject_root_instructions()
    conversation_cache.put_capture(
        conversation_id="conv-kv",
        source_type="web",
        title="KV Invariant Test",
        content="Dynamic external capture payload that must stay out of SystemMessage.",
        source_url="https://example.com/kv-test",
    )
    after = inject_root_instructions()
    assert before == after


def test_spawn_conversation_inherits_manifest_cli_nexus_primary_and_brief_lint(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `spawn_conversation` appends inherited capture manifest, works from `nexus_primary`, and ignores `cache://` in path lint."""
    monkeypatch.setattr(chat_branching, "seed_langgraph_thread_from_messages", lambda *_a, **_kw: None)

    vault_dir = isolated_env["vault"]
    (vault_dir / "Real Note.md").write_text("# Real Note", encoding="utf-8")

    # 1. Path lint must NOT flag cache:// handles or {{cache:...}} placeholders ending in .md/.pdf/.docx
    brief_with_cache = (
        "Inspect [[Real Note]], cache://web/report.pdf, `cache://tab/notes.md`, and {{cache:web/paper.pdf}}."
    )
    assert vault_reader.verify_context_brief_paths(brief_with_cache) == []

    brief_with_real_and_missing = (
        "Inspect cache://web/report.pdf, {{cache:web/paper.pdf}}, and Missing File.md."
    )
    assert vault_reader.verify_context_brief_paths(brief_with_real_and_missing) == ["Missing File.md"]

    # 2. Normal parent UUID: spawn_conversation inherits captures, appends manifest, and surfaces count in receipt
    parent_id = chats_db.create_conversation(title="Inbox Sweep")
    secret_body = "UNIQUE_RAW_CAPTURE_BODY_SHOULD_NOT_BE_DUMPED_IN_MANIFEST"
    k_parent = conversation_cache.put_capture(
        conversation_id=parent_id,
        source_type="tab",
        title="Target Listing",
        content=secret_body,
        source_url="https://example.com/listing",
    )
    tok = set_hitl_execution_context(conversation_id=parent_id, thread_id=parent_id)
    try:
        receipt = shared_module.spawn_conversation.invoke(
            {
                "title": "Follow-up Thread",
                "context_brief": f"Archive `cache://tab/notes.md` and `{k_parent}` with [[Real Note]].",
                "nest_under_current": True,
            }
        )
    finally:
        reset_hitl_execution_context(tok)

    assert "inherited captures: 1" in receipt
    assert "[SYSTEM WARNING:" not in receipt
    children = [c for c in chats_db.get_conversations() if c.get("parent_conversation_id") == parent_id]
    assert len(children) == 1
    child_id = children[0]["id"]

    history = chats_db.get_chat_history(child_id)
    assert len(history) == 1
    seeded_brief = history[0]["content"]
    assert "### 📦 Inherited External Captures (1)" in seeded_brief
    assert k_parent in seeded_brief
    assert secret_body not in seeded_brief
    assert conversation_cache.get_capture(child_id, k_parent)["content"] == secret_body

    # 3. CLI/eval `"nexus_primary"` context: creates standalone root thread AND inherits `"nexus_primary"` captures
    k_cli = conversation_cache.put_capture(
        conversation_id="nexus_primary",
        source_type="web",
        title="CLI Spec",
        content="CLI verbatim body.",
        source_url="https://example.com/cli-spec",
    )
    cli_tok = set_hitl_execution_context(conversation_id="nexus_primary", thread_id="nexus_primary")
    try:
        cli_receipt = shared_module.spawn_conversation.invoke(
            {
                "title": "CLI Spawned Thread",
                "context_brief": f"Work from `{k_cli}`.",
                "nest_under_current": True,
            }
        )
    finally:
        reset_hitl_execution_context(cli_tok)

    assert "standalone root conversation" in cli_receipt
    assert "inherited captures: 1" in cli_receipt
    cli_convs = [c for c in chats_db.get_conversations() if c.get("title") == "CLI Spawned Thread"]
    assert len(cli_convs) == 1
    cli_child_id = cli_convs[0]["id"]
    assert cli_convs[0]["parent_conversation_id"] is None
    assert conversation_cache.get_capture(cli_child_id, k_cli)["content"] == "CLI verbatim body."
