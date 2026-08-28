"""
agents.py — Agent status and interaction routes.
Bridges the Next.js frontend to the existing LangGraph multi-agent swarm.
"""
# json: Standard library for serializing Python dictionaries to JSON strings for HTTP/SSE transport
import json
# queue: Thread-safe FIFO data structure used to pass events between background worker threads and async SSE generators
import queue
# threading: Standard library for spawning background OS threads for long-running synchronous agent invocations
import threading
import time
# datetime & timezone: Provides UTC timestamp generation for message logs and event telemetry
from datetime import datetime, timezone
from typing import Optional

# FastAPI primitives:
# - APIRouter: Modular sub-application for grouping related routes under a common prefix (/api/agents)
# - HTTPException: Raises structured HTTP error responses (e.g., 400 Bad Request, 500 Internal Server Error)
# - Request: Represents the raw incoming HTTP request, used to detect client disconnects during streaming
from fastapi import APIRouter, HTTPException, Request
# StreamingResponse: Streams chunks of data (SSE) over an open HTTP connection without buffering entire response
from fastapi.responses import StreamingResponse
# Pydantic BaseModel: Validates incoming request JSON payloads and serializes outgoing response schemas
from pydantic import BaseModel

# trace_bus: Global pub/sub event bus where LangGraph agents emit live trace events (tools, LLM calls)
from nexus.core.trace import trace_bus
# run_logger: Persists formatted execution run snapshots to logs/runs/ for observability and evals
from nexus.core.run_logger import log_run, list_runs, get_run
# chats_db: SQLite data access layer for persisting conversations, messages, and sticky agent routing state
from nexus.core.chats_db import (
    get_active_agent, set_active_agent, log_message, get_chat_history,
    create_conversation, get_conversations, get_conversation, 
    delete_conversation, update_conversation_title
)

# APIRouter instance mounted in main.py under prefix="/api/agents"
router = APIRouter()


# ── Request / Response Models ─────────────────────────────────

# Pydantic schema for incoming chat requests
class AskRequest(BaseModel):
    query: str              # Raw user prompt text
    conversation_id: str    # UUID linking to chats.db conversation thread


# Pydantic schema for synchronous chat responses
class AskResponse(BaseModel):
    response: str                   # Markdown text returned by the answering agent
    agent: str                      # Agent identifier (e.g., "career", "librarian")
    domain: str | None = None       # Classified knowledge domain (e.g., "career", "general")
    confidence: float | None = None # Router confidence score (0.0 to 1.0)
    reasoning: str | None = None    # Router explanation for domain selection
    timestamp: str                  # ISO-8601 UTC timestamp


# Pydantic schema for agent operational status displayed in the dashboard
class AgentStatusEntry(BaseModel):
    name: str               # Unique machine ID (e.g., "career")
    display_name: str       # Human-friendly label (e.g., "Career Agent")
    status: str             # Operational state: "idle" | "running" | "waiting_hitl" | "not_built"
    last_run: str | None    # ISO-8601 timestamp of last execution or None
    error_count: int        # Cumulative exceptions caught during execution
    description: str        # Summary of agent responsibilities


# ── Agent Registry ────────────────────────────────────────────
# Static registry of all planned swarm agents. Populates the dashboard table
# so the full architecture is visible even if specific agents are still in development.
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
        "status": "idle",
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

# Returns list of all registered swarm agents and their active states
@router.get("/status", response_model=list[AgentStatusEntry])
async def get_agent_status():
    """Returns the status of all registered agents for dashboard monitoring."""
    return AGENT_REGISTRY

# Returns all conversation threads for sidebar rendering
@router.get("/ask/conversations")
async def list_conversations():
    """Fetches all conversation metadata from SQLite chats.db."""
    return get_conversations()

# Pydantic schema for creating a new conversation
class CreateConversationRequest(BaseModel):
    title: str = "New Chat"

# Creates a new conversation thread with an initial title
@router.post("/ask/conversations")
async def create_new_conversation(req: CreateConversationRequest):
    """Generates a UUID and initializes a new thread in chats.db."""
    conv_id = create_conversation(req.title)
    return {"conversation_id": conv_id}

# Deletes a conversation and cascades to delete all its messages
@router.delete("/ask/conversations/{conversation_id}")
async def remove_conversation(conversation_id: str):
    """Removes a conversation thread by UUID."""
    delete_conversation(conversation_id)
    return {"status": "deleted"}

# Pydantic schema for renaming a conversation
class UpdateTitleRequest(BaseModel):
    title: str

# Updates the title of an existing conversation
@router.patch("/ask/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, req: UpdateTitleRequest):
    """Renames an existing conversation thread."""
    update_conversation_title(conversation_id, req.title)
    return {"status": "updated"}

# Clears the sticky agent lock so the next message is routed fresh
@router.post("/ask/conversations/{conversation_id}/reset")
async def reset_conversation_routing(conversation_id: str):
    """Clears sticky session agent lock for the specified conversation."""
    set_active_agent(None, conversation_id)
    return {"status": "reset"}

# Returns message history for a specific conversation
@router.get("/ask/history")
async def ask_brain_history(conversation_id: str):
    """Returns the ordered chat history for a given conversation UUID."""
    return get_chat_history(conversation_id=conversation_id)


# Synchronous (non-streaming) one-shot agent execution
@router.post("/ask", response_model=AskResponse)
async def ask_brain(request: AskRequest):
    """
    Routes a natural-language query through the Content Router agent or active sticky agent,
    waits for execution to finish, logs to SQLite, and returns the response JSON.
    """
    # Guard clause against empty queries
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        t0 = time.time()
        conversation_id = request.conversation_id
        # Phase 1: Persist user message to SQLite chats.db before running agents
        log_message(role="user", content=request.query, conversation_id=conversation_id)
        
        # Phase 2: Check for Sticky Session — if locked, bypass Router and call agent directly
        active_agent = get_active_agent(conversation_id)
        if active_agent == "career":
            from nexus.agents.career.api import run_career_agent
            response = run_career_agent(content=request.query, thread_id=conversation_id)
            result = {"domain": "career", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        elif active_agent == "librarian":
            from nexus.agents.librarian.api import ask_librarian
            response = ask_librarian(query=request.query, thread_id=conversation_id)
            result = {"domain": "general", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        else:
            # No sticky lock: run universal Content Router to classify and dispatch
            from nexus.agents.router.api import route_content
            result = route_content(request.query, thread_id=conversation_id)

        # Determine which downstream agent actually handled the query
        routed_domain = result.get("domain", "general")
        agent_name = "career" if routed_domain == "career" else "librarian"
        elapsed_sec = time.time() - t0
        
        # Phase 3: Check for [HANDOFF] token — allows agents to relinquish sticky lock
        response_text = result.get("response", "")
        if "[HANDOFF]" in response_text:
            set_active_agent(None, conversation_id)
            response_text = response_text.replace("[HANDOFF]", "").strip()
        else:
            set_active_agent(agent_name, conversation_id) # Lock sticky session to this agent

        # Phase 4: Persist assistant response to SQLite chats.db
        log_message(
            role="assistant",
            content=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            trace=[],
            conversation_id=conversation_id
        )

        # Phase 5: Persist structured JSON run snapshot to logs/runs/
        log_run(
            agent_name=agent_name,
            query=request.query,
            response=response_text,
            thread_id=conversation_id,
            domain=routed_domain,
            confidence=result.get("confidence"),
            reasoning=result.get("reasoning"),
            latency_seconds=elapsed_sec,
        )

        # Update last_run timestamps in the static registry
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


# ── SSE Streaming Endpoint & Worker Thread ───────────────────

# Worker function executed inside a dedicated background OS thread
def _run_pipeline(query: str, conversation_id: str, event_queue: queue.Queue):
    """
    Runs agent graph execution in a background thread so the async event loop is not blocked.
    Collects trace events via trace_bus subscription and pushes the final 'done' event to event_queue.
    """
    t0 = time.time()
    # Log user query to database immediately
    log_message(role="user", content=query, conversation_id=conversation_id)
    
    # Subscribe to trace_bus to capture all LLM and tool events emitted during this run
    trace_events = []
    def _on_trace(evt):
        trace_events.append(evt)
    unsub = trace_bus.subscribe(_on_trace)

    try:
        # Check for sticky session routing vs universal content routing
        active_agent = get_active_agent(conversation_id)
        if active_agent == "career":
            from nexus.agents.career.api import run_career_agent
            response = run_career_agent(content=query, thread_id=conversation_id)
            result = {"domain": "career", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        elif active_agent == "librarian":
            from nexus.agents.librarian.api import ask_librarian
            response = ask_librarian(query=query, thread_id=conversation_id)
            result = {"domain": "general", "response": response, "confidence": 1.0, "reasoning": "Sticky session"}
        else:
            from nexus.agents.router.api import route_content
            result = route_content(query, thread_id=conversation_id)

        routed_domain = result.get("domain", "general")
        agent_name = "career" if routed_domain == "career" else "librarian"
        elapsed_sec = time.time() - t0
        
        # Check for agent-initiated [HANDOFF] signal
        response_text = result.get("response", "")
        if "[HANDOFF]" in response_text:
            set_active_agent(None, conversation_id)
            response_text = response_text.replace("[HANDOFF]", "").strip()
        else:
            set_active_agent(agent_name, conversation_id)

        now = datetime.now(timezone.utc).isoformat()
        for agent in AGENT_REGISTRY:
            if agent["name"] == "content_router":
                agent["last_run"] = now
            if agent["name"] == agent_name:
                agent["last_run"] = now
                
        # Persist assistant message along with full trace array to chats.db
        log_message(
            role="assistant",
            content=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            trace=trace_events,
            conversation_id=conversation_id
        )

        # Persist structured JSON run snapshot to logs/runs/
        log_run(
            agent_name=agent_name,
            query=query,
            response=response_text,
            thread_id=conversation_id,
            domain=routed_domain,
            confidence=result.get("confidence"),
            reasoning=result.get("reasoning"),
            trace_events=trace_events,
            latency_seconds=elapsed_sec,
        )

        # Push terminal 'done' event to thread queue to complete the SSE stream
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
        # Push terminal 'error' event to thread queue on failure
        event_queue.put({
            "type": "error",
            "message": f"Agent execution failed: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        unsub() # Unsubscribe trace listener to prevent memory leaks


# Server-Sent Events (SSE) streaming endpoint
@router.post("/ask/stream")
async def ask_brain_stream(request: AskRequest, req: Request):
    """
    SSE streaming endpoint for live Thinking Panel updates.
    Spawns a background thread to run the agent, subscribes to trace_bus,
    and yields SSE data packets (data: {...}\n\n) as events occur.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Thread-safe FIFO queue to transfer events from background thread to async generator
    event_queue = queue.Queue()

    # Subscribe to trace_bus: every time an agent prints/emits a trace step, push it to event_queue
    unsubscribe = trace_bus.subscribe(lambda evt: event_queue.put(evt))

    # Spawn synchronous agent pipeline in background OS thread (daemon=True allows clean shutdown)
    pipeline_thread = threading.Thread(
        target=_run_pipeline, 
        args=(request.query, request.conversation_id, event_queue), 
        daemon=True
    )
    pipeline_thread.start()

    # Async generator function yielding formatted SSE packets
    async def event_generator():
        try:
            while True:
                # Detect if the client closed browser tab or canceled request
                if await req.is_disconnected():
                    break

                try:
                    # Non-blocking poll with 100ms timeout to periodically check req.is_disconnected()
                    event = event_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # SSE protocol format: 'data: <json_string>\n\n'
                event_data = json.dumps(event, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

                # Stop streaming after terminal events
                if event.get("type") in ("done", "error"):
                    break
        finally:
            unsubscribe() # Clean up global trace subscription when stream ends

    # Return StreamingResponse with SSE headers (no caching, keep-alive, no reverse proxy buffering)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Run Snapshot Inspection Endpoints ─────────────────────────

@router.get("/runs")
async def get_agent_runs(limit: int = 20, agent: Optional[str] = None):
    """
    Returns recent structured JSON run snapshots from logs/runs/.
    Supports filtering by agent name and custom limit.
    """
    return list_runs(limit=limit, agent=agent)


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str):
    """
    Retrieves full details of a specific execution run snapshot by ID.
    """
    run_data = get_run(run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return run_data


# ── Unified Engine Dashboard Endpoint ─────────────────────────

@router.get("/dashboard")
async def get_engine_dashboard():
    """
    Returns consolidated real-time engine telemetry, including pending HITL items,
    active conversation counts, agent execution statuses, and markdown summary.
    """
    from nexus.core.dashboard import get_dashboard_summary, generate_dashboard_markdown
    summary = get_dashboard_summary()
    markdown = generate_dashboard_markdown(summary)
    return {
        "summary": summary,
        "markdown": markdown,
    }


