"""
browser_bridge.py — Read-Only Chrome Browser & Tab Group Bridge for the Nexus Engine.

Connects to the local unpacked Chrome Extension (`src/nexus/shared_tools/browser_extension/`)
to list open tabs, inspect native Chrome Tab Groups (`chrome.tabGroups`), and extract clean
Markdown from the live rendered DOM of authenticated tabs with zero vision tokens and zero
anti-bot network footprint.
"""
# argparse: Standard library CLI argument parser for `python -m nexus.shared_tools.browser_bridge`
import argparse
# asyncio: Standard library async I/O runtime used for standalone WebSocket server fallback
import asyncio
import json
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Coroutine, Dict, List, Optional

# httpx: Modern HTTP client used to query the FastAPI `/api/browser` relay when `start.ps1` is running
import httpx
# websockets: Standards-compliant WebSocket library used for standalone CLI mode when FastAPI is offline
from websockets.asyncio.server import ServerConnection, serve

from nexus.core.constants import PROJECT_ROOT

# Loopback URLs and ports for communicating with the Chrome Extension
FASTAPI_BASE_URL = "http://127.0.0.1:8000/api/browser"
CLI_WS_HOST = "127.0.0.1"
CLI_WS_PORT = 8765
API_WS_PORT = 8000
EXTENSION_DIR: Path = PROJECT_ROOT / "src" / "nexus" / "shared_tools" / "browser_extension"


# ── Event Loop Execution Helper ──────────────────────────────────────────────

# Runs an async coroutine (`Coroutine[Any, Any, dict[str, Any]]`) synchronously whether or not
# the calling thread already has an active asyncio event loop.
def _run_coro_sync(coro: Coroutine[Any, Any, Dict[str, Any]]) -> Dict[str, Any]:
    """Executes `coro` synchronously, isolating in a worker thread if an event loop is already running."""
    try:
        asyncio.get_running_loop()
        loop_running = True
    except RuntimeError:
        loop_running = False

    if not loop_running:
        return asyncio.run(coro)

    # If called from inside an active async event loop, run `asyncio.run(coro)` in a dedicated thread
    result_box: Dict[str, Any] = {}
    error_box: List[BaseException] = []

    def _runner() -> None:
        try:
            result_box["value"] = asyncio.run(coro)
        except BaseException as exc:
            error_box.append(exc)

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    worker.join()
    if error_box:
        raise error_box[0]
    return result_box.get("value", {})


# ── Standalone Ephemeral WebSocket RPC Relay ─────────────────────────────────

# Spins up a short-lived loopback WebSocket server on `127.0.0.1:8765` (and `8000` if free)
# when the main FastAPI server (`start.ps1`) is not running, waits for the Chrome Extension's
# 2-second keepalive heartbeat to connect, executes a single read-only RPC command, and closes.
async def _execute_via_ephemeral_ws(
    action: str,
    params: Dict[str, Any],
    connect_timeout: float = 5.0,
    response_timeout: float = 20.0,
) -> Dict[str, Any]:
    """Executes a single read-only browser command by hosting an ephemeral loopback WebSocket server."""
    loop = asyncio.get_running_loop()
    # Future resolved as soon as the Chrome Extension connects and replies to our `request_id`
    result_future: asyncio.Future[Dict[str, Any]] = loop.create_future()
    request_id = str(uuid.uuid4())
    command_sent = False

    # Handler invoked by `websockets.serve` when the Chrome Extension connects to `/api/browser/ws`
    async def _ws_handler(websocket: ServerConnection) -> None:
        nonlocal command_sent
        try:
            # Send our RPC request immediately upon connection
            if not command_sent:
                command_sent = True
                await websocket.send(
                    json.dumps(
                        {
                            "request_id": request_id,
                            "action": action,
                            "params": params,
                        }
                    )
                )

            # Read incoming frames (`hello`, `heartbeat`, `response`) until matching `request_id` arrives
            async for raw_frame in websocket:
                try:
                    msg = json.loads(raw_frame)
                except Exception:
                    continue

                if msg.get("type") == "response" and msg.get("request_id") == request_id:
                    if not result_future.done():
                        result_future.set_result(msg)
                    return
        except Exception as exc:
            if not result_future.done():
                result_future.set_exception(exc)

    servers = []
    # Bind port 8765 (dedicated CLI bridge port) and also port 8000 if FastAPI is completely offline
    for port in (CLI_WS_PORT, API_WS_PORT):
        try:
            srv = await serve(_ws_handler, CLI_WS_HOST, port)
            servers.append(srv)
        except OSError:
            # Port is already bound by another process (e.g. FastAPI on 8000); skip cleanly
            continue

    if not servers:
        return {
            "ok": False,
            "error": (
                f"Could not bind local WebSocket bridge ports ({CLI_WS_PORT}, {API_WS_PORT}) "
                f"and FastAPI `/api/browser` was unreachable."
            ),
        }

    try:
        # Wait up to `connect_timeout + response_timeout` depending on whether extension connected
        total_wait = connect_timeout if action == "ping" else (connect_timeout + response_timeout)
        response = await asyncio.wait_for(result_future, timeout=total_wait)
        if not response.get("ok", False):
            return {
                "ok": False,
                "error": response.get("error") or f"Chrome Extension reported error for '{action}'.",
            }
        return {
            "ok": True,
            "transport": f"ephemeral_ws:{CLI_WS_PORT}",
            "data": response.get("data") or {},
        }
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "error": (
                "Timed out waiting for the Nexus Browser Bridge Chrome Extension to connect.\n"
                "Setup Instructions (one-time, takes 15 seconds):\n"
                "  1. Open Chrome and navigate to: chrome://extensions\n"
                "  2. Toggle 'Developer mode' ON (top-right corner)\n"
                "  3. Click 'Load unpacked' (top-left) and select this folder:\n"
                f"     {EXTENSION_DIR}"
            ),
        }
    except Exception as exc:
        return {"ok": False, "error": f"Standalone WebSocket bridge error: {exc}"}
    finally:
        for srv in servers:
            srv.close()
            await srv.wait_closed()


# ── Dual-Mode Transport Dispatcher (FastAPI Relay -> Ephemeral WS Fallback) ──

def _dispatch_browser_command(
    action: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """Dispatches a read-only browser command via FastAPI (`localhost:8000`) if connected, else standalone WS (`8765`).

    Args:
        action: One of `"ping"`, `"list_tabs"`, or `"read_tabs"`.
        params: Optional filter/extraction parameters dictionary.
        timeout: Maximum timeout in seconds for the command.

    Returns:
        Dictionary with `{"ok": bool, "data": ..., "error": ...}`.
    """
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}

    # Phase 1: Probe FastAPI `/api/browser/status` (fast 0.8s timeout) to see if `start.ps1` is active
    try:
        with httpx.Client(timeout=0.8) as probe_client:
            status_resp = probe_client.get(f"{FASTAPI_BASE_URL}/status")
            if status_resp.status_code == 200:
                status_json = status_resp.json()
                if status_json.get("connected"):
                    # FastAPI has an active Chrome Extension socket! Route through REST API.
                    with httpx.Client(timeout=timeout) as api_client:
                        if action == "ping":
                            return {
                                "ok": True,
                                "transport": "fastapi:8000",
                                "data": status_json.get("metadata") or status_json,
                            }
                        elif action == "list_tabs":
                            r = api_client.get(f"{FASTAPI_BASE_URL}/tabs", params=clean_params)
                        elif action == "read_tabs":
                            r = api_client.post(f"{FASTAPI_BASE_URL}/read", json=clean_params)
                        else:
                            return {"ok": False, "error": f"Unknown action: {action}"}

                        if r.status_code == 200:
                            return {
                                "ok": True,
                                "transport": "fastapi:8000",
                                "data": r.json(),
                            }
                        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text
                        return {"ok": False, "error": f"FastAPI browser bridge error ({r.status_code}): {detail}"}
    except Exception:
        # FastAPI is not running or not reachable; fall through seamlessly to Phase 2
        pass

    # Phase 2: Spin up ephemeral loopback WebSocket listener so CLI works standalone without `start.ps1`
    return _run_coro_sync(
        _execute_via_ephemeral_ws(
            action=action,
            params=clean_params,
            connect_timeout=4.5,
            response_timeout=timeout,
        )
    )


# ── Public Pure-Python API ───────────────────────────────────────────────────

def get_bridge_status() -> Dict[str, Any]:
    """Checks connection status of the read-only Chrome Extension bridge."""
    res = _dispatch_browser_command("ping", timeout=5.0)
    if not res.get("ok"):
        return {
            "connected": False,
            "mode": "read_only",
            "extension_dir": str(EXTENSION_DIR),
            "error": res.get("error"),
        }
    return {
        "connected": True,
        "mode": "read_only",
        "transport": res.get("transport"),
        "extension_dir": str(EXTENSION_DIR),
        "metadata": res.get("data", {}),
    }


def list_tabs(
    group_name: Optional[str] = None,
    query: Optional[str] = None,
    active_only: bool = False,
) -> Dict[str, Any]:
    """Lists open Chrome tabs and native Chrome Tab Groups (`chrome.tabGroups`).

    Args:
        group_name: Optional case-insensitive Chrome Tab Group name filter (e.g. "Jobs").
        query: Optional case-insensitive substring filter matching tab title, URL, or group name.
        active_only: If True, returns only the currently focused tab in each window.
    """
    return _dispatch_browser_command(
        action="list_tabs",
        params={
            "group_name": group_name,
            "query": query,
            "active_only": active_only,
        },
        timeout=10.0,
    )


def read_tabs(
    tab_ids: Optional[List[int]] = None,
    group_name: Optional[str] = None,
    query: Optional[str] = None,
    active_only: bool = False,
    max_chars: int = 20000,
) -> Dict[str, Any]:
    """Extracts clean Markdown from the live rendered DOM of matching Chrome tabs (strictly read-only).

    Args:
        tab_ids: Optional list of integer Chrome `tab_id` values to read.
        group_name: Optional Chrome Tab Group title to read all tabs from (case-insensitive).
        query: Optional substring filter matching tab title or URL.
        active_only: If True, reads only the currently active tab.
        max_chars: Maximum characters of Markdown to return per tab (default: 20,000).
    """
    return _dispatch_browser_command(
        action="read_tabs",
        params={
            "tab_ids": tab_ids,
            "group_name": group_name,
            "query": query,
            "active_only": active_only,
            "max_chars": max_chars,
        },
        timeout=25.0,
    )


# ── Markdown Formatters for Agent & CLI Consumption ──────────────────────────

def format_tabs_as_markdown(result: Dict[str, Any]) -> str:
    """Formats the output of `list_tabs()` into a clean, token-efficient Markdown report."""
    if not result.get("ok"):
        return f"❌ **Nexus Browser Bridge Error:**\n{result.get('error', 'Unknown error')}"

    data = result.get("data") or {}
    groups: List[Dict[str, Any]] = data.get("groups") or []
    tabs: List[Dict[str, Any]] = data.get("tabs") or []
    total_open = data.get("total_open_tabs", len(tabs))
    matched = data.get("matched_tabs", len(tabs))

    lines: List[str] = [
        f"# Chrome Browser Tabs ({matched} matched / {total_open} total open)",
    ]

    # 1. Render Chrome Tab Groups overview if any exist
    if groups:
        lines.append("\n## Chrome Tab Groups")
        for g in groups:
            g_title = g.get("title") or "(Untitled Group)"
            g_color = g.get("color") or "grey"
            g_count = g.get("tab_count", 0)
            collapsed = " [collapsed]" if g.get("collapsed") else ""
            lines.append(f"- **{g_title}** (`color: {g_color}`, `group_id: {g.get('group_id')}`) — {g_count} tab(s){collapsed}")
    else:
        lines.append("\n*No Chrome Tab Groups currently open.*")

    # 2. Render matched tabs
    if not tabs:
        lines.append("\n*No open tabs matched the filter criteria.*")
        return "\n".join(lines)

    lines.append("\n## Open Tabs")
    for t in tabs:
        tid = t.get("tab_id")
        title = (t.get("title") or "(Untitled)").strip()
        url = t.get("url") or ""
        g_title = t.get("group_title")
        g_color = t.get("group_color")
        active_badge = " **[ACTIVE]**" if t.get("active") else ""
        group_badge = f" `[Group: {g_title} ({g_color})]`" if g_title else " `[Ungrouped]`"
        lines.append(f"- **`[tab_id: {tid}]`**{group_badge}{active_badge} **{title}**\n  - URL: {url}")

    return "\n".join(lines)


def format_tab_reads_as_markdown(result: Dict[str, Any]) -> str:
    """Formats the output of `read_tabs()` into structured Markdown blocks per tab."""
    if not result.get("ok"):
        return f"❌ **Nexus Browser Bridge Error:**\n{result.get('error', 'Unknown error')}"

    data = result.get("data") or {}
    tabs: List[Dict[str, Any]] = data.get("tabs") or []
    req_count = data.get("requested_count", len(tabs))
    ok_count = data.get("succeeded_count", 0)

    if not tabs:
        return "No matching Chrome tabs found to read."

    blocks: List[str] = [
        f"# Extracted Chrome Tab Content ({ok_count}/{req_count} tabs read successfully)"
    ]

    for idx, t in enumerate(tabs, start=1):
        tid = t.get("tab_id")
        title = (t.get("title") or "(Untitled)").strip()
        url = t.get("url") or ""
        g_title = t.get("group_title")
        group_line = f"- **Chrome Tab Group:** {g_title} ({t.get('group_color')})\n" if g_title else ""

        header = (
            f"## {idx}. [tab_id: {tid}] {title}\n"
            f"- **URL:** {url}\n"
            f"{group_line}"
        )

        if not t.get("ok"):
            blocks.append(f"{header}- **Status:** ❌ Error — {t.get('error')}\n")
            continue

        char_count = t.get("char_count", 0)
        trunc_note = " (truncated)" if t.get("truncated") else ""
        md_body = (t.get("markdown") or "").strip()
        blocks.append(
            f"{header}- **Extracted Length:** {char_count:,} chars{trunc_note}\n\n"
            f"{md_body}\n"
        )

    return "\n---\n\n".join(blocks)


# ── CLI Entrypoint (`python -m nexus.shared_tools.browser_bridge`) ───────────

def main() -> None:
    """CLI entrypoint for inspecting Chrome Tab Groups and extracting live tab Markdown."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Read-Only Chrome Browser & Tab Group Bridge for the Nexus Engine."
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check whether the Chrome Extension is connected.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List open Chrome tabs and Chrome Tab Groups (default action if --read is not passed).",
    )
    parser.add_argument(
        "--read",
        action="store_true",
        help="Extract clean rendered DOM Markdown from matching tabs.",
    )
    parser.add_argument(
        "-g",
        "--group",
        type=str,
        default=None,
        help="Filter by Chrome Tab Group name (case-insensitive, e.g. 'Jobs').",
    )
    parser.add_argument(
        "-q",
        "--query",
        type=str,
        default=None,
        help="Filter tabs by title, URL, or group name substring.",
    )
    parser.add_argument(
        "-t",
        "--tab-id",
        type=int,
        nargs="+",
        default=None,
        help="One or more specific Chrome tab_id integers to read.",
    )
    parser.add_argument(
        "--active",
        action="store_true",
        help="Target only the currently active/focused Chrome tab.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=20000,
        help="Maximum characters of Markdown to extract per tab (default: 20000).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted Markdown.",
    )

    args = parser.parse_args()

    if args.status:
        status = get_bridge_status()
        if args.json:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        elif status.get("connected"):
            meta = status.get("metadata") or {}
            print(
                f"✅ Nexus Browser Bridge Connected ({status.get('transport')})\n"
                f"   Mode: {status.get('mode')}\n"
                f"   Open Tabs: {meta.get('tab_count', '?')} | Tab Groups: {meta.get('group_count', '?')}"
            )
        else:
            print(f"❌ Nexus Browser Bridge Disconnected\n{status.get('error')}")
            sys.exit(1)
        return

    # If `--read` or `--tab-id` was passed, extract tab DOM Markdown
    if args.read or args.tab_id:
        res = read_tabs(
            tab_ids=args.tab_id,
            group_name=args.group,
            query=args.query,
            active_only=args.active,
            max_chars=args.max_chars,
        )
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(format_tab_reads_as_markdown(res))
        if not res.get("ok"):
            sys.exit(1)
        return

    # Default action: list open tabs and Chrome Tab Groups
    res = list_tabs(
        group_name=args.group,
        query=args.query,
        active_only=args.active,
    )
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(format_tabs_as_markdown(res))
    if not res.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
