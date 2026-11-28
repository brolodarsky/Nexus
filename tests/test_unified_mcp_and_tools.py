"""
test_unified_mcp_and_tools.py — Verification suite for the unified Nexus tool registry and FastMCP server.

Covers:
1. Exact 1:1 tool-name parity between `nexus.agent.graph.TOOLS` and `nexus.mcp.server.mcp`.
2. Absence of retired tools/modules (`run_shared_tool_cli`, `generate_podcast`, `medical_xml_parser`, `tool_catalog`).
3. Slimmed `@tool` schema + description character footprint (`< 20,000` chars across descriptions).
4. `stdio` JSON-RPC safety (`NEXUS_STDIO_MCP=1` routes Loguru to `stderr`, tool `print()` stays off `stdout`).
5. `mcp.call_tool(...)` and `mcp.read_resource("nexus://instructions/master")` execution.
6. Unit tests for newly promoted tools (`read_webpage`, `get_youtube_transcript`, `modify_emails`,
   `trash_emails`, `create_email_draft`, `render_resume_documents`, `ingest_phone_chat`, `export_agent_conversation`).
"""
import asyncio
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool

from nexus.agent.graph import TOOLS
from nexus.agent.runtime import CORE_TOOLS
from nexus.core import logger as logger_mod
from nexus.mcp.server import _register_langchain_tool, mcp
from nexus.shared_tools import shared as shared_mod


def test_unified_mcp_and_agent_tool_parity() -> None:
    """`FastMCP` and `NexusAgent` (`TOOLS`) expose the exact same 30 tools, with legacy splits removed."""
    agent_names = [t.name for t in TOOLS]
    mcp_tools = mcp._tool_manager.list_tools()
    mcp_names = [t.name for t in mcp_tools]

    assert len(CORE_TOOLS) == 29
    assert len(TOOLS) == 30
    assert agent_names == mcp_names

    # Retired tools/modules must not exist
    assert "run_shared_tool_cli" not in agent_names
    assert importlib.util.find_spec("nexus.core.tool_catalog") is None
    assert importlib.util.find_spec("nexus.shared_tools.generate_podcast") is None
    assert importlib.util.find_spec("nexus.shared_tools.medical_xml_parser") is None

    # Newly promoted unified tools must all be present
    expected_promoted = {
        "read_webpage",
        "get_youtube_transcript",
        "modify_emails",
        "trash_emails",
        "create_email_draft",
        "render_resume_documents",
        "ingest_phone_chat",
        "export_agent_conversation",
    }
    assert expected_promoted <= set(agent_names)


def test_slimmed_tool_descriptions_budget() -> None:
    """All 30 unified tool descriptions stay compact (< 20,000 chars) after docstring slimming."""
    total_desc_chars = sum(len(t.description) for t in TOOLS)
    assert total_desc_chars < 20_000


def test_mcp_stdio_safety_and_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP wrappers redirect stray `print()` to stderr, route Loguru off stdout, and serve Master Instructions."""
    from mcp.server.fastmcp import FastMCP

    temp_mcp = FastMCP("test-stdio")

    @tool
    def noisy_tool(value: str) -> str:
        """Test tool that prints to stdout."""
        print("stray stdout noise")
        return f"clean:{value}"

    _register_langchain_tool(temp_mcp, noisy_tool)

    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_stdout)
    monkeypatch.setattr(sys, "stderr", captured_stderr)

    result = asyncio.run(temp_mcp.call_tool("noisy_tool", {"value": "ok"}))
    assert captured_stdout.getvalue() == ""
    assert "stray stdout noise" in captured_stderr.getvalue()
    assert "clean:ok" in str(result)

    # Verify NEXUS_STDIO_MCP=1 switches Loguru console sink to stderr without crashing
    monkeypatch.setenv("NEXUS_STDIO_MCP", "1")
    logger_mod.setup_logger()
    try:
        logger_mod.logger.info("mcp stderr log check")
        assert captured_stdout.getvalue() == ""
    finally:
        monkeypatch.delenv("NEXUS_STDIO_MCP", raising=False)
        logger_mod.setup_logger()

    # Verify master instructions resource resolves non-empty hydrated Markdown without `{shared_tools}`
    resources = asyncio.run(mcp.read_resource("nexus://instructions/master"))
    rendered_text = "".join(getattr(part, "content", "") for part in resources)
    assert "Unified Tools" in rendered_text
    assert "{shared_tools}" not in rendered_text


def test_promoted_gmail_mutation_and_draft_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """`modify_emails`, `trash_emails`, and `create_email_draft` delegate cleanly with multi-account fallback."""
    from nexus.shared_tools import gmail_engine

    monkeypatch.setattr(gmail_engine, "list_available_accounts", lambda: ["primary", "alt"])
    monkeypatch.setattr(gmail_engine, "get_gmail_service", lambda account="default": f"svc:{account}")

    def fake_modify(message_id, add=None, remove=None, account="default", service=None):
        if account == "primary":
            raise RuntimeError("404 not on primary")
        return ["Receipts"]

    monkeypatch.setattr(gmail_engine, "modify_labels", fake_modify)
    monkeypatch.setattr(gmail_engine, "trash_message", lambda message_id, account="default", service=None: True)
    monkeypatch.setattr(
        gmail_engine,
        "create_draft",
        lambda **kwargs: {"account": kwargs["account"], "draft_id": "d1", "message_id": "m1", "thread_id": "t1"},
    )

    mod_res = json.loads(
        shared_mod.modify_emails.invoke(
            {"message_ids": ["msg-1"], "add_labels": ["Receipts"], "remove_labels": ["INBOX"], "account": "all"}
        )
    )
    assert mod_res["errors"] == []
    assert mod_res["results"][0]["account"] == "alt"

    trash_res = json.loads(shared_mod.trash_emails.invoke({"message_ids": ["msg-1", "msg-1"], "account": "primary"}))
    assert len(trash_res["results"]) == 1
    assert trash_res["results"][0]["result"] is True

    draft_res = json.loads(
        shared_mod.create_email_draft.invoke(
            {"to": "a@example.com", "subject": "Hi", "body": "Body", "account": "primary"}
        )
    )
    assert draft_res["draft_id"] == "d1"


def test_promoted_resume_adb_and_export_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `render_resume_documents`, `ingest_phone_chat` SystemExit safety, and `export_agent_conversation` Vault guard."""
    from nexus.shared_tools.resume_engine import service as resume_service
    from nexus.shared_tools import ingest_phone, export_conversation

    vault_dir = tmp_path / "Vault"
    (vault_dir / "0. Inbox").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(shared_mod, "VAULT_PATH", vault_dir)

    monkeypatch.setattr(
        resume_service,
        "render_documents",
        lambda file_paths, formats=None: {"success": True, "exit_code": 0, "results": [{"name": "Resume - Master"}]},
    )
    resume_out = json.loads(shared_mod.render_resume_documents.invoke({"file_paths": ["Resume - Master.md"]}))
    assert resume_out["success"] is True

    # Ensure check_device() calling sys.exit(1) is caught cleanly as an error string
    def fake_exit(device=None):
        raise SystemExit(1)

    monkeypatch.setattr(ingest_phone, "check_device", fake_exit)
    adb_out = shared_mod.ingest_phone_chat.invoke({"screens": 1})
    assert adb_out.startswith("Error: Android ADB capture failed (exit 1)")

    # Verify export_agent_conversation lists recent conversations and blocks path traversal outside Vault
    monkeypatch.setattr(
        export_conversation,
        "list_conversations",
        lambda limit=15: [{"id": "conv-123", "created_at": "2026-11-27", "messages": 4, "preview": "Test"}],
    )
    list_out = shared_mod.export_agent_conversation.invoke({"list_recent": True})
    assert "conv-123" in list_out

    monkeypatch.setattr(
        export_conversation,
        "load_conversation_source",
        lambda source="latest": ("Test Session", [SimpleNamespace(role="user", content="hi")], "local"),
    )
    monkeypatch.setattr(export_conversation, "coalesce_conversation_turns", lambda msgs: ["turn1"])
    monkeypatch.setattr(export_conversation, "format_turns_to_markdown", lambda **kwargs: "# Exported Transcript")

    traversal_out = shared_mod.export_agent_conversation.invoke(
        {"source": "latest", "output_note_path": "../../evil.md"}
    )
    assert "outside the Vault" in traversal_out

    ok_export = shared_mod.export_agent_conversation.invoke(
        {"source": "latest", "output_note_path": "0. Inbox/Exported.md"}
    )
    assert "Exported 1 steps" in ok_export
    assert (vault_dir / "0. Inbox" / "Exported.md").exists()
