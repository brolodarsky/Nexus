"""
agents.py — Agent status and interaction routes.
Bridges the Next.js frontend to the existing LangGraph agents.
"""
import json
import queue
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from nexus.core.trace import trace_bus

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
        from nexus.agents.router.api import route_content

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


# ── SSE Streaming Endpoint ───────────────────────────────────

def _run_pipeline(query: str, event_queue: queue.Queue):
    """
    Runs route_content() synchronously in a background thread.
    Pushes the final result (or error) into the queue as a special event.
    Trace events are fanned out via the global trace_bus subscription
    set up by the SSE generator.
    """
    try:
        from nexus.agents.router.api import route_content

        result = route_content(query)

        routed_domain = result.get("domain", "general")
        agent_name = "career" if routed_domain == "career" else "librarian" # TODO: Generalize 

        now = datetime.now(timezone.utc).isoformat()
        for agent in AGENT_REGISTRY:
            if agent["name"] == "content_router":
                agent["last_run"] = now
            if agent["name"] == agent_name:
                agent["last_run"] = now

        event_queue.put({
            "type": "done",
            "response": result.get("response", ""),
            "agent": agent_name,
            "domain": routed_domain,
            "confidence": result.get("confidence"),
            "reasoning": result.get("reasoning"),
            "timestamp": now,
        })
    except Exception as e:
        event_queue.put({
            "type": "error",
            "message": f"Agent execution failed: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


@router.post("/ask/stream")
async def ask_brain_stream(request: AskRequest, req: Request):
    """
    SSE streaming endpoint. Streams real-time trace events from the
    agent pipeline, then emits a final 'done' event with the response.

    Uses a thread-safe queue: trace_bus pushes events, the SSE generator
    yields them as `data:` lines.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    event_queue: queue.Queue = queue.Queue()

    # Subscribe to the global trace bus — push events into our queue
    unsubscribe = trace_bus.subscribe(lambda evt: event_queue.put(evt))

    # Kick off the pipeline in a background thread
    thread = threading.Thread(
        target=_run_pipeline,
        args=(request.query, event_queue),
        daemon=True,
    )
    thread.start()

    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await req.is_disconnected():
                    break

                try:
                    event = event_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                event_data = json.dumps(event, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

                # Terminal events — stop streaming after these
                if event.get("type") in ("done", "error"):
                    break
        finally:
            unsubscribe()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
