"""
test_conversation_cache.py — Comprehensive tests for the Universal Per-Conversation External Capture Cache.

Covers:
  1. Per-conversation SQLite WAL storage, normalized URL upsert, and slug collision disambiguation.
  2. Strict per-conversation isolation across `get_capture`, `list_captures`, `read_file`,
     `hydrate_subagent_context_files`, `create_file`, and `modify_file`.
  3. Cache inheritance across `fork_conversation` (`fork` and `tangent`) and `spawn_seeded_conversation`
     (`nest_under_parent=True` and `False`), plus snapshot isolation after fork.
  4. `delete_conversation` cleanup of `conversation_captures` without touching siblings or promoted children.
  5. `read_browser_tabs` (`browser_bridge.read_tabs`), universal `read_webpage.scrape_url`, `get_youtube_transcript`
     auto-caching, `NEXUS_CONVERSATION_ID` fallback, and `fetch_emails` untruncated full-body caching.
  6. `read_file` + `hydrate_subagent_context_files` `cache://` resolution & fail-fast error diagnostics.
  7. Universal deterministic `{{cache:<key>}}` splicing in `create_file` and `modify_file` (backslashes,
     non-recursive expansion, multiple placeholders, fail-fast missing key).
  8. Chrome Extension (`background.js`) DOM deduplication verification via Node.js.
  9. KV prompt-cache invariant (`inject_root_instructions()` stays byte-identical across captures).
  10. Read-only HTTP API routes (`/api/agents/ask/conversations/{id}/captures` and `/captures/item`).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient
import pytest
from langchain_core.messages import AIMessage

from nexus.api.main import app
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


def test_read_webpage_extracts_accessible_images_and_filters_noise(
    isolated_env: dict[str, Path],
) -> None:
    """Verify `read_webpage` enriches inline images with accessibility metadata, handles JSON-LD images, and strips noise."""
    rich_html = """
    <html>
      <head><title>Visual Systems Guide</title></head>
      <body>
        <nav><img src="/nav-logo.png" alt="Site Navigation Logo" /></nav>
        <article>
          <h1>Visual Systems</h1>
          <p>Detailed systems architecture overview covering write-ahead logging, checkpointing, and replication flows across nodes.</p>
          <figure>
            <img src="/images/wal-flow.png" alt="WAL checkpoint diagram" />
            <figcaption>Figure 1: Pages flush from WAL to main DB.</figcaption>
          </figure>
          <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" data-src="/images/lazy-arch.webp" aria-label="Lazy-loaded replication topology" />
          <svg role="img" aria-label="P99 latency breakdown"><title>P99 latency breakdown</title></svg>
          <img src="/pixel.gif" alt="" width="1" height="1" />
          <p>Additional technical explanation ensuring extraction length cleanly passes validation thresholds in trafilatura.</p>
        </article>
      </body>
    </html>
    """
    trafilatura_md = (
        "# Visual Systems\n\n"
        "Detailed systems architecture overview covering write-ahead logging, checkpointing, and replication flows across nodes.\n\n"
        "![WAL checkpoint diagram](/images/wal-flow.png)\n\n"
        "![](/pixel.gif)\n\n"
        "Additional technical explanation ensuring extraction length cleanly passes validation thresholds in trafilatura."
    )

    tok = set_hitl_execution_context(conversation_id="conv-img", thread_id="conv-img")
    try:
        with (
            patch.object(read_webpage.trafilatura, "fetch_url", return_value=rich_html),
            patch.object(read_webpage.trafilatura, "extract", return_value=trafilatura_md),
        ):
            out, key = read_webpage.scrape_url_with_cache("https://blog.example.com/posts/visual-systems")

        assert out is not None
        assert key == "cache://web/visual-systems-guide"
        # Inline image upgraded with figcaption and resolved to absolute URL
        assert "![WAL checkpoint diagram — Figure 1: Pages flush from WAL to main DB.](https://blog.example.com/images/wal-flow.png)" in out
        # Lazy-loaded data-src image and semantic SVG captured in appendix
        assert "## Visuals (Accessibility Metadata)" in out
        assert "![Lazy-loaded replication topology](https://blog.example.com/images/lazy-arch.webp)" in out
        assert "[SVG Diagram: P99 latency breakdown]" in out
        # Nav logo and 1x1 empty-alt tracking pixel excluded
        assert "nav-logo.png" not in out
        assert "pixel.gif" not in out

        # Verify JSON-LD fallback preserves lazy/relative `<img>` tags with accessible text
        desc = (
            "<p>"
            + ("Platform architecture role details with embedded diagram context for candidates. " * 5)
            + '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" data-src="/assets/org-chart.png" alt="Engineering org chart" />'
            + "</p>"
        )
        spa_html = (
            "<html><head><title>SPA With Diagram</title>"
            f'<script type="application/ld+json">{json.dumps({"@type": "JobPosting", "title": "Staff Infra", "description": desc})}</script>'
            "</head><body>You need to enable JavaScript to run this app.</body></html>"
        )
        with (
            patch.object(read_webpage.trafilatura, "fetch_url", return_value=spa_html),
            patch.object(read_webpage.trafilatura, "extract", return_value="You need to enable JavaScript to run this app."),
        ):
            spa_out, _ = read_webpage.scrape_url_with_cache("https://jobs.example.io/roles/staff-infra")
        assert spa_out is not None
        assert "![Engineering org chart](https://jobs.example.io/assets/org-chart.png)" in spa_out
    finally:
        reset_hitl_execution_context(tok)


def test_read_webpage_and_youtube_tools_cache_in_active_conversation(
    isolated_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`read_webpage` and `get_youtube_transcript` cache under the active `conversation_id` and respect `NEXUS_CONVERSATION_ID`."""
    from nexus.shared_tools import youtube_transcript

    monkeypatch.setattr(
        read_webpage,
        "scrape_url_with_cache",
        lambda url, output_format="markdown": ("# Example Page\n\nBody text.", "cache://web/example"),
    )
    monkeypatch.setattr(
        youtube_transcript,
        "get_transcript",
        lambda video_id: [SimpleNamespace(text="Hello unified tools.")],
    )
    monkeypatch.setattr(youtube_transcript, "get_video_title", lambda video_id: "Unified Tools Demo")

    tok = set_hitl_execution_context(conversation_id="conv-unified-cache", thread_id="conv-unified-cache")
    try:
        web_res = shared_module.read_webpage.invoke({"url": "https://example.com"})
        yt_res = shared_module.get_youtube_transcript.invoke({"url_or_id": "https://youtu.be/abc123XYZ"})
        cached = conversation_cache.get_capture("conv-unified-cache", "cache://youtube/abc123XYZ")
    finally:
        reset_hitl_execution_context(tok)

    assert "cache://web/example" in web_res
    assert "# Example Page" in web_res
    assert "cache://youtube/abc123XYZ" in yt_res
    assert "Hello unified tools." in yt_res
    assert cached is not None
    assert "Unified Tools Demo" in cached["title"]

    # Verify env fallback still resolves NEXUS_CONVERSATION_ID when ContextVar is unset
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
        # Default scan mode returns metadata+snippet only without calling get_message
        scan_payload = json.loads(shared_module.fetch_emails.invoke({"count": 1}))
        assert len(scan_payload) == 1
        assert "body" not in scan_payload[0]

        # Explicit include_body=True (or message_ids=[...]) hydrates + caches full untruncated body
        payload = json.loads(shared_module.fetch_emails.invoke({"count": 1, "include_body": True}))
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


# ── 10. Read-Only Capture Cache HTTP API Routes ──────────────────────────────

def test_http_conversation_captures_list_item_isolation_and_validation(
    isolated_env: dict[str, Path],
) -> None:
    """Verify read-only GET capture list and item routes enforce isolation and reject blank/missing keys."""
    # TestClient: in-process ASGI HTTP client invoking FastAPI routes against isolated temp SQLite DB
    client = TestClient(app)

    # 1. Empty conversation returns 200 with count 0 and empty list
    empty_res = client.get("/api/agents/ask/conversations/conv-empty/captures")
    assert empty_res.status_code == 200
    assert empty_res.json() == {
        "conversation_id": "conv-empty",
        "count": 0,
        "captures": [],
    }

    # 2. Populate conv-a with tab, web, and email captures, plus conv-b isolation target
    key_tab = conversation_cache.put_capture(
        conversation_id="conv-a",
        source_type="tab",
        title="Tab Spec",
        content="# Tab Spec\n\nVerbatim tab body.",
        source_url="https://example.com/tab-spec",
    )
    key_web = conversation_cache.put_capture(
        conversation_id="conv-a",
        source_type="web",
        title="Web Guide",
        content="Verbatim web markdown body.",
        source_url="https://example.com/web-guide",
    )
    key_email = conversation_cache.put_capture(
        conversation_id="conv-a",
        source_type="email",
        title="Recruiter Follow-up",
        content="Verbatim email body.",
        cache_key="cache://email/msg-42",
    )
    key_b = conversation_cache.put_capture(
        conversation_id="conv-b",
        source_type="tab",
        title="Secret Other Thread Tab",
        content="Strictly isolated from conv-a.",
        source_url="https://example.com/secret-b",
    )

    # 3. List endpoint returns lightweight metadata (omitting raw `content`) scoped strictly to conv-a
    list_res = client.get("/api/agents/ask/conversations/conv-a/captures")
    assert list_res.status_code == 200
    list_payload = list_res.json()
    assert list_payload["conversation_id"] == "conv-a"
    assert list_payload["count"] == 3
    returned_keys = {item["cache_key"] for item in list_payload["captures"]}
    assert returned_keys == {key_tab, key_web, key_email}
    assert key_b not in returned_keys
    assert all("content" not in item for item in list_payload["captures"])

    # 4. Item endpoint fetches verbatim content and metadata using `?key=` query param
    item_res = client.get(
        "/api/agents/ask/conversations/conv-a/captures/item",
        params={"key": key_tab},
    )
    assert item_res.status_code == 200
    item_payload = item_res.json()
    assert item_payload["cache_key"] == key_tab
    assert item_payload["conversation_id"] == "conv-a"
    assert item_payload["source_type"] == "tab"
    assert item_payload["source_url"] == "https://example.com/tab-spec"
    assert item_payload["title"] == "Tab Spec"
    assert item_payload["content"] == "# Tab Spec\n\nVerbatim tab body."
    assert item_payload["char_count"] == len("# Tab Spec\n\nVerbatim tab body.")
    assert item_payload["created_at"]

    # 5. Cross-conversation isolation: requesting conv-b's key inside conv-a returns 404
    cross_res = client.get(
        "/api/agents/ask/conversations/conv-a/captures/item",
        params={"key": key_b},
    )
    assert cross_res.status_code == 404

    # 6. Missing capture key inside conv-a returns 404
    missing_res = client.get(
        "/api/agents/ask/conversations/conv-a/captures/item",
        params={"key": "cache://tab/nonexistent"},
    )
    assert missing_res.status_code == 404

    # 7. Blank/whitespace-only key returns 400
    blank_res = client.get(
        "/api/agents/ask/conversations/conv-a/captures/item",
        params={"key": "   "},
    )
    assert blank_res.status_code == 400


# ── 11. Verbatim Chat Draft Block Cache (`cache://chat`) & Literal Immunity ──

def test_chat_block_extraction_manifest_splice_and_isolation(
    isolated_env: dict[str, Path],
) -> None:
    """Verify `cache://chat` extracts fenced drafts verbatim (incl. 4-backtick nested fences) with strict isolation."""
    nested_draft = (
        "---\n"
        "tags: [instructions]\n"
        "---\n"
        "# Master Draft\n\n"
        "* **Subject:** Human named {user_name}\n"
        "- Syntax note: `` `{{cache:...}}` ``\n\n"
        "```markdown\n"
        "# Inner Example\n"
        "Body inside nested fence.\n"
        "```\n"
        + ("Extra substantive specification line.\n" * 6)
    ).strip()
    tilde_draft = (
        "# Second Tilde Draft\n\n"
        + ("Substantive tilde-fenced draft line for testing extraction.\n" * 6)
    ).strip()
    assistant_msg = (
        "Here are your two drafts:\n\n"
        "### Draft 1: `Master Draft.md`\n"
        f"````markdown\n{nested_draft}\n````\n\n"
        "### Draft 2: `Second Draft.md`\n"
        "```text\nTiny snippet (<200 chars) should stay hidden in manifest\n```\n\n"
        f"~~~markdown\n{tilde_draft}\n~~~\n"
    )

    conv_a = chats_db.create_conversation(title="Draft Chat A")
    conv_b = chats_db.create_conversation(title="Draft Chat B")
    chats_db.log_message(role="user", content="Write two drafts", conversation_id=conv_a)
    msg_a_id = chats_db.log_message(role="assistant", content=assistant_msg, agent="nexus", conversation_id=conv_a)
    chats_db.log_message(
        role="assistant",
        content=f"### Secret B\n```markdown\n{'Secret draft in B. ' * 15}\n```",
        agent="nexus",
        conversation_id=conv_b,
    )

    # 1. `extract_fenced_blocks` assigns stable 1-based `block_index` before `min_chars` filtering
    all_blocks = conversation_cache.extract_fenced_blocks(assistant_msg, min_chars=0)
    assert len(all_blocks) == 3
    assert all_blocks[0]["block_index"] == 1
    assert all_blocks[0]["content"] == nested_draft
    assert all_blocks[2]["block_index"] == 3
    assert all_blocks[2]["content"] == tilde_draft

    # Only blocks >= CHAT_BLOCK_MIN_CHARS appear in `list_chat_blocks`, keeping `b1` and `b3` handles stable
    listed = conversation_cache.list_chat_blocks(conv_a)
    assert [item["cache_key"] for item in listed] == [
        f"cache://chat/m{msg_a_id}-b1",
        f"cache://chat/m{msg_a_id}-b3",
    ]
    assert all("content" not in item for item in listed)

    tok = set_hitl_execution_context(conversation_id=conv_a, thread_id=conv_a)
    try:
        # 2. `read_file("cache://chat")` and `read_file("cache://")` expose chat draft handles without dumping raw bodies
        chat_manifest = shared_module.read_file.invoke({"file_path": "cache://chat"})
        assert f"cache://chat/m{msg_a_id}-b1" in chat_manifest
        assert f"cache://chat/m{msg_a_id}-b3" in chat_manifest
        assert "Body inside nested fence." not in chat_manifest

        combined_manifest = shared_module.read_file.invoke({"file_path": "cache://"})
        assert f"cache://chat/m{msg_a_id}-b1" in combined_manifest

        # Adding an external capture keeps `# Cached External Captures (1 item(s)` header + chat section
        conversation_cache.put_capture(
            conversation_id=conv_a,
            source_type="web",
            title="External Ref",
            content="External body",
            source_url="https://example.com/ref",
        )
        both_manifest = shared_module.read_file.invoke({"file_path": "cache://"})
        assert "Cached External Captures (1 item(s)" in both_manifest
        assert f"cache://chat/m{msg_a_id}-b1" in both_manifest

        # 3. `read_file` slicing & `hydrate_subagent_context_files` resolve `cache://chat/m<id>-b<n>`
        sliced = shared_module.read_file.invoke(
            {"file_path": f"cache://chat/m{msg_a_id}-b1", "start_line": 6, "end_line": 6}
        )
        assert "{user_name}" in sliced

        prehydrated, hydr_err = shared_module.hydrate_subagent_context_files(
            [f"cache://chat/m{msg_a_id}-b1"]
        )
        assert hydr_err is None
        assert prehydrated is not None
        assert nested_draft in prehydrated

        # 4. `create_file` & `modify_file` splice `{{cache:chat/m<id>-b<n>}}` 100% verbatim
        create_res = shared_module.create_file.invoke(
            {
                "file_path": "Draft - Master.md",
                "content": f"{{{{cache:chat/m{msg_a_id}-b1}}}}",
                "reasoning": "Copy draft verbatim from chat",
            }
        )
        assert "spliced 1 cached capture(s) verbatim" in create_res
        staged = hq.get_pending_for_file("Vault/Draft - Master.md")
        assert staged is not None
        assert staged["proposed_content"] == nested_draft

        # 5. Cross-conversation isolation: conv_a cannot read or splice conv_b's chat blocks
        conv_b_blocks = conversation_cache.list_chat_blocks(conv_b)
        assert len(conv_b_blocks) == 1
        secret_key = conv_b_blocks[0]["cache_key"]
        secret_short = secret_key[len("cache://") :]

        iso_read = shared_module.read_file.invoke({"file_path": secret_key})
        assert f"not found in conversation `{conv_a}`" in iso_read

        iso_splice = shared_module.create_file.invoke(
            {
                "file_path": "0. Inbox/Leak.md",
                "content": f"{{{{cache:{secret_short}}}}}",
                "reasoning": "Should not leak conv_b chat block",
            }
        )
        assert iso_splice.startswith("Error: Unresolved cache placeholder(s)")
    finally:
        reset_hitl_execution_context(tok)


def test_resolve_cache_placeholders_literal_doc_immunity(
    isolated_env: dict[str, Path],
) -> None:
    """Verify inline-backticked and metasyntax `{{cache:...}}` examples pass through while active missing keys fail fast."""
    conv_id = chats_db.create_conversation(title="Literal Doc Test")
    draft_body = "# Real Draft\n\n" + ("Actual draft content line.\n" * 10)
    msg_id = chats_db.log_message(
        role="assistant",
        content=f"### Draft\n```markdown\n{draft_body}\n```",
        agent="nexus",
        conversation_id=conv_id,
    )

    tok = set_hitl_execution_context(conversation_id=conv_id, thread_id=conv_id)
    try:
        # 1. Documentation tokens (backticked or metasyntax) stage cleanly with zero error
        doc_content = (
            "---\ntags: [instructions]\n---\n"
            "- Never leak `{{cache:...}}` or `{{cache:tab/example}}`.\n"
            "- Syntax: {{cache:<key>}} or {{cache:<type>/<slug>}} or {{cache:*}} or {{cache:...}}.\n"
        )
        ok_res = shared_module.create_file.invoke(
            {
                "file_path": "Draft - Docs.md",
                "content": doc_content,
                "reasoning": "Stage instruction doc mentioning cache syntax",
            }
        )
        assert "✅ File creation staged to HITL queue" in ok_res
        assert "spliced" not in ok_res
        staged_doc = hq.get_pending_for_file("Vault/Draft - Docs.md")
        assert staged_doc is not None
        assert staged_doc["proposed_content"] == doc_content

        # 2. Mixed doc: backticked literal `{{cache:...}}` + real {{cache:chat/m<id>-b1}} expands ONLY the real key
        mixed_res = shared_module.create_file.invoke(
            {
                "file_path": "Draft - Mixed.md",
                "content": f"Example: `{{{{cache:...}}}}`\n\n{{{{cache:chat/m{msg_id}-b1}}}}",
                "reasoning": "Mixed literal doc token and active chat splice",
            }
        )
        assert "spliced 1 cached capture(s) verbatim" in mixed_res
        staged_mixed = hq.get_pending_for_file("Vault/Draft - Mixed.md")
        assert staged_mixed is not None
        assert "Example: `{{cache:...}}`" in staged_mixed["proposed_content"]
        assert draft_body in staged_mixed["proposed_content"]

        # 3. Missing active key MUST still fail fast without staging
        bad_res = shared_module.create_file.invoke(
            {
                "file_path": "Draft - Missing.md",
                "content": "Broken: {{cache:chat/m99999-b1}}",
                "reasoning": "Should fail fast",
            }
        )
        assert bad_res.startswith("Error: Unresolved cache placeholder(s)")
        assert hq.get_pending_for_file("Vault/Draft - Missing.md") is None
    finally:
        reset_hitl_execution_context(tok)
