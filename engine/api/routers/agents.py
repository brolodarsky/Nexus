"""
agents.py — Agent status and interaction routes.
Bridges the Next.js frontend to the existing LangGraph agents.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────

class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    response: str
    agent: str
    timestamp: str


class AgentStatusEntry(BaseModel):
    name: str
    display_name: str
    status: str          # "idle" | "running" | "waiting_hitl" | "not_built"
    last_run: str | None
    error_count: int
    description: str


# ── Agent Registry ────────────────────────────────────────────
# Static registry of all planned agents. Only the Librarian is
# operational — the rest are listed so the dashboard can display
# the full system vision with accurate build status.

AGENT_REGISTRY = [
    {
        "name": "librarian",
        "display_name": "Librarian",
        "status": "idle",
        "last_run": None,
        "error_count": 0,
        "description": "Cross-domain vault search & file navigation agent.",
    },
    {
        "name": "career",
        "display_name": "Career Agent",
        "status": "not_built",
        "last_run": None,
        "error_count": 0,
        "description": "Job tracking, resume updates, and career strategy.",
    },
    {
        "name": "medical",
        "display_name": "Medical Team",
        "status": "not_built",
        "last_run": None,
        "error_count": 0,
        "description": "Longitudinal clinical reasoning & health tracking.",
    },
    {
        "name": "content_router",
        "display_name": "Content Router",
        "status": "not_built",
        "last_run": None,
        "error_count": 0,
        "description": "Universal content classification & agent dispatch.",
    },
    {
        "name": "weekly_review",
        "display_name": "Weekly Review",
        "status": "not_built",
        "last_run": None,
        "error_count": 0,
        "description": "Automated weekly checklist with HITL interrupts.",
    },
    {
        "name": "engine_architect",
        "display_name": "Engine Architect",
        "status": "not_built",
        "last_run": None,
        "error_count": 0,
        "description": "System health audits, eval benchmarks, engine rot prevention.",
    },
]


# ── Routes ────────────────────────────────────────────────────

@router.get("/status", response_model=list[AgentStatusEntry])
async def get_agent_status():
    """Returns the status of all registered agents."""
    return AGENT_REGISTRY


@router.post("/ask", response_model=AskResponse)
async def ask_brain(request: AskRequest):
    """
    Sends a natural-language query to the Librarian agent and returns
    its response. This is the primary conversational endpoint.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        from agents.librarian.api import ask_librarian

        response_text = ask_librarian(request.query)

        # Update the Librarian's last_run timestamp in the registry
        for agent in AGENT_REGISTRY:
            if agent["name"] == "librarian":
                agent["last_run"] = datetime.now(timezone.utc).isoformat()
                break

        return AskResponse(
            response=response_text,
            agent="librarian",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}",
        )
