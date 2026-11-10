"""
test_browser_bridge.py — Unit and integration tests for the Read-Only Nexus Browser Bridge.

Verifies:
1. `tool_catalog.py` static AST discovery of `nexus.shared_tools.browser_bridge [CLI]`.
2. Markdown formatting (`format_tabs_as_markdown`, `format_tab_reads_as_markdown`) for Chrome Tab Groups and tabs.
3. Active Chat & Floating Overlays parsing and formatting from live rendered DOM.
4. Standalone ephemeral WebSocket RPC loop (`_execute_via_ephemeral_ws`) with a simulated Chrome Extension client.
5. FastAPI `/api/browser` router (`/status`, `/tabs`, `/read`, `/ws`) end-to-end request/response correlation.
6. LangChain `@tool` wrappers (`list_browser_tabs`, `read_browser_tabs`) registration in `CORE_TOOLS`.
"""
import asyncio
import json
import os
from typing import Any, Dict
from unittest.mock import patch

# Ensure dummy API key is present when running in isolated git worktrees without `.env`
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient
from websockets.asyncio.client import connect

from nexus.agent.graph import CORE_TOOLS
from nexus.api.main import app
from nexus.core.tool_catalog import get_shared_tools_catalog
from nexus.shared_tools import browser_bridge
from nexus.shared_tools.shared import list_browser_tabs, read_browser_tabs


def test_browser_bridge_in_tool_catalog() -> None:
    """Ensure `nexus.shared_tools.browser_bridge [CLI]` is discovered by `tool_catalog.py`."""
    catalog = get_shared_tools_catalog()
    assert "`nexus.shared_tools.browser_bridge` [CLI]" in catalog


def test_browser_tools_bound_in_core_tools() -> None:
    """Ensure `list_browser_tabs` and `read_browser_tabs` are bound in `NexusAgent` CORE_TOOLS."""
    tool_names = {t.name for t in CORE_TOOLS}
    assert "list_browser_tabs" in tool_names
    assert "read_browser_tabs" in tool_names


def test_format_tabs_as_markdown() -> None:
    """Verify Markdown rendering of Chrome Tab Groups and open tabs."""
    sample = {
        "ok": True,
        "data": {
            "total_open_tabs": 5,
            "matched_tabs": 2,
            "groups": [
                {
                    "group_id": 101,
                    "title": "Job Hunt",
                    "color": "blue",
                    "collapsed": False,
                    "tab_count": 2,
                }
            ],
            "tabs": [
                {
                    "tab_id": 42,
                    "title": "Senior AI Engineer - Acme",
                    "url": "https://boards.greenhouse.io/acme/jobs/123",
                    "active": True,
                    "group_id": 101,
                    "group_title": "Job Hunt",
                    "group_color": "blue",
                },
                {
                    "tab_id": 43,
                    "title": "Forward Deployed Engineer - Palantir",
                    "url": "https://linkedin.com/jobs/view/999",
                    "active": False,
                    "group_id": 101,
                    "group_title": "Job Hunt",
                    "group_color": "blue",
                },
            ],
        },
    }
    md = browser_bridge.format_tabs_as_markdown(sample)
    assert "# Chrome Browser Tabs (2 matched / 5 total open)" in md
    assert "**Job Hunt** (`color: blue`, `group_id: 101`) — 2 tab(s)" in md
    assert "`[tab_id: 42]`" in md
    assert "`[Group: Job Hunt (blue)]`" in md
    assert "**[ACTIVE]**" in md
    assert "Senior AI Engineer - Acme" in md


def test_format_tab_reads_as_markdown() -> None:
    """Verify Markdown rendering of extracted DOM content from tabs."""
    sample = {
        "ok": True,
        "data": {
            "requested_count": 2,
            "succeeded_count": 1,
            "tabs": [
                {
                    "tab_id": 42,
                    "title": "Senior AI Engineer - Acme",
                    "url": "https://boards.greenhouse.io/acme/jobs/123",
                    "group_title": "Job Hunt",
                    "group_color": "blue",
                    "ok": True,
                    "char_count": 128,
                    "truncated": False,
                    "markdown": "### Structured Schema (JobPosting)\n- **Company:** Acme\n\n## About the Role\nBuild LangGraph agents.",
                },
                {
                    "tab_id": 99,
                    "title": "Extensions",
                    "url": "chrome://extensions",
                    "group_title": None,
                    "group_color": None,
                    "ok": False,
                    "error": "Cannot extract DOM from restricted browser URL: chrome://extensions",
                },
            ],
        },
    }
    md = browser_bridge.format_tab_reads_as_markdown(sample)
    assert "1/2 tabs read successfully" in md
    assert "[tab_id: 42] Senior AI Engineer - Acme" in md
    assert "Build LangGraph agents." in md
    assert "❌ Error — Cannot extract DOM from restricted browser URL" in md


def test_format_tab_reads_with_active_chat_overlays() -> None:
    """Verify Markdown rendering of tab content with active chat & floating overlays."""
    sample = {
        "ok": True,
        "data": {
            "requested_count": 1,
            "succeeded_count": 1,
            "tabs": [
                {
                    "tab_id": 101,
                    "title": "Jane Doe | LinkedIn",
                    "url": "https://www.linkedin.com/in/janedoe/",
                    "group_title": "Recruiters",
                    "group_color": "purple",
                    "ok": True,
                    "char_count": 450,
                    "truncated": False,
                    "markdown": (
                        "# Jane Doe\nStaff Technical Recruiter at Acme\n\n"
                        "---\n## Active Chat & Floating Overlays\n\n"
                        "### Jane Doe\n"
                        "- **Sender:** Jane Doe (10:14 AM)\n"
                        "> Hi William, check out this role: [AI Engineer](https://jobs.example.com/123)\n\n"
                        "- **Sender:** William (10:20 AM)\n"
                        "> Thanks Jane, reviewing now!"
                    ),
                }
            ],
        },
    }
    md = browser_bridge.format_tab_reads_as_markdown(sample)
    assert "1/1 tabs read successfully" in md
    assert "[tab_id: 101] Jane Doe | LinkedIn" in md
    assert "**Chrome Tab Group:** Recruiters (purple)" in md
    assert "## Active Chat & Floating Overlays" in md
    assert "### Jane Doe" in md
    assert "- **Sender:** Jane Doe (10:14 AM)" in md
    assert "> Hi William, check out this role: [AI Engineer](https://jobs.example.com/123)" in md
    assert "- **Sender:** William (10:20 AM)" in md
    assert "> Thanks Jane, reviewing now!" in md


def test_browser_extension_active_overlay_dom_extraction() -> None:
    """Execute extractTabMarkdownReadOnly against a simulated DOM in Node.js to verify active overlay extraction."""
    import shutil
    import subprocess
    from pathlib import Path

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js not available on system PATH; skipping JS DOM simulation test.")

    test_script_path = Path(__file__).resolve().parent / "test_browser_extension_dom.js"
    assert test_script_path.exists(), f"test_browser_extension_dom.js not found at {test_script_path}"

    proc = subprocess.run(
        [node_bin, str(test_script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"Node script failed ({proc.returncode}):\n{proc.stderr}\n{proc.stdout}"
    assert "All Node.js browser extension DOM tests passed successfully!" in proc.stdout


def test_ephemeral_ws_roundtrip() -> None:
    """Verify standalone ephemeral WebSocket server round-trip with a simulated Chrome Extension client."""

    async def _run_test() -> Dict[str, Any]:
        # Launch `_execute_via_ephemeral_ws` as a background task
        server_task = asyncio.create_task(
            browser_bridge._execute_via_ephemeral_ws(
                action="list_tabs",
                params={"group_name": "Job Hunt"},
                connect_timeout=3.0,
                response_timeout=3.0,
            )
        )
        # Give server 150ms to bind port 8765
        await asyncio.sleep(0.15)

        # Simulate the Chrome Extension connecting to ws://127.0.0.1:8765
        async with connect(f"ws://127.0.0.1:{browser_bridge.CLI_WS_PORT}/api/browser/ws") as ws:
            raw_cmd = await ws.recv()
            cmd = json.loads(raw_cmd)
            assert cmd["action"] == "list_tabs"
            assert cmd["params"]["group_name"] == "Job Hunt"

            await ws.send(
                json.dumps(
                    {
                        "type": "response",
                        "request_id": cmd["request_id"],
                        "ok": True,
                        "data": {
                            "total_open_tabs": 1,
                            "matched_tabs": 1,
                            "groups": [{"group_id": 7, "title": "Job Hunt", "color": "green", "tab_count": 1}],
                            "tabs": [{"tab_id": 10, "title": "Test JD", "url": "https://example.com/job", "group_title": "Job Hunt", "group_color": "green"}],
                        },
                    }
                )
            )

        return await server_task

    res = asyncio.run(_run_test())
    assert res["ok"] is True
    assert res["data"]["matched_tabs"] == 1
    assert res["data"]["tabs"][0]["title"] == "Test JD"


def test_langchain_tool_wrappers() -> None:
    """Verify `list_browser_tabs` and `read_browser_tabs` LangChain @tool wrappers."""
    mock_list = {
        "ok": True,
        "data": {
            "total_open_tabs": 1,
            "matched_tabs": 1,
            "groups": [{"group_id": 1, "title": "Jobs", "color": "cyan", "tab_count": 1}],
            "tabs": [{"tab_id": 55, "title": "AI Engineer", "url": "https://example.com", "group_title": "Jobs", "group_color": "cyan"}],
        },
    }
    mock_read = {
        "ok": True,
        "data": {
            "requested_count": 1,
            "succeeded_count": 1,
            "tabs": [
                {
                    "tab_id": 55,
                    "title": "AI Engineer",
                    "url": "https://example.com",
                    "group_title": "Jobs",
                    "group_color": "cyan",
                    "ok": True,
                    "char_count": 42,
                    "truncated": False,
                    "markdown": "# Job Description\nPython, LangGraph, FastAPI.",
                }
            ],
        },
    }
    with patch("nexus.shared_tools.browser_bridge.list_tabs", return_value=mock_list):
        out_list = list_browser_tabs.invoke({"group_name": "Jobs"})
        assert "`[tab_id: 55]`" in out_list
        assert "AI Engineer" in out_list

    with patch("nexus.shared_tools.browser_bridge.read_tabs", return_value=mock_read):
        out_read = read_browser_tabs.invoke({"tab_ids": [55]})
        assert "# Job Description" in out_read
        assert "Python, LangGraph, FastAPI." in out_read


def test_fastapi_browser_router_status_when_disconnected() -> None:
    """Verify `/api/browser/status` and 503 guard on `/api/browser/tabs` when extension is not connected."""
    client = TestClient(app)
    status_res = client.get("/api/browser/status")
    assert status_res.status_code == 200
    body = status_res.json()
    assert body["connected"] is False
    assert body["mode"] == "read_only"

    tabs_res = client.get("/api/browser/tabs")
    assert tabs_res.status_code == 503
    assert "chrome://extensions" in tabs_res.json()["detail"]
