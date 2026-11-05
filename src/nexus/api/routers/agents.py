"""
agents.py — Agent status and interaction routes.
Bridges the Next.js frontend to the existing LangGraph multi-agent swarm.
"""

import asyncio
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
from nexus.core.cost import calculate_token_cost
from nexus.core.trace import trace_bus
# run_logger: Persists formatted execution run snapshots to logs/runs/ for observability and evals
from nexus.core.run_logger import log_run, list_runs, get_run
# chats_db: SQLite data access layer for conversations and chat history
from nexus.core.chats_db import (
    log_message, get_chat_history,
    create_conversation, get_conversations, get_conversation,
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
    cost_usd: float | None = None       # Estimated USD inference cost for this execution turn
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
    """
    Renames an existing conversation thread in SQLite `chats.db`.
    - conversation_id: UUID primary key identifying the target thread
    - req.title: New display title string (validated to prevent blank/whitespace-only names)
    """
    new_title = req.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    
    # Verify the target conversation exists in the SQLite store before writing
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found.")
    
    update_conversation_title(conversation_id, new_title)
    return {"status": "updated", "conversation_id": conversation_id, "title": new_title}

# Automatically generates a concise topic title for an existing conversation using the fast low-tier model
@router.post("/ask/conversations/{conversation_id}/auto-title")
async def auto_generate_conversation_title(conversation_id: str):
    """
    Summarizes the opening turn of a conversation into a concise 3-6 word title using the fast low-tier model.
    - conversation_id: UUID primary key identifying the conversation
    - Reads first user query and optional assistant excerpt from SQLite `messages` table
    - Invokes fast `tier="low"` LLM (`gemini-3.8-flash` or `claude-sonnet-4-5`) with low temperature
    - Falls back gracefully to a prompt excerpt if the model call times out or encounters an error
    """
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found.")

    history = get_chat_history(conversation_id=conversation_id, limit=6)
    if not history:
        return {"status": "unchanged", "title": conv.get("title", "New Chat")}

    # Locate the first user prompt and first assistant message in chronological history
    first_user_msg = next((m["content"] for m in history if m.get("role") == "user"), None)
    first_assistant_msg = next((m["content"] for m in history if m.get("role") == "assistant"), None)

    if not first_user_msg:
        return {"status": "unchanged", "title": conv.get("title", "New Chat")}

    # Default fallback title in case LLM is unavailable or unconfigured
    fallback_title = first_user_msg.strip()[:35].strip()
    if len(first_user_msg.strip()) > 35:
        fallback_title += "..."

    try:
        from nexus.core.constants import get_chat_model
        from nexus.agent.graph import extract_message_text
        # Use low-tier model (Flash / Sonnet) for sub-second, ultra-low-cost title summarization
        chat_model = get_chat_model(tier="low", temperature=0.2)
        
        prompt = (
            "Generate a concise, high-signal, natural conversation title (maximum 3 to 6 words) "
            "summarizing the topic of this chat. Do NOT use quotation marks, ending punctuation, "
            "prefixes like 'Title:', or markdown formatting. Return ONLY the raw title text.\n\n"
            f"User prompt: {first_user_msg[:400]}"
        )
        if first_assistant_msg:
            prompt += f"\nAssistant excerpt: {first_assistant_msg[:400]}"

        # BaseChatModel.ainvoke: asynchronous coroutine executing the prompt without blocking the event loop
        resp = await chat_model.ainvoke(prompt)
        # extract_message_text: cleanly unpacks text across both string and Gemini 3+ block-list formats
        raw_content = extract_message_text(resp)
        cleaned_title = raw_content.strip().strip('"\'`').replace("\n", " ").strip()
        
        # Strip common LLM preamble prefixes if present
        for prefix in ("Title:", "title:", "Topic:", "topic:"):
            if cleaned_title.startswith(prefix):
                cleaned_title = cleaned_title[len(prefix):].strip()
        cleaned_title = cleaned_title.strip('"\'`')
        
        # Enforce maximum sensible display length for sidebar neatness
        if len(cleaned_title) > 60:
            cleaned_title = cleaned_title[:57] + "..."
            
        final_title = cleaned_title if cleaned_title else fallback_title
        update_conversation_title(conversation_id, final_title)
        return {"status": "updated", "conversation_id": conversation_id, "title": final_title}
    except Exception as exc:
        # Fall back gracefully to prompt snippet without failing HTTP response
        update_conversation_title(conversation_id, fallback_title)
        return {"status": "updated", "conversation_id": conversation_id, "title": fallback_title, "fallback": True}

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

        # Compute turn cost from trace events
        turn_cost_usd = sum(
            float(e.get("data", {}).get("cost_usd", 0.0) or 0.0)
            for e in trace_events
            if e.get("type") == "info"
        )
        if not turn_cost_usd:
            tot_in = sum(int(e.get("data", {}).get("input_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
            tot_out = sum(int(e.get("data", {}).get("output_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
            tot_cached = sum(int(e.get("data", {}).get("cached_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
            if tot_in or tot_out:
                turn_cost_usd = calculate_token_cost(
                    input_tokens=tot_in,
                    output_tokens=tot_out,
                    cached_tokens=tot_cached,
                    model_name=used_model,
                    tier=used_tier,
                )
        turn_cost_formatted = round(turn_cost_usd, 4) if turn_cost_usd else None

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
            cost_usd=turn_cost_formatted,
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

        # Compute turn cost from trace events
        turn_cost_usd = sum(
            float(e.get("data", {}).get("cost_usd", 0.0) or 0.0)
            for e in trace_events
            if e.get("type") == "info"
        )
        if not turn_cost_usd:
            tot_in = sum(int(e.get("data", {}).get("input_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
            tot_out = sum(int(e.get("data", {}).get("output_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
            tot_cached = sum(int(e.get("data", {}).get("cached_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
            if tot_in or tot_out:
                turn_cost_usd = calculate_token_cost(
                    input_tokens=tot_in,
                    output_tokens=tot_out,
                    cached_tokens=tot_cached,
                    model_name=used_model,
                    tier=used_tier,
                )
        turn_cost_formatted = round(turn_cost_usd, 4) if turn_cost_usd else None

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
            "cost_usd": turn_cost_formatted,
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
    # - Non-blocking event_queue.get_nowait() prevents starving the asyncio event loop thread
    # - Periodic SSE comment ping packets (': ping\n\n') keep HTTP connections open across browser and proxy timeouts
    async def event_generator():
        last_ping_time = time.time()
        try:
            while True:
                # Detect if the client closed browser tab or canceled request
                if await req.is_disconnected():
                    break

                try:
                    # Non-blocking poll of thread-safe FIFO queue
                    event = event_queue.get_nowait()
                except queue.Empty:
                    # Yield execution to the asyncio event loop so other concurrent tasks can progress
                    await asyncio.sleep(0.05)
                    # RFC 8895: Emit periodic SSE comment line (': ping\n\n') every 10s of idle wait to keep TCP alive
                    now_ts = time.time()
                    if now_ts - last_ping_time >= 10.0:
                        last_ping_time = now_ts
                        yield ": ping\n\n"
                    continue

                last_ping_time = time.time()
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
