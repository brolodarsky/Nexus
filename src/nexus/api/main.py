"""
main.py — FastAPI application for the Nexus Engine Control Panel.
Serves as the HTTP bridge between the Next.js frontend and the Python engine.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus.api.routers import agents, board, browser, chat_branches, hitl, tools, vault

app = FastAPI(
    title="Nexus Engine API",
    description="HTTP bridge for the Nexus Agentic Engine Control Panel",
    version="2.0.0",
)

# ── CORS Middleware ───────────────────────────────────────────
# Cross-Origin Resource Sharing (CORS) security configuration:
# When browsing the Next.js frontend from a mobile device or laptop across a local area network (LAN)
# or Tailscale mesh VPN, the client browser originates requests from distinct IP addresses or hostnames
# (e.g. http://192.168.1.50:3000 or http://100.x.y.z:3000) targeting the FastAPI backend (port 8000).
#
# allow_origin_regex:
#   Starlette evaluates this regex pattern against incoming Origin headers. Matches:
#   - Local loopback: localhost, 127.0.0.1
#   - Tailscale CGNAT IP range: 100.64.0.0/10 (100.x.y.z)
#   - Private RFC 1918 LAN ranges: 192.168.x.y, 10.x.y.z
#   - Tailscale MagicDNS hostnames: *.ts.net
#   - Optional port specifier: (:\d+)? allowing :3000, :8000, or standard web ports
# allow_credentials=True: Permits cookies, credentials, and authorization headers across origins
# allow_methods=["*"]: Permits all HTTP methods (GET, POST, OPTIONS, PUT, DELETE)
# allow_headers=["*"]: Permits all headers (e.g., Content-Type, Accept, Cache-Control)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|100\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|[a-zA-Z0-9-]+\.ts\.net)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route Mounts ──────────────────────────────────────────────
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(chat_branches.router, prefix="/api/agents", tags=["agents"])
app.include_router(vault.router, prefix="/api/vault", tags=["vault"])
app.include_router(hitl.router, prefix="/api/hitl", tags=["hitl"])
app.include_router(board.router, prefix="/api/board", tags=["board"])
app.include_router(browser.router, prefix="/api/browser", tags=["browser"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])


# ── Health Check ──────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """Basic health check — confirms the API is reachable."""
    return {
        "status": "ok",
        "engine": "Nexus",
        "version": "2.0.0",
    }
