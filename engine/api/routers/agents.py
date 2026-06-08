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
    domain: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
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
        "status": "idle",
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
    Routes a natural-language query through the Content Router agent,
    which classifies the domain and dispatches to the appropriate agent
    (Career, Librarian, etc.).
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        from agents.router.api import route_content

        result = route_content(request.query)

        # Determine which downstream agent actually handled the query
        # TODO: Make dynamic to integrate all agents
        routed_domain = result.get("domain", "general")
        agent_name = "career" if routed_domain == "career" else "librarian"

        # Update timestamps in the registry
        now = datetime.now(timezone.utc).isoformat()
        for agent in AGENT_REGISTRY:
            if agent["name"] == "content_router":
                agent["last_run"] = now
            if agent["name"] == agent_name:
                agent["last_run"] = now

        return AskResponse(
            response=result.get("response", ""),
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            reasoning=result.get("reasoning"),
            timestamp=now,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}",
        )
