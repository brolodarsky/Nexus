"""
agents.py — Agent status and interaction routes.
Bridges the Next.js frontend to the existing LangGraph multi-agent swarm.
"""

import asyncio
import io
import json
import mimetypes
from pathlib import Path
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from PIL import Image

# FastAPI primitives:
# - APIRouter: Modular sub-application for grouping related routes under a common prefix (/api/agents)
# - HTTPException: Raises structured HTTP error responses (e.g., 400 Bad Request, 500 Internal Server Error)
# - Request: Represents the raw incoming HTTP request, used to detect client disconnects during streaming
# - UploadFile, File: Handles multipart/form-data image attachment uploads from the chat composer
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
# StreamingResponse: Streams chunks of data (SSE) over an open HTTP connection without buffering entire response
# FileResponse: Streams stored binary assets (uploaded images) back to the browser
from fastapi.responses import FileResponse, StreamingResponse
# Pydantic BaseModel: Validates incoming request JSON payloads and serializes outgoing response schemas
from pydantic import BaseModel
from nexus.core.constants import PROJECT_ROOT
# trace_bus: Global pub/sub event bus where LangGraph agents emit live trace events (tools, LLM calls)
from nexus.core.cost import calculate_token_cost
from nexus.core.trace import trace_bus
# run_logger: Persists formatted execution run snapshots to logs/runs/ for observability and evals
from nexus.core.run_logger import log_run, list_runs, get_run
# chats_db: SQLite data access layer for conversations and chat history
from nexus.core.chats_db import (
    log_message, get_chat_history,
    create_conversation, get_conversations, get_conversation,
    delete_conversation, update_conversation_title,
    revert_last_turn,
)
from nexus.core.hitl_queue import cancel_pending_transactions_for_conversation
from nexus.core.blackboard import clear_bulletins
from nexus.agent.graph import (
    get_latest_checkpoint_id,
    rollback_checkpoints_for_thread,
    register_cancel_event,
    unregister_cancel_event,
    is_thread_cancelled,
)

# Upload storage directory for chat image attachments
UPLOADS_DIR = PROJECT_ROOT / "logs" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 20MB maximum allowed upload file size
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# 1600px maximum edge dimension for high-fidelity multimodal vision inference without excessive token inflation
MAX_IMAGE_DIM = 1600

# APIRouter instance mounted in main.py under prefix="/api/agents"
router = APIRouter()

# ── Request / Response Models ─────────────────────────────────

# Pydantic schema for incoming chat requests
class AskRequest(BaseModel):
    query: str                          # Raw user prompt text
    conversation_id: str                # UUID linking to chats.db conversation thread
    model_tier: Optional[str] = None    # Optional per-turn model tier/ID override ("strong", "medium", "low")
    images: Optional[list[str]] = None  # Optional list of image URLs/paths (e.g. ["/api/agents/uploads/<uuid>.png"])



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


# Pydantic schemas for the Stop & Revert endpoint
class StopAndRevertRequest(BaseModel):
    conversation_id: str                # UUID identifying the conversation thread to stop and revert


class StopAndRevertResponse(BaseModel):
    status: str                         # Outcome status (e.g. "stopped_and_reverted")
    restored_query: str                 # Reverted prompt text restored to the composer
    restored_images: list[str] = []     # Any staged/attached image URLs restored to the composer
    cancelled_hitl_count: int = 0       # Number of pending HITL file mutations cancelled
    reverted_messages_count: int = 0    # Number of messages purged from chats.db


class ActiveRun:
    """Tracks runtime context, cancellation tokens, and SSE event queues for an in-flight agent turn."""

    def __init__(
        self,
        conversation_id: str,
        query: str,
        images: Optional[list[str]],
        cancel_event: threading.Event,
        pre_turn_checkpoint_id: Optional[str],
        event_queue: queue.Queue,
    ):
        self.conversation_id = conversation_id
        self.query = query
        self.images = images or []
        self.cancel_event = cancel_event
        self.pre_turn_checkpoint_id = pre_turn_checkpoint_id
        self.event_queue = event_queue
        self.start_time = time.time()
        self.is_stopped = False


# Thread-safe dictionary tracking active runs per conversation UUID
_active_runs: dict[str, ActiveRun] = {}
_active_runs_lock = threading.Lock()


# ── Image Upload & Asset Routes ──────────────────────────────

# Accepts uploaded image files from the chat composer, validates and optimizes them
@router.post("/upload")
async def upload_image_file(file: UploadFile = File(...)):
    """
    Accepts an uploaded image file, validates content type and image integrity,
    resizes/optimizes oversized dimensions (max 1600px edge), persists the asset
    to `logs/uploads/`, and returns its accessible relative URL path.
    """
    content_type = (file.content_type or "").lower()
    raw_filename = (file.filename or "").lower()
    is_image = content_type.startswith("image/") or raw_filename.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
    )
    if not is_image:
        raise HTTPException(
            status_code=400,
            detail="Only image files (PNG, JPEG, WEBP, GIF, BMP) are supported.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image size exceeds maximum 20MB limit.")

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        # Re-open after verify() since verify() alters internal stream pointer
        img = Image.open(io.BytesIO(file_bytes))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Corrupted or invalid image file: {str(exc)}")

    # Determine extension and format mapping
    original_format = (img.format or "PNG").upper()
    ext_map = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif", "BMP": ".bmp"}
    ext = ext_map.get(original_format, ".png")

    # Resize oversized images preserving aspect ratio
    if img.width > MAX_IMAGE_DIM or img.height > MAX_IMAGE_DIM:
        img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.Resampling.LANCZOS)

    unique_filename = f"{uuid.uuid4().hex}{ext}"
    out_path = UPLOADS_DIR / unique_filename

    # Handle transparent PNG/RGBA conversion when saving to JPEG
    save_format = original_format if original_format in ext_map else "PNG"
    if save_format == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.save(out_path, format=save_format, optimize=True)

    mime, _ = mimetypes.guess_type(str(out_path))
    return {
        "url": f"/api/agents/uploads/{unique_filename}",
        "filename": unique_filename,
        "mime_type": mime or content_type or "image/png",
        "width": img.width,
        "height": img.height,
    }


# Serves stored image attachments to the Next.js Chat UI
@router.get("/uploads/{filename}")
async def get_uploaded_image(filename: str):
    """
    Serves a locally uploaded image from `logs/uploads/` with path-traversal prevention.
    """
    safe_name = Path(filename).name
    file_path = UPLOADS_DIR / safe_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded image not found.")

    mime, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(file_path, media_type=mime or "application/octet-stream")


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
async def ask_brain_history(conversation_id: str, limit: Optional[int] = None):
    """Returns the ordered chat history for a given conversation UUID."""
    return get_chat_history(conversation_id=conversation_id, limit=limit)


# Synchronous (non-streaming) one-shot agent execution
@router.post("/ask", response_model=AskResponse)
async def ask_brain(request: AskRequest):
    """
    Routes a natural-language query through the Content Router agent or active sticky agent,
    waits for execution to finish, logs to SQLite, and returns the response JSON.
    """
    # Guard clause against empty queries when no images are attached
    effective_query = request.query.strip()
    if not effective_query and not request.images:
        raise HTTPException(status_code=400, detail="Query or image attachment cannot be empty.")
    if not effective_query:
        effective_query = "Analyze the attached image(s)."

    try:
        t0 = time.time()
        conversation_id = request.conversation_id
        # Phase 1: Persist user message to SQLite chats.db before running agents
        log_message(
            role="user",
            content=effective_query,
            conversation_id=conversation_id,
            images=request.images,
        )
        
        # Subscribe to trace_bus so synchronous `/ask` also captures 100% of LLM & Subagent trace steps
        trace_events = []
        def _on_sync_trace(evt):
            trace_events.append(evt)
        unsub_sync = trace_bus.subscribe(_on_sync_trace)

        try:
            # Phase 2: Invoke the unified NexusAgent directly with optional per-turn model and image overrides
            from nexus.agent.api import run_nexus_agent_with_trace
            result = run_nexus_agent_with_trace(
                query=effective_query,
                thread_id=conversation_id,
                model_tier=request.model_tier,
                images=request.images,
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
    images: Optional[list[str]] = None,
):
    """
    Runs agent graph execution in a background thread so the async event loop is not blocked.
    Collects trace events via trace_bus subscription and pushes the final 'done' event to event_queue.
    Supports atomic interruption and zero-vestige turn reversion via `Stop & Revert`.
    """
    t0 = time.time()
    effective_query = query.strip() or "Analyze the attached image(s)."

    # Capture checkpointer baseline BEFORE writing messages or graph state so rollback is 100% deterministic
    pre_turn_checkpoint_id = get_latest_checkpoint_id(conversation_id)
    cancel_event = threading.Event()
    register_cancel_event(conversation_id, cancel_event)

    active_run = ActiveRun(
        conversation_id=conversation_id,
        query=effective_query,
        images=images,
        cancel_event=cancel_event,
        pre_turn_checkpoint_id=pre_turn_checkpoint_id,
        event_queue=event_queue,
    )
    with _active_runs_lock:
        _active_runs[conversation_id] = active_run

    # Log user query and image attachments to database immediately
    log_message(
        role="user",
        content=effective_query,
        conversation_id=conversation_id,
        images=images,
    )
    
    # Subscribe to trace_bus to capture all LLM and tool events emitted during this run
    trace_events = []
    def _on_trace(evt):
        trace_events.append(evt)
    unsub = trace_bus.subscribe(_on_trace)

    try:
        # Check if already cancelled before invoking graph
        if is_thread_cancelled(conversation_id) or active_run.is_stopped:
            return

        # Invoke the unified NexusAgent directly with optional per-turn model and image overrides
        from nexus.agent.api import run_nexus_agent_with_trace
        result = run_nexus_agent_with_trace(
            query=effective_query,
            thread_id=conversation_id,
            model_tier=model_tier,
            images=images,
        )

        # Post-execution cancellation check: do not commit results or logs if cancelled while agent was running
        if is_thread_cancelled(conversation_id) or active_run.is_stopped:
            return

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
    except InterruptedError:
        # Interrupted cleanly by user via Stop & Revert: push clean terminal event without recording partial error
        event_queue.put({
            "type": "info",
            "message": "⏹ Agent execution stopped and reverted by user.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        event_queue.put({
            "type": "done",
            "response": "",
            "stopped": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        unregister_cancel_event(conversation_id)
        with _active_runs_lock:
            if _active_runs.get(conversation_id) is active_run:
                _active_runs.pop(conversation_id, None)


# Server-Sent Events (SSE) streaming endpoint
@router.post("/ask/stream")
async def ask_brain_stream(request: AskRequest, req: Request):
    """
    SSE streaming endpoint for live Thinking Panel updates.
    Spawns a background thread to run the agent, subscribes to trace_bus,
    and yields SSE data packets (data: {...}\n\n) as events occur.
    """
    effective_query = request.query.strip()
    if not effective_query and not request.images:
        raise HTTPException(status_code=400, detail="Query or image attachment cannot be empty.")
    if not effective_query:
        effective_query = "Analyze the attached image(s)."

    # Thread-safe FIFO queue to transfer events from background thread to async generator
    event_queue = queue.Queue()

    # Subscribe to trace_bus: every time an agent prints/emits a trace step, push it to event_queue
    unsubscribe = trace_bus.subscribe(lambda evt: event_queue.put(evt))

    # Spawn synchronous agent pipeline in background OS thread (daemon=True allows clean shutdown)
    pipeline_thread = threading.Thread(
        target=_run_pipeline, 
        args=(effective_query, request.conversation_id, event_queue, request.model_tier, request.images), 
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


# ── Stop & Revert Endpoint ───────────────────────────────────

@router.post("/stop-and-revert", response_model=StopAndRevertResponse)
async def stop_and_revert_turn(req: StopAndRevertRequest):
    """
    Stops active agent execution for the target conversation thread and rolls back all state:
      1. Signals the active background worker thread and LangGraph nodes to immediately halt.
      2. Cancels all unapproved pending HITL transactions (file creations, edits, moves, deletions).
      3. Rolls back LangGraph checkpointer SQLite database (`memory.sqlite`) to pre-turn state.
      4. Deletes the turn's user and assistant messages from SQLite `chats.db`.
      5. Cleans up any thread-scoped blackboard bulletins posted during the aborted turn.
      6. Returns the user's prompt text and attached images for immediate composer restoration.
    """
    conv_id = req.conversation_id.strip()
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id cannot be empty.")

    # Phase 1: Halt any active in-flight worker thread for this conversation
    with _active_runs_lock:
        active_run = _active_runs.get(conv_id)
        if active_run:
            active_run.is_stopped = True
            active_run.cancel_event.set()
            # Push clean interruption notice onto SSE event queue so frontend terminates streaming immediately
            try:
                active_run.event_queue.put({
                    "type": "info",
                    "message": "⏹ Execution stopped and reverted by user.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                active_run.event_queue.put({
                    "type": "done",
                    "response": "",
                    "stopped": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass

    # Phase 2: Cancel all staged unapproved HITL transactions for this thread
    cancelled_tx_ids = cancel_pending_transactions_for_conversation(conv_id)

    # Phase 3: Rollback LangGraph checkpointer memory in memory.sqlite
    pre_checkpoint = active_run.pre_turn_checkpoint_id if active_run else None
    rollback_checkpoints_for_thread(conv_id, pre_turn_checkpoint_id=pre_checkpoint)

    # Phase 4: Rollback chats.db messages and extract prompt to restore
    revert_data = revert_last_turn(conv_id)

    restored_query = ""
    restored_images: list[str] = []
    reverted_count = 0

    if revert_data:
        restored_query = revert_data["restored_query"]
        restored_images = revert_data["images"]
        reverted_count = revert_data["deleted_count"]
    elif active_run:
        restored_query = active_run.query
        restored_images = active_run.images

    # Phase 5: Clean up thread Blackboard bulletins if any were created during this turn
    try:
        clear_bulletins(thread_id=conv_id)
    except Exception:
        pass

    return StopAndRevertResponse(
        status="stopped_and_reverted",
        restored_query=restored_query,
        restored_images=restored_images,
        cancelled_hitl_count=len(cancelled_tx_ids),
        reverted_messages_count=reverted_count,
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
