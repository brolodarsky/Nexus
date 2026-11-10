"""
browser.py — FastAPI Router & WebSocket Relay for the Read-Only Nexus Browser Bridge (`/api/browser`).

Provides the loopback WebSocket endpoint (`/api/browser/ws`) that the unpacked Chrome Extension
(`src/nexus/shared_tools/browser_extension/`) connects to, alongside REST endpoints (`/status`,
`/tabs`, `/read`) so both the Next.js Control Panel and Python tools (`browser_bridge.py`) can
inspect Chrome Tab Groups and extract clean Markdown from live rendered tabs in <200ms.
"""
# asyncio: Standard Python asynchronous I/O library used for Future-based request/response correlation
import asyncio
import time
import uuid
# Typing primitives:
# - Any: Dynamic JSON payload values returned by Chrome extension APIs
# - Dict / List / Optional: Explicit collection and nullable type annotations
from typing import Any, Dict, List, Optional

# FastAPI primitives:
# - APIRouter: Modular route group mounted at `/api/browser` in `main.py`
# - HTTPException: Raises structured HTTP error responses (e.g. 503 when extension is disconnected)
# - WebSocket / WebSocketDisconnect: Bi-directional persistent socket protocol and disconnect exception
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
# BaseModel / Field: Pydantic schema validation for incoming REST POST bodies
from pydantic import BaseModel, Field

from nexus.core.constants import PROJECT_ROOT
from nexus.core.logger import logger

router = APIRouter()

# Path to the unpacked Chrome Extension folder for user-facing diagnostic hints
EXTENSION_DIR_PATH = str(PROJECT_ROOT / "src" / "nexus" / "shared_tools" / "browser_extension")


# ── Pydantic Request Schemas ─────────────────────────────────────────────────

# Schema describing the JSON payload accepted by `POST /api/browser/read`
class BrowserReadRequest(BaseModel):
    """Request parameters for extracting rendered DOM Markdown from one or more Chrome tabs."""
    # Optional list of integer Chrome tab IDs (e.g. [142, 145])
    tab_ids: Optional[List[int]] = Field(default=None, description="Specific Chrome tab IDs to read.")
    # Optional Chrome Tab Group title filter (case-insensitive substring or exact match)
    group_name: Optional[str] = Field(default=None, description="Chrome Tab Group title to read (e.g. 'Jobs').")
    # Optional keyword filter matching tab title, URL, or group name
    query: Optional[str] = Field(default=None, description="Substring filter matching tab title or URL.")
    # When True, restricts extraction to the currently focused tab in each window
    active_only: bool = Field(default=False, description="Read only the currently active tab(s).")
    # Per-tab character budget preventing a single massive webpage from exhausting context tokens
    max_chars: int = Field(default=20000, ge=500, le=200000, description="Max Markdown characters per tab.")


# ── Asynchronous WebSocket RPC Manager ───────────────────────────────────────

# Manages the persistent loopback WebSocket connection from the Chrome Extension service worker
# and matches outbound command `request_id` UUIDs to awaiting `asyncio.Future` objects.
class BrowserBridgeManager:
    """Coordinates async request-response RPC calls over the Chrome Extension WebSocket."""

    def __init__(self) -> None:
        # Currently active WebSocket connection from the Chrome extension (None when disconnected)
        self._active_ws: Optional[WebSocket] = None
        # Metadata received during the extension's `hello` handshake or periodic heartbeats
        self._metadata: Dict[str, Any] = {}
        # Unix epoch timestamps tracking connection lifecycle
        self._connected_at: Optional[float] = None
        self._last_seen_at: Optional[float] = None
        # Dictionary mapping in-flight `request_id` UUID strings -> `asyncio.Future` objects
        # `asyncio.Future[Dict[str, Any]]` represents a placeholder for a JSON result that will arrive asynchronously
        self._pending_requests: Dict[str, asyncio.Future[Dict[str, Any]]] = {}

    @property
    def is_connected(self) -> bool:
        """Returns True if an extension WebSocket is currently open."""
        return self._active_ws is not None

    def get_status(self) -> Dict[str, Any]:
        """Returns a structured diagnostic snapshot of the browser bridge connection."""
        return {
            "connected": self.is_connected,
            "mode": "read_only",
            "connected_at": self._connected_at,
            "last_seen_at": self._last_seen_at,
            "extension_dir": EXTENSION_DIR_PATH,
            "metadata": self._metadata,
        }

    # async def defines a coroutine that pauses on `await` without blocking the main FastAPI event loop
    async def accept_connection(self, websocket: WebSocket) -> None:
        """Accepts a new extension WebSocket connection and processes incoming frames until disconnect."""
        await websocket.accept()
        self._active_ws = websocket
        now = time.time()
        self._connected_at = now
        self._last_seen_at = now
        logger.info("Chrome Extension connected to /api/browser/ws (read-only mode).")

        try:
            while True:
                # Pause coroutine until the next JSON message frame arrives from Chrome
                raw_msg: Dict[str, Any] = await websocket.receive_json()
                self._last_seen_at = time.time()
                msg_type = raw_msg.get("type")

                if msg_type == "hello":
                    # Store browser version, initial tab counts, and mode from handshake
                    self._metadata = {
                        "bridge_version": raw_msg.get("bridge_version", "1.0.0"),
                        "mode": raw_msg.get("mode", "read_only"),
                        "user_agent": raw_msg.get("user_agent", ""),
                        "tab_count": raw_msg.get("tab_count", 0),
                        "group_count": raw_msg.get("group_count", 0),
                    }
                elif msg_type == "heartbeat":
                    # Heartbeat frame keeps MV3 service worker and socket alive; no state mutation needed
                    pass
                elif msg_type == "response":
                    # Match the response's `request_id` to the waiting `asyncio.Future` and resolve it
                    req_id = raw_msg.get("request_id")
                    if isinstance(req_id, str) and req_id in self._pending_requests:
                        future = self._pending_requests.pop(req_id)
                        if not future.done():
                            future.set_result(raw_msg)
        except WebSocketDisconnect:
            logger.info("Chrome Extension WebSocket disconnected.")
        except Exception as exc:
            logger.warning(f"Chrome Extension WebSocket closed with error: {exc}")
        finally:
            # Clean up only if this socket is still the active one (guards against rapid reconnect races)
            if self._active_ws is websocket:
                self._active_ws = None
                self._connected_at = None
            # Fail any in-flight futures immediately so callers do not hang until timeout
            for req_id, fut in list(self._pending_requests.items()):
                if not fut.done():
                    fut.set_exception(RuntimeError("Chrome Extension disconnected while command was in flight."))
            self._pending_requests.clear()

    async def send_command(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """Sends a JSON-RPC command (`ping`, `list_tabs`, `read_tabs`) to Chrome and awaits the response.

        Args:
            action: Read-only command name (`"ping"`, `"list_tabs"`, or `"read_tabs"`).
            params: Optional dictionary of filter or extraction arguments.
            timeout: Maximum seconds to wait for Chrome to respond before raising TimeoutError.
        """
        if self._active_ws is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Nexus Browser Bridge Chrome Extension is not connected. "
                    f"Open chrome://extensions, enable Developer Mode, click 'Load unpacked', "
                    f"and select: {EXTENSION_DIR_PATH}"
                ),
            )

        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        # Create an unresolved Future bound to the active event loop
        future: asyncio.Future[Dict[str, Any]] = loop.create_future()
        self._pending_requests[request_id] = future

        payload = {
            "request_id": request_id,
            "action": action,
            "params": params or {},
        }

        try:
            await self._active_ws.send_json(payload)
            # asyncio.wait_for suspends until `future` resolves or `timeout` seconds elapse
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise HTTPException(
                status_code=504,
                detail=f"Timed out after {timeout}s waiting for Chrome Extension response to '{action}'.",
            )
        except HTTPException:
            raise
        except Exception as exc:
            self._pending_requests.pop(request_id, None)
            raise HTTPException(
                status_code=502,
                detail=f"Failed communicating with Chrome Extension: {exc}",
            )

        if not response.get("ok", False):
            err_msg = response.get("error") or f"Chrome Extension reported failure for '{action}'."
            raise HTTPException(status_code=500, detail=err_msg)

        return response.get("data") or {}


# Singleton manager shared across all `/api/browser` endpoints
bridge_manager = BrowserBridgeManager()


# ── WebSocket & REST Route Handlers ──────────────────────────────────────────

@router.websocket("/ws")
async def browser_bridge_websocket(websocket: WebSocket) -> None:
    """Loopback WebSocket endpoint that the Chrome Extension service worker connects to."""
    await bridge_manager.accept_connection(websocket)


@router.get("/status")
async def get_browser_bridge_status() -> Dict[str, Any]:
    """Check whether the Nexus Browser Bridge Chrome Extension is connected and responsive."""
    status = bridge_manager.get_status()
    if status["connected"]:
        try:
            ping_data = await bridge_manager.send_command("ping", timeout=3.0)
            status["metadata"] = ping_data
        except Exception:
            pass
    return status


@router.get("/tabs")
async def list_browser_tabs_endpoint(
    group_name: Optional[str] = None,
    query: Optional[str] = None,
    active_only: bool = False,
) -> Dict[str, Any]:
    """List open Chrome tabs and Chrome Tab Groups (with optional group/keyword filters)."""
    return await bridge_manager.send_command(
        action="list_tabs",
        params={
            "group_name": group_name,
            "query": query,
            "active_only": active_only,
        },
    )


@router.post("/read")
async def read_browser_tabs_endpoint(req: BrowserReadRequest) -> Dict[str, Any]:
    """Extract clean, read-only Markdown from the live rendered DOM of matching Chrome tabs."""
    return await bridge_manager.send_command(
        action="read_tabs",
        params={
            "tab_ids": req.tab_ids,
            "group_name": req.group_name,
            "query": req.query,
            "active_only": req.active_only,
            "max_chars": req.max_chars,
        },
        timeout=25.0,
    )
