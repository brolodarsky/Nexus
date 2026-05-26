"""
main.py — FastAPI application for the Nexus Engine Control Panel.
Serves as the HTTP bridge between the Next.js frontend and the Python engine.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import agents, vault

app = FastAPI(
    title="Nexus Engine API",
    description="HTTP bridge for the Nexus Agentic Engine Control Panel",
    version="0.1.0",
)

# CORS — allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route Mounts ──────────────────────────────────────────────
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(vault.router, prefix="/api/vault", tags=["vault"])


# ── Health Check ──────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """Basic health check — confirms the API is reachable."""
    return {
        "status": "ok",
        "engine": "Nexus",
        "version": "2.0.0",
    }
