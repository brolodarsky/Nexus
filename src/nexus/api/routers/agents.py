"""
agents.py — Agent status and interaction routes.
Bridges the Next.js frontend to the existing LangGraph multi-agent swarm.
"""

import json
import queue
import threading
import time
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
# chats_db: SQLite data access layer for conversations and chat history
from nexus.core.chats_db import (
    log_message, get_chat_history,
    create_conversation, get_conversations, 
    delete_conversation, update_conversation_title
)

# APIRouter instance mounted in main.py under prefix="/api/agents"
router = APIRouter()

# ── Request / Response Models ─────────────────────────────────

# Pydantic schema for incoming chat requests
class AskRequest(BaseModel):
    query: str                          # Raw user prompt text
    conversation_id: str                # UUID linking to chats.db conversation thread
    model_tier: Optional[str] = None    # Optional per-turn model tier/ID override ("strong", "medium", "low")


# Pydantic schema for synchronous chat responses
class AskResponse(BaseModel):
    response: str                       # Markdown text returned by the answering agent
    agent: str                          # Agent identifier (e.g., "nexus")
    domain: str | None = None           # Classified knowledge domain (e.g., "career", "general")
    confidence: float | None = None     # Router confidence score (0.0 to 1.0)
    reasoning: str | None = None        # Router explanation for domain selection
    model_tier: str | None = None       # Effective model tier used for this turn ("strong", "medium", "low")
    model_name: str | None = None       # Concrete provider model identifier (e.g., "gemini-4-argon", "gemini-3.8-flash")
    timestamp: str                      # ISO-8601 UTC timestamp


# ── Routes ────────────────────────────────────────────────────


# Returns selectable model tiers and active provider metadata for per-turn model selection in the Chat UI
@router.get("/models")
async def get_models_catalog():
    """Returns the configured model tiers, concrete model identifiers, and default tier from `.env`."""
    from nexus.core.constants import get_available_models
    return get_available_models()

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
        
        # Subscribe to trace_bus so synchronous `/ask` also captures 100% of LLM & Subagent trace steps
        trace_events = []
        def _on_sync_trace(evt):
            trace_events.append(evt)
        unsub_sync = trace_bus.subscribe(_on_sync_trace)

        try:
            # Phase 2: Invoke the unified NexusAgent directly with optional per-turn model override
            from nexus.agent.api import run_nexus_agent_with_trace
            result = run_nexus_agent_with_trace(
                query=request.query,
                thread_id=conversation_id,
                model_tier=request.model_tier,
            )
        finally:
            unsub_sync()

        routed_domain = result.get("domain")
        agent_name = "nexus"
        elapsed_sec = time.time() - t0
        response_text = result.get("response", "")
        used_tier = result.get("model_tier")
        used_model = result.get("model_name")

        # Phase 4: Persist assistant response + full trace events to SQLite chats.db
        log_message(
            role="assistant",
            content=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            trace=trace_events,
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
            tool_calls=result.get("tool_calls"),
            trace_events=trace_events,
            latency_seconds=elapsed_sec,
            metadata={"model_tier": used_tier, "model_name": used_model},
        )

        # Generate ISO-8601 UTC timestamp for chat response serialization
        now = datetime.now(timezone.utc).isoformat()

        return AskResponse(
            response=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            reasoning=result.get("reasoning"),
            model_tier=used_tier,
            model_name=used_model,
            timestamp=now,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}",
        )


# ── SSE Streaming Endpoint & Worker Thread ───────────────────

# Worker function executed inside a dedicated background OS thread
def _run_pipeline(
    query: str,
    conversation_id: str,
    event_queue: queue.Queue,
    model_tier: Optional[str] = None,
):
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
        # Invoke the unified NexusAgent directly with optional per-turn model override
        from nexus.agent.api import run_nexus_agent_with_trace
        result = run_nexus_agent_with_trace(
            query=query,
            thread_id=conversation_id,
            model_tier=model_tier,
        )

        routed_domain = result.get("domain")
        agent_name = "nexus"
        elapsed_sec = time.time() - t0
        response_text = result.get("response", "")
        used_tier = result.get("model_tier")
        used_model = result.get("model_name")

        # Generate ISO-8601 UTC timestamp for terminal SSE 'done' packet
        now = datetime.now(timezone.utc).isoformat()
                
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
            tool_calls=result.get("tool_calls"),
            trace_events=trace_events,
            latency_seconds=elapsed_sec,
            metadata={"model_tier": used_tier, "model_name": used_model},
        )

        # Push terminal 'done' event to thread queue to complete the SSE stream
        event_queue.put({
            "type": "done",
            "response": response_text,
            "agent": agent_name,
            "domain": routed_domain,
            "confidence": result.get("confidence"),
            "reasoning": result.get("reasoning"),
            "model_tier": used_tier,
            "model_name": used_model,
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
        args=(request.query, request.conversation_id, event_queue, request.model_tier), 
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
async def get_agent_runs(limit: int = 50, agent: Optional[str] = None):
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
    try:
        run_data = get_run(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not run_data:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return run_data
