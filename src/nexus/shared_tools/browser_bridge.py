"""
browser_bridge.py — Chrome Browser, Tab Group & Assisted-Draft Form Bridge for the Nexus Engine.

Connects to the local unpacked Chrome Extension (`src/nexus/shared_tools/browser_extension/`)
to list open tabs, inspect/create Chrome Tab Groups (`chrome.tabGroups`), extract clean
Markdown (and optional transient form refs) from the live rendered DOM of authenticated tabs,
and draft-fill form fields without ever auto-submitting.
"""
# argparse: Standard library CLI argument parser for `python -m nexus.shared_tools.browser_bridge`
import argparse
# asyncio: Standard library async I/O runtime used for standalone WebSocket server fallback
import asyncio
import http
import json
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Coroutine, Dict, List, Optional
from urllib.parse import urlsplit

# httpx: Modern HTTP client used to query the FastAPI `/api/browser` relay when `start.ps1` is running
import httpx
# websockets: Standards-compliant WebSocket library used for standalone CLI mode when FastAPI is offline
from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Request, Response

from nexus.core.constants import PROJECT_ROOT

# Loopback URLs and ports for communicating with the Chrome Extension
FASTAPI_BASE_URL = "http://127.0.0.1:8000/api/browser"
CLI_WS_HOST = "127.0.0.1"
CLI_WS_PORT = 8765
API_WS_PORT = 8000
EXPECTED_BRIDGE_VERSION = "1.2.0"
MAX_OPEN_TABS = 10
MAX_FILL_FIELDS = 50
VALID_GROUP_COLORS = frozenset({"grey", "blue", "red", "yellow", "green", "pink", "purple", "cyan", "orange"})
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
    hello_version: Optional[str] = None

    # Handler invoked by `websockets.serve` when the Chrome Extension connects to `/api/browser/ws`
    async def _ws_handler(websocket: ServerConnection) -> None:
        nonlocal command_sent, hello_version
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

                if msg.get("type") == "hello" and isinstance(msg.get("bridge_version"), str):
                    hello_version = msg.get("bridge_version")

                if msg.get("type") == "response" and msg.get("request_id") == request_id:
                    if not result_future.done():
                        result_future.set_result(msg)
                    return
        except Exception as exc:
            if not result_future.done():
                result_future.set_exception(exc)

    # Answers the Chrome Extension's lightweight HTTP status probe (`GET /api/browser/status`)
    # with `200 OK` so `background.js` only initiates `new WebSocket(...)` when a listener is live,
    # preventing Chromium's C++ WebSocket layer from logging `ERR_CONNECTION_REFUSED` in `chrome://extensions`.
    async def _process_request(connection: ServerConnection, request: Request) -> Optional[Response]:
        if request.headers.get("Upgrade", "").lower() != "websocket":
            resp = connection.respond(http.HTTPStatus.OK, '{"ok": true, "mode": "ephemeral_cli"}\n')
            resp.headers["Content-Type"] = "application/json"
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp
        return None

    servers = []
    # Bind port 8000 (if FastAPI is completely offline) and port 8765 (dedicated CLI bridge port)
    for port in (API_WS_PORT, CLI_WS_PORT):
        try:
            srv = await serve(_ws_handler, CLI_WS_HOST, port, process_request=_process_request)
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
        data = response.get("data") or {}
        loaded_version = (data.get("bridge_version") if isinstance(data, dict) else None) or hello_version
        result: Dict[str, Any] = {
            "ok": True,
            "transport": f"ephemeral_ws:{CLI_WS_PORT}",
            "data": data,
        }
        if loaded_version:
            result["bridge_version"] = loaded_version
        return result
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
    """Dispatches a browser bridge command via FastAPI (`localhost:8000`) if connected, else standalone WS (`8765`).

    Args:
        action: One of `"ping"`, `"list_tabs"`, `"read_tabs"`, `"open_tabs"`, or `"fill_form"`.
        params: Optional filter, extraction, tab-opening, or form-fill parameters dictionary.
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
                    loaded_version = (status_json.get("metadata") or {}).get("bridge_version")
                    # FastAPI has an active Chrome Extension socket! Route through REST API.
                    with httpx.Client(timeout=timeout) as api_client:
                        if action == "ping":
                            ping_out: Dict[str, Any] = {
                                "ok": True,
                                "transport": "fastapi:8000",
                                "data": status_json.get("metadata") or status_json,
                            }
                            if loaded_version:
                                ping_out["bridge_version"] = loaded_version
                            return ping_out
                        elif action == "list_tabs":
                            r = api_client.get(f"{FASTAPI_BASE_URL}/tabs", params=clean_params)
                        elif action == "read_tabs":
                            r = api_client.post(f"{FASTAPI_BASE_URL}/read", json=clean_params)
                        elif action == "open_tabs":
                            r = api_client.post(f"{FASTAPI_BASE_URL}/open", json=clean_params)
                        elif action == "fill_form":
                            r = api_client.post(f"{FASTAPI_BASE_URL}/fill", json=clean_params)
                        else:
                            return {"ok": False, "error": f"Unknown action: {action}"}

                        if r.status_code == 200:
                            resp_data = r.json()
                            eff_version = (
                                resp_data.get("bridge_version") if isinstance(resp_data, dict) else None
                            ) or loaded_version
                            out: Dict[str, Any] = {
                                "ok": True,
                                "transport": "fastapi:8000",
                                "data": resp_data,
                            }
                            if eff_version:
                                out["bridge_version"] = eff_version
                            return out
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


# ── Pure-Python Validation Helpers ───────────────────────────────────────────

# Validates and normalizes target URLs before dispatching `open_tabs` so non-HTTP schemes never hit Chrome.
def validate_http_urls(urls: List[str]) -> tuple[List[str], Optional[str]]:
    """Validates a bounded list of `http://` or `https://` URLs for `open_tabs()`.

    Returns:
        Tuple `(cleaned_urls, error_message)`. `error_message` is None when valid.
    """
    if not isinstance(urls, list) or not urls:
        return [], "Provide at least 1 URL to open."
    if len(urls) > MAX_OPEN_TABS:
        return [], f"Cannot open more than {MAX_OPEN_TABS} tabs per call (received {len(urls)})."

    cleaned: List[str] = []
    for raw in urls:
        u = str(raw or "").strip()
        if not u:
            return [], "Empty URL string in `urls` list."
        parsed = urlsplit(u)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            return [], f"Rejected unsafe or invalid URL '{u}'. Only http:// and https:// URLs are permitted."
        cleaned.append(u)
    return cleaned, None


# ── Public Pure-Python API ───────────────────────────────────────────────────

def get_bridge_status() -> Dict[str, Any]:
    """Checks connection status of the Chrome Extension bridge."""
    res = _dispatch_browser_command("ping", timeout=5.0)
    if not res.get("ok"):
        return {
            "connected": False,
            "mode": "assisted_draft",
            "expected_bridge_version": EXPECTED_BRIDGE_VERSION,
            "extension_dir": str(EXTENSION_DIR),
            "error": res.get("error"),
        }
    meta = res.get("data", {}) or {}
    loaded_version = (meta.get("bridge_version") if isinstance(meta, dict) else None) or res.get("bridge_version")
    update_required = bool(isinstance(loaded_version, str) and loaded_version and loaded_version != EXPECTED_BRIDGE_VERSION)
    mode = (meta.get("mode") if isinstance(meta, dict) else None) or "assisted_draft"
    return {
        "connected": True,
        "mode": mode,
        "transport": res.get("transport"),
        "expected_bridge_version": EXPECTED_BRIDGE_VERSION,
        "loaded_bridge_version": loaded_version,
        "update_required": update_required,
        "extension_dir": str(EXTENSION_DIR),
        "metadata": meta,
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


# ── Per-Conversation Tab Capture Cache Hook ──────────────────────────────────

# Extracts valid DOM reads from `read_tabs()` output, stores them in the active conversation's
# SQLite capture ledger (`conversation_cache`), and attaches each tab's assigned `cache://tab/<slug>` handle.
def _store_read_tabs_in_conversation_cache(
    result: Dict[str, Any],
    conversation_id: Optional[str] = None,
) -> None:
    """Stores successful `read_tabs()` extractions in `conversation_cache` for the active conversation."""
    try:
        from nexus.core.conversation_cache import get_active_conversation_id, put_capture

        data = result.get("data") or {}
        tabs = data.get("tabs") or []
        convo_id = (conversation_id or "").strip() or get_active_conversation_id()

        for tab in tabs:
            if not isinstance(tab, dict) or not tab.get("ok"):
                continue
            md_text = str(tab.get("markdown") or "")
            if not md_text.strip():
                continue
            raw_url = str(tab.get("url") or "").strip() or None
            title = str(tab.get("title") or "").strip() or (raw_url or "Chrome Tab")
            cache_key = put_capture(
                conversation_id=convo_id,
                source_type="tab",
                title=title,
                content=md_text,
                source_url=raw_url,
            )
            tab["cache_key"] = cache_key
    except Exception:
        # Defensive guard: cache I/O failures must never break live `read_tabs()` responses
        return


def read_tabs(
    tab_ids: Optional[List[int]] = None,
    group_name: Optional[str] = None,
    query: Optional[str] = None,
    active_only: bool = False,
    max_chars: int = 20000,
    include_refs: bool = False,
) -> Dict[str, Any]:
    """Extracts clean Markdown from the live rendered DOM of matching Chrome tabs.

    Args:
        tab_ids: Optional list of integer Chrome `tab_id` values to read.
        group_name: Optional Chrome Tab Group title to read all tabs from (case-insensitive).
        query: Optional substring filter matching tab title or URL.
        active_only: If True, reads only the currently active tab.
        max_chars: Maximum characters of Markdown to return per tab (default: 20,000).
        include_refs: If True, stamps transient `data-nexus-ref` IDs onto visible form controls for `fill_form()`.
    """
    res = _dispatch_browser_command(
        action="read_tabs",
        params={
            "tab_ids": tab_ids,
            "group_name": group_name,
            "query": query,
            "active_only": active_only,
            "max_chars": max_chars,
            "include_refs": include_refs,
        },
        timeout=25.0,
    )
    if res.get("ok"):
        _store_read_tabs_in_conversation_cache(res)
    return res


def open_tabs(
    urls: List[str],
    group_name: Optional[str] = None,
    group_color: str = "blue",
    activate_first: bool = False,
) -> Dict[str, Any]:
    """Opens 1-10 `http(s)` URLs in Chrome tabs and optionally groups them into a Chrome Tab Group.

    Args:
        urls: List of 1-10 `http://` or `https://` URLs to open.
        group_name: Optional Chrome Tab Group title (reuses existing group in window if matched).
        group_color: Tab Group color (`grey`, `blue`, `red`, `yellow`, `green`, `pink`, `purple`, `cyan`, `orange`).
        activate_first: If True, focuses the first newly opened tab.
    """
    cleaned_urls, err = validate_http_urls(urls)
    if err:
        return {"ok": False, "error": err}

    norm_color = (group_color or "blue").strip().lower()
    if norm_color not in VALID_GROUP_COLORS:
        norm_color = "blue"

    clean_group = group_name.strip() if isinstance(group_name, str) and group_name.strip() else None
    return _dispatch_browser_command(
        action="open_tabs",
        params={
            "urls": cleaned_urls,
            "group_name": clean_group,
            "group_color": norm_color,
            "activate_first": bool(activate_first),
        },
        timeout=20.0,
    )


def fill_form(
    tab_id: int,
    fields: Dict[str, Any],
) -> Dict[str, Any]:
    """Draft-fills form controls inside an open Chrome tab using transient `ref` IDs (never auto-submits).

    Args:
        tab_id: Integer Chrome `tab_id` previously inspected with `read_tabs(..., include_refs=True)`.
        fields: Dictionary mapping `ref` IDs (e.g. `{"f0_1": "Jane Doe"}`) to draft values.
    """
    if isinstance(tab_id, bool) or not isinstance(tab_id, int):
        return {"ok": False, "error": "`tab_id` must be an integer Chrome tab ID."}
    if not isinstance(fields, dict) or not fields:
        return {"ok": False, "error": "`fields` must be a non-empty dictionary mapping element refs to values."}
    if len(fields) > MAX_FILL_FIELDS:
        return {"ok": False, "error": f"Cannot fill more than {MAX_FILL_FIELDS} fields per call (received {len(fields)})."}

    return _dispatch_browser_command(
        action="fill_form",
        params={
            "tab_id": tab_id,
            "fields": fields,
        },
        timeout=20.0,
    )


# ── Markdown Formatters for Agent & CLI Consumption ──────────────────────────

# Emits a top reload notice when the running Chrome extension reports an older `BRIDGE_VERSION`.
def _version_drift_callout(data: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    """Returns a Markdown warning block if loaded extension version differs from `EXPECTED_BRIDGE_VERSION`."""
    loaded_version = data.get("bridge_version") or result.get("bridge_version")
    if isinstance(loaded_version, str) and loaded_version and loaded_version != EXPECTED_BRIDGE_VERSION:
        return (
            f"\n> ⚠️ **Stale Chrome Extension Detected:** Chrome is running Nexus Browser Bridge "
            f"`v{loaded_version}` (expected `v{EXPECTED_BRIDGE_VERSION}`). Open `chrome://extensions` "
            f"and click **Reload** on *Nexus Browser Bridge* to activate the latest "
            f"DOM/modal/form/tab-automation capabilities."
        )
    return None


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

    header_lines: List[str] = [
        f"# Extracted Chrome Tab Content ({ok_count}/{req_count} tabs read successfully)"
    ]
    drift = _version_drift_callout(data, result)
    if drift:
        header_lines.append(drift)
    blocks: List[str] = ["\n".join(header_lines)]

    for idx, t in enumerate(tabs, start=1):
        tid = t.get("tab_id")
        title = (t.get("title") or "(Untitled)").strip()
        url = t.get("url") or ""
        g_title = t.get("group_title")
        group_line = f"- **Chrome Tab Group:** {g_title} ({t.get('group_color')})\n" if g_title else ""
        cache_key = t.get("cache_key")
        if isinstance(cache_key, str) and cache_key:
            short_key = cache_key[len("cache://") :] if cache_key.startswith("cache://") else cache_key
            cache_line = f"- **Cache Key:** `{cache_key}` *(embed verbatim via `{{{{cache:{short_key}}}}}`)*\n"
        else:
            cache_line = ""

        header = (
            f"## {idx}. [tab_id: {tid}] {title}\n"
            f"- **URL:** {url}\n"
            f"{cache_line}"
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


def format_open_tabs_as_markdown(result: Dict[str, Any]) -> str:
    """Formats the output of `open_tabs()` into a structured Markdown summary with `tab_id` handles."""
    if not result.get("ok"):
        return f"❌ **Nexus Browser Bridge Error:**\n{result.get('error', 'Unknown error')}"

    data = result.get("data") or {}
    tabs: List[Dict[str, Any]] = data.get("tabs") or []
    opened_count = data.get("opened_count", len(tabs))
    group_title = data.get("group_title")
    group_color = data.get("group_color")
    group_id = data.get("group_id")

    lines: List[str] = [f"# Opened Chrome Tabs ({opened_count} tab(s))"]
    drift = _version_drift_callout(data, result)
    if drift:
        lines.append(drift)

    if group_title:
        lines.append(
            f"- **Chrome Tab Group:** {group_title} (`color: {group_color or 'blue'}`, `group_id: {group_id}`)"
        )

    for t in tabs:
        tid = t.get("tab_id")
        url = t.get("url") or ""
        active_badge = " **[ACTIVE]**" if t.get("active") else ""
        lines.append(f"- **`[tab_id: {tid}]`**{active_badge} {url}")

    return "\n".join(lines)


def format_fill_form_as_markdown(result: Dict[str, Any]) -> str:
    """Formats the output of `fill_form()` into a clear audit report for human review."""
    if not result.get("ok"):
        return f"❌ **Nexus Browser Bridge Error:**\n{result.get('error', 'Unknown error')}"

    data = result.get("data") or {}
    tab_id = data.get("tab_id")
    title = (data.get("title") or "(Untitled)").strip()
    url = data.get("url") or ""
    filled_count = data.get("filled_count", 0)
    blocked_count = data.get("blocked_count", 0)
    skipped_count = data.get("skipped_count", 0)
    not_found_count = data.get("not_found_count", 0)
    entries: List[Dict[str, Any]] = data.get("results") or []

    lines: List[str] = [
        f"# Draft Form Fill Report — `[tab_id: {tab_id}]` {title}",
        f"- **URL:** {url}",
        (
            f"- **Summary:** {filled_count} filled | {blocked_count} blocked | "
            f"{skipped_count} skipped | {not_found_count} not found"
        ),
    ]
    drift = _version_drift_callout(data, result)
    if drift:
        lines.append(drift)

    if entries:
        lines.append("\n## Field Outcomes")
        for item in entries:
            ref = item.get("ref", "?")
            status = item.get("status", "unknown")
            label = item.get("label") or item.get("tag") or ""
            label_part = f" ({label})" if label else ""
            if status == "filled":
                lines.append(f"- ✅ `{ref}`{label_part}: set to `{item.get('new_value', '')}`")
            elif status == "blocked":
                lines.append(f"- ⛔ `{ref}`{label_part}: **BLOCKED** — {item.get('reason', 'Restricted field')}")
            elif status == "skipped":
                lines.append(f"- ⚠️ `{ref}`{label_part}: **SKIPPED** — {item.get('reason', 'Could not apply value')}")
            else:
                lines.append(f"- ❌ `{ref}`: **NOT FOUND** — {item.get('reason', 'Missing in DOM')}")

    lines.append(
        "\n> **Review Required:** Inspect the blue-outlined draft fields in Chrome and submit manually "
        "(Nexus never auto-submits forms)."
    )
    return "\n".join(lines)


# ── CLI Entrypoint (`python -m nexus.shared_tools.browser_bridge`) ───────────

def main() -> None:
    """CLI entrypoint for inspecting/opening Chrome Tab Groups, extracting DOM Markdown, and draft-filling forms."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Chrome Browser, Tab Group & Assisted-Draft Form Bridge for the Nexus Engine."
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check whether the Chrome Extension is connected.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List open Chrome tabs and Chrome Tab Groups (default action if --read/--open/--fill are not passed).",
    )
    parser.add_argument(
        "--read",
        action="store_true",
        help="Extract clean rendered DOM Markdown from matching tabs.",
    )
    parser.add_argument(
        "--refs",
        action="store_true",
        help="Stamp transient `ref` handles onto visible form controls when using --read.",
    )
    parser.add_argument(
        "--open",
        nargs="+",
        metavar="URL",
        default=None,
        help="Open 1-10 HTTP(S) URLs in Chrome tabs (optionally grouped via --group/--color).",
    )
    parser.add_argument(
        "--color",
        type=str,
        default="blue",
        help="Chrome Tab Group color for --open (grey, blue, red, yellow, green, pink, purple, cyan, orange).",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Focus the first newly opened tab when using --open.",
    )
    parser.add_argument(
        "--fill",
        action="store_true",
        help="Draft-fill form fields in a single --tab-id using --fields-json (never submits).",
    )
    parser.add_argument(
        "--fields-json",
        type=str,
        default=None,
        help='JSON object mapping element refs to draft values (e.g. \'{"f0_1": "Jane Doe"}\').',
    )
    parser.add_argument(
        "-g",
        "--group",
        type=str,
        default=None,
        help="Filter or assign Chrome Tab Group name (case-insensitive, e.g. 'Jobs').",
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
        help="One or more specific Chrome tab_id integers to read (or single tab_id for --fill).",
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
            loaded_ver = status.get("loaded_bridge_version") or "?"
            print(
                f"✅ Nexus Browser Bridge Connected ({status.get('transport')})\n"
                f"   Mode: {status.get('mode')} | Version: v{loaded_ver} (expected v{status.get('expected_bridge_version')})\n"
                f"   Open Tabs: {meta.get('tab_count', '?')} | Tab Groups: {meta.get('group_count', '?')}"
            )
            if status.get("update_required"):
                print(
                    f"⚠️  Stale Chrome Extension detected: Chrome is running v{loaded_ver} "
                    f"(expected v{status.get('expected_bridge_version')}).\n"
                    "   Open chrome://extensions and click Reload on 'Nexus Browser Bridge'."
                )
        else:
            print(f"❌ Nexus Browser Bridge Disconnected\n{status.get('error')}")
            sys.exit(1)
        return

    if args.open:
        res = open_tabs(
            urls=args.open,
            group_name=args.group,
            group_color=args.color,
            activate_first=args.activate,
        )
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(format_open_tabs_as_markdown(res))
        if not res.get("ok"):
            sys.exit(1)
        return

    if args.fill:
        if not args.tab_id or len(args.tab_id) != 1:
            print("❌ Error: --fill requires exactly one --tab-id.", file=sys.stderr)
            sys.exit(1)
        if not args.fields_json:
            print("❌ Error: --fill requires --fields-json with a JSON object.", file=sys.stderr)
            sys.exit(1)
        try:
            parsed_fields = json.loads(args.fields_json)
        except Exception as exc:
            print(f"❌ Error parsing --fields-json: {exc}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(parsed_fields, dict):
            print("❌ Error: --fields-json must decode to a JSON object.", file=sys.stderr)
            sys.exit(1)

        res = fill_form(tab_id=args.tab_id[0], fields=parsed_fields)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(format_fill_form_as_markdown(res))
        if not res.get("ok"):
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
            include_refs=args.refs,
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
