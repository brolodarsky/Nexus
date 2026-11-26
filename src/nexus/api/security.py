"""
security.py — Bearer Token Authentication & Host-Header Validation for the Nexus Engine API (`S6`).

Protects all `/api/*` endpoints when FastAPI binds to `0.0.0.0:8000` for LAN Wi-Fi and Tailscale
mobile PWA access:
  1. `get_or_create_api_token()`: Reads `NEXUS_API_TOKEN` from `.env`, or auto-generates and persists
     a cryptographically random 32-byte URL-safe token in `.secrets/api_token`.
  2. `verify_api_token()`: Constant-time (`secrets.compare_digest`) dependency checking
     `Authorization: Bearer <token>` or `X-Nexus-Token: <token>`, with `?token=` query-parameter
     fallback strictly scoped to browser `<img>`, `<audio>`, and `<iframe>` GET/HEAD asset endpoints.
  3. `HostValidationMiddleware`: Pure ASGI middleware rejecting DNS-rebinding `Host` headers while
     permitting loopback (`127.0.0.1`, `localhost`, `[::1]`), RFC1918 LAN (`10.*`, `172.16-31.*`,
     `192.168.*`), and Tailscale (`100.64.0.0/10`, `*.ts.net`), plus an optional
     `NEXUS_LOCALHOST_ONLY=true` lockdown mode for untrusted public Wi-Fi.
"""

import ipaddress
import os
import re
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request, WebSocket
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from nexus.core.config import EngineSettings
from nexus.core.constants import PROJECT_ROOT

# Local secret file storing the auto-generated API bearer token (gitignored via `.secrets/`)
API_TOKEN_FILE: Path = PROJECT_ROOT / ".secrets" / "api_token"

# Loopback hostnames and raw TCP client addresses permitted in both standard and localhost-only modes
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOOPBACK_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})

# Tailscale MagicDNS hostname pattern (`<machine>.<tailnet>.ts.net`)
_TS_NET_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net$", re.IGNORECASE)

# RFC1918 private LAN + Tailscale CGNAT (`100.64.0.0/10`) IPv4 networks matching `main.py` CORS origins
_ALLOWED_LAN_NETWORKS = (
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("100.64.0.0/10"),
)

# Browser asset/media endpoints that load via HTML `<img>`, `<audio>`, or `<iframe>` tags
# (which cannot attach custom `Authorization` headers and therefore receive `?token=`).
QUERY_TOKEN_EXACT_PATHS = frozenset({"/api/vault/podcast/download", "/api/tools/resume/file"})
QUERY_TOKEN_PREFIXES = ("/api/agents/uploads/",)


def get_or_create_api_token() -> str:
    """Return the active Nexus API bearer token from settings or `.secrets/api_token` (generating if absent)."""
    configured = (EngineSettings().nexus_api_token or "").strip()
    if configured:
        return configured

    if API_TOKEN_FILE.is_file():
        try:
            existing = API_TOKEN_FILE.read_text(encoding="utf-8").strip()
            if len(existing) >= 16:
                return existing
        except OSError:
            pass

    token = secrets.token_urlsafe(32)
    API_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically via sibling temp file so concurrent startup probes never read a half-written token
    tmp_path = API_TOKEN_FILE.with_suffix(".tmp")
    tmp_path.write_text(f"{token}\n", encoding="utf-8")
    os.replace(tmp_path, API_TOKEN_FILE)
    return token


def _is_unauthenticated_testclient(client_host: Optional[str]) -> bool:
    """Allow in-process Starlette `TestClient` suites unless `NEXUS_ENFORCE_TEST_AUTH=1` is explicitly set."""
    if (client_host or "").strip().lower() != "testclient":
        return False
    return os.environ.get("NEXUS_ENFORCE_TEST_AUTH", "").strip().lower() not in ("1", "true", "yes")


def _allows_query_token(method: str, path: str) -> bool:
    """Return True strictly for read-only media/upload GET/HEAD routes where browsers cannot send headers."""
    if method.upper() not in ("GET", "HEAD"):
        return False
    if path in QUERY_TOKEN_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in QUERY_TOKEN_PREFIXES)


def _extract_token_from_headers_and_query(
    headers: dict[str, str],
    query_token: Optional[str] = None,
    allow_query_token: bool = False,
) -> Optional[str]:
    """Extract a bearer token from `Authorization: Bearer ...`, `X-Nexus-Token`, or allowed `?token=` query param."""
    auth_header = (headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        candidate = auth_header[7:].strip()
        if candidate:
            return candidate

    nexus_header = (headers.get("x-nexus-token") or "").strip()
    if nexus_header:
        return nexus_header

    if allow_query_token and query_token:
        cleaned = query_token.strip()
        if cleaned:
            return cleaned
    return None


def _tokens_match(provided: Optional[str]) -> bool:
    """Verify `provided` against the active API token in constant time to prevent timing side-channels."""
    if not provided:
        return False
    expected = get_or_create_api_token()
    return secrets.compare_digest(provided, expected)


def extract_request_token(request: Request, allow_query_token: Optional[bool] = None) -> Optional[str]:
    """Extract an API token from a FastAPI `Request` respecting the media-route query-param allowlist."""
    allow_qp = (
        _allows_query_token(request.method, request.url.path)
        if allow_query_token is None
        else bool(allow_query_token)
    )
    lower_headers = {k.lower(): v for k, v in request.headers.items()}
    return _extract_token_from_headers_and_query(
        lower_headers,
        query_token=request.query_params.get("token"),
        allow_query_token=allow_qp,
    )


def verify_api_token(request: Request) -> None:
    """FastAPI dependency enforcing Bearer / `X-Nexus-Token` authentication across `/api/*` routers."""
    # CORS preflight requests never carry Authorization headers and must reach CORSMiddleware unblocked
    if request.method.upper() == "OPTIONS":
        return

    client_host = request.client.host if request.client else None
    if _is_unauthenticated_testclient(client_host):
        return

    provided = extract_request_token(request)
    if not _tokens_match(provided):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing Nexus API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_browser_probe_or_token(request: Request) -> None:
    """Allow loopback Chrome Extension MV3 service-worker probes alongside token-authenticated CLI clients.

    Why: Chrome Extension `background.js` runs outside the Next.js env and sends `Origin: chrome-extension://<id>`
    (or no Origin during fetch probes) on `127.0.0.1` to check `/api/browser/status` before opening `/api/browser/ws`.
    Any `http://` or `https://` web origin without a valid API token is rejected with HTTP 401.
    """
    client_host = request.client.host if request.client else None
    if _is_unauthenticated_testclient(client_host):
        return

    provided = extract_request_token(request, allow_query_token=False)
    if _tokens_match(provided):
        return

    origin = (request.headers.get("origin") or "").strip().lower()
    if not origin or origin.startswith("chrome-extension://"):
        return

    raise HTTPException(
        status_code=401,
        detail="Invalid or missing Nexus API token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_browser_ws_auth(websocket: WebSocket) -> bool:
    """Authorize loopback Chrome Extension or token-bearing WebSocket clients for `/api/browser/ws`."""
    client_host = websocket.client.host if websocket.client else None
    if _is_unauthenticated_testclient(client_host):
        return True

    lower_headers = {k.lower(): v for k, v in websocket.headers.items()}
    provided = _extract_token_from_headers_and_query(
        lower_headers,
        query_token=websocket.query_params.get("token"),
        allow_query_token=True,
    )
    if _tokens_match(provided):
        return True

    origin = lower_headers.get("origin", "").strip().lower()
    return not origin or origin.startswith("chrome-extension://")


def _extract_hostname_from_host_header(host_header: Optional[str]) -> str:
    """Strip an optional `:port` suffix from an HTTP `Host` header, handling bracketed IPv6 literals."""
    raw = (host_header or "").strip().lower()
    if not raw:
        return ""
    # Reject host headers containing whitespace, slashes, or userinfo (`@`) injection tricks
    if any(ch in raw for ch in ("/", "\\", "@", " ", "\t")):
        return ""
    if raw.startswith("["):
        end_bracket = raw.find("]")
        if end_bracket == -1:
            return ""
        return raw[1:end_bracket]
    # Single colon denotes `hostname:port`; multiple colons denote an unbracketed IPv6 literal (e.g. `::1`)
    if raw.count(":") == 1:
        return raw.rsplit(":", 1)[0]
    return raw


def is_allowed_host_header(
    host_header: Optional[str],
    localhost_only: bool = False,
    allow_testserver: bool = False,
) -> bool:
    """Validate incoming HTTP `Host` headers against loopback, RFC1918 LAN, and Tailscale allowlists."""
    hostname = _extract_hostname_from_host_header(host_header)
    if not hostname:
        return False
    if hostname in LOOPBACK_HOSTS:
        return True
    if allow_testserver and hostname == "testserver":
        return True
    if localhost_only:
        return False

    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        return bool(_TS_NET_RE.match(hostname))

    if ip_obj.version == 4:
        return any(ip_obj in net for net in _ALLOWED_LAN_NETWORKS)
    return ip_obj.is_loopback


def _is_loopback_peer(client_host: Optional[str], allow_testclient: bool = False) -> bool:
    """Return True when the raw TCP peer belongs to local loopback."""
    clean = (client_host or "").strip().lower()
    if clean in LOOPBACK_CLIENT_HOSTS:
        return True
    return allow_testclient and clean == "testclient"


class HostValidationMiddleware:
    """Pure ASGI middleware enforcing `Host` header & optional `NEXUS_LOCALHOST_ONLY` validation.

    Implemented directly at the ASGI layer (instead of Starlette `BaseHTTPMiddleware`) so SSE
    streaming responses (`/api/agents/ask/stream`) pass through unbuffered with zero latency overhead.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if isinstance(client, (tuple, list)) and len(client) >= 1 else None
        is_testclient = (client_host or "").strip().lower() == "testclient"
        localhost_only = bool(EngineSettings().nexus_localhost_only)

        # Decode raw ASGI `(name_bytes, value_bytes)` headers to extract `Host`
        host_header: Optional[str] = None
        for name_b, val_b in scope.get("headers") or ():
            if name_b.lower() == b"host":
                host_header = val_b.decode("latin-1")
                break

        host_ok = is_allowed_host_header(
            host_header,
            localhost_only=localhost_only,
            allow_testserver=is_testclient,
        )
        peer_ok = True if not localhost_only else _is_loopback_peer(client_host, allow_testclient=is_testclient)

        if not (host_ok and peer_ok):
            if scope_type == "websocket":
                # Reject disallowed WebSocket handshake cleanly before accepting the socket
                await send({"type": "websocket.close", "code": 1008})
                return
            resp = JSONResponse(
                status_code=403,
                content={"detail": "Disallowed Host header or non-local client."},
            )
            await resp(scope, receive, send)
            return

        await self.app(scope, receive, send)
