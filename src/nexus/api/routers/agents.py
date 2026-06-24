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
from typing import Optional

from nexus.core.trace import trace_bus
from nexus.core.chats_db import get_active_agent, set_active_agent, log_message, get_chat_history

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

@router.get("/ask/history")
async def ask_brain_history(session_id: str = "default"):
    """Returns the chat history for a given session."""
    return get_chat_history(session_id=session_id)


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
        session_id = "default"
        log_message(role="user", content=request.query, session_id=session_id)
        
        active_agent = get_active_agent(session_id)
        if active_agent == "career":
            from nexus.agents.career.api import run_career_agent
            response = run_career_agent(content=request.query)
            result = {"domain": "career", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        elif active_agent == "librarian":
            from nexus.agents.librarian.api import ask_librarian
            response = ask_librarian(query=request.query)
            result = {"domain": "general", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        else:
            from nexus.agents.router.api import route_content
            result = route_content(request.query)

        # Determine which downstream agent actually handled the query
        routed_domain = result.get("domain", "general")
        agent_name = "career" if routed_domain == "career" else "librarian"
        
        response_text = result.get("response", "")
        if "[HANDOFF]" in response_text:
            set_active_agent(None, session_id)
            response_text = response_text.replace("[HANDOFF]", "").strip()
        else:
            set_active_agent(agent_name, session_id)

        log_message(
            role="assistant",
            content=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            trace=[],
            session_id=session_id
        )

        # Update timestamps in the registry
        now = datetime.now(timezone.utc).isoformat()
        for agent in AGENT_REGISTRY:
            if agent["name"] == "content_router":
                agent["last_run"] = now
            if agent["name"] == agent_name:
                agent["last_run"] = now

        return AskResponse(
            response=response_text,
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
    Runs route_content() or active agent synchronously in a background thread.
    Pushes the final result (or error) into the queue as a special event.
    Trace events are fanned out via the global trace_bus subscription
    set up by the SSE generator.
    """
    session_id = "default"
    log_message(role="user", content=query, session_id=session_id)
    
    trace_events = []
    def _on_trace(evt):
        trace_events.append(evt)
    unsub = trace_bus.subscribe(_on_trace)

    try:
        active_agent = get_active_agent(session_id)
        if active_agent == "career":
            from nexus.agents.career.api import run_career_agent
            response = run_career_agent(content=query)
            result = {"domain": "career", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        elif active_agent == "librarian":
            from nexus.agents.librarian.api import ask_librarian
            response = ask_librarian(query=query)
            result = {"domain": "general", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        else:
            from nexus.agents.router.api import route_content
            result = route_content(query)

        routed_domain = result.get("domain", "general")
        agent_name = "career" if routed_domain == "career" else "librarian" # TODO: Generalize 
        
        response_text = result.get("response", "")
        if "[HANDOFF]" in response_text:
            set_active_agent(None, session_id)
            response_text = response_text.replace("[HANDOFF]", "").strip()
        else:
            set_active_agent(agent_name, session_id)

        now = datetime.now(timezone.utc).isoformat()
        for agent in AGENT_REGISTRY:
            if agent["name"] == "content_router":
                agent["last_run"] = now
            if agent["name"] == agent_name:
                agent["last_run"] = now
                
        log_message(
            role="assistant",
            content=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            trace=trace_events,
            session_id=session_id
        )

        event_queue.put({
            "type": "done",
            "response": response_text,
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
    finally:
        unsub()


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
