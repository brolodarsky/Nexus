"""
agents.py — Agent status and interaction routes.
Bridges the Next.js frontend to the existing LangGraph multi-agent swarm.
"""

import asyncio
import io
import json
import math
import mimetypes
from pathlib import Path
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional
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
from nexus.core.constants import PROJECT_ROOT, resolve_model_config
# trace_bus: Global pub/sub event bus where LangGraph agents emit live trace events (tools, LLM calls)
from nexus.core.cost import calculate_token_cost
from nexus.core.trace import reset_trace_thread_id, set_trace_thread_id, trace_bus
# run_logger: Persists formatted execution run snapshots to logs/runs/ for observability and evals
from nexus.core.run_logger import log_run, list_runs, get_run
# chats_db: SQLite data access layer for conversations and chat history
from nexus.core.chats_db import (
    log_message, get_chat_history, get_message_trace,
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
    model_name: str | None = None       # Concrete provider model identifier (e.g., "gemini-4-argon", "gemini-4-hydrogen")
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


# Standard SSE response headers disabling HTTP caching and reverse-proxy chunk buffering
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sanitize_for_json(value):
    """Recursively converts non-finite floats (NaN/Inf) to None so SSE JSON never fails browser JSON.parse."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value


def _safe_json_dumps(payload: dict) -> str:
    """Serializes SSE payloads strictly as valid JSON, coercing non-finite numbers and exotic objects."""
    try:
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        sanitized = _sanitize_for_json(payload)
        return json.dumps(sanitized, ensure_ascii=False, allow_nan=False, default=str)


class ActiveRun:
    """Tracks runtime context, cancellation tokens, lossless trace backlog, and multi-client SSE subscribers."""

    # Optional[...] parameters preserve backward compatibility with unit tests that instantiate ActiveRun directly
    def __init__(
        self,
        conversation_id: str,
        query: str,
        images: Optional[list[str]],
        cancel_event: threading.Event,
        pre_turn_checkpoint_id: Optional[str],
        event_queue: Optional[queue.Queue] = None,
        model_tier: Optional[str] = None,
        model_name: Optional[str] = None,
        model_label: Optional[str] = None,
        user_message_id: Optional[int] = None,
    ):
        self.conversation_id = conversation_id
        self.query = query
        self.images = images or []
        self.cancel_event = cancel_event
        self.pre_turn_checkpoint_id = pre_turn_checkpoint_id
        # Optional legacy queue retained for Stop & Revert test assertions
        self.event_queue = event_queue
        self.model_tier = model_tier
        self.model_name = model_name
        self.model_label = model_label
        self.user_message_id = user_message_id
        self.start_time = time.time()
        self.is_stopped = False
        # Mutex protecting trace_events, subscribers, and terminal_event so re-attaching clients never drop or duplicate steps
        self.lock = threading.Lock()
        self.trace_events: list[dict] = []
        self.subscribers: list[queue.Queue] = []
        self.terminal_event: Optional[dict] = None

    def publish_trace(self, event: dict) -> None:
        """Records a live trace event in the run backlog and fans it out to every connected SSE subscriber."""
        with self.lock:
            # Ignore late-arriving events once the run has reached a terminal state
            if self.terminal_event is not None:
                return
            self.trace_events.append(event)
            if self.event_queue is not None:
                self.event_queue.put(event)
            for sub_q in self.subscribers:
                sub_q.put(event)

    def publish_terminal(self, event: dict) -> None:
        """Stores the terminal ('done' or 'error') packet once and delivers it to all attached subscribers."""
        with self.lock:
            # Guard against duplicate terminal events when Stop & Revert races with worker teardown
            if self.terminal_event is not None:
                return
            self.terminal_event = event
            if self.event_queue is not None:
                self.event_queue.put(event)
            for sub_q in self.subscribers:
                sub_q.put(event)

    def subscribe(self) -> tuple[list[dict], Optional[dict], Optional[queue.Queue]]:
        """Atomically snapshots emitted trace history and registers a live queue if the turn is still running."""
        with self.lock:
            backlog = list(self.trace_events)
            if self.terminal_event is not None:
                return backlog, self.terminal_event, None
            # Fresh thread-safe FIFO queue receiving every event emitted after this snapshot
            sub_q: queue.Queue = queue.Queue()
            self.subscribers.append(sub_q)
            return backlog, None, sub_q

    def unsubscribe(self, sub_q: Optional[queue.Queue]) -> None:
        """Removes a disconnected or completed client queue from fan-out delivery."""
        if sub_q is None:
            return
        with self.lock:
            try:
                self.subscribers.remove(sub_q)
            except ValueError:
                pass

    def snapshot_trace(self) -> list[dict]:
        """Returns a shallow thread-safe copy of all trace events emitted during this run."""
        with self.lock:
            return list(self.trace_events)

    def snapshot_status(self) -> dict:
        """Returns lightweight metadata describing this in-flight run for UI state restoration."""
        with self.lock:
            return {
                "active": not self.is_stopped and self.terminal_event is None,
                "conversation_id": self.conversation_id,
                "query": self.query,
                "model_tier": self.model_tier,
                "model_name": self.model_name,
                "model_label": self.model_label,
                "user_message_id": self.user_message_id,
                "started_at": datetime.fromtimestamp(self.start_time, timezone.utc).isoformat(),
                "step_count": len(self.trace_events),
                "is_stopped": self.is_stopped,
            }


# Thread-safe dictionary tracking active runs per conversation UUID
_active_runs: dict[str, ActiveRun] = {}
_active_runs_lock = threading.Lock()


def _cancel_active_run_record(active_run: ActiveRun) -> None:
    """Marks an ActiveRun stopped, trips its cancellation event, and notifies attached SSE clients."""
    active_run.is_stopped = True
    active_run.cancel_event.set()
    # Push clean interruption notice onto SSE subscribers so frontend terminates streaming immediately
    try:
        active_run.publish_trace({
            "type": "info",
            "message": "⏹ Execution stopped and reverted by user.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        active_run.publish_terminal({
            "type": "done",
            "response": "",
            "stopped": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


# ── Image Upload & Asset Routes ──────────────────────────────

# Accepts uploaded image files and PDF documents from the chat composer, validates and optimizes them
@router.post("/upload")
async def upload_image_file(file: UploadFile = File(...)):
    """
    Accepts an uploaded image file or PDF document, validates content type and integrity,
    resizes/optimizes oversized images (max 1600px edge), rasterizes multi-page PDFs
    into crisp 2x supersampled PNG pages (max 10 pages), persists assets to `logs/uploads/`,
    and returns accessible relative URL paths.
    """
    content_type = (file.content_type or "").lower()
    raw_filename = (file.filename or "").lower()
    is_pdf = content_type == "application/pdf" or raw_filename.endswith(".pdf")
    is_image = content_type.startswith("image/") or raw_filename.endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
    )
    if not is_image and not is_pdf:
        raise HTTPException(
            status_code=400,
            detail="Only image files (PNG, JPEG, WEBP, GIF, BMP) and PDF documents are supported.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds maximum 20MB limit.")

    # ── PDF Document Processing ──────────────────────────────────
    if is_pdf:
        try:
            import pymupdf
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="PDF rendering engine ('pymupdf') is not installed on the server.",
            )

        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Corrupted or invalid PDF document: {str(exc)}")

        total_pages = len(doc)
        if total_pages == 0:
            raise HTTPException(status_code=400, detail="Uploaded PDF contains 0 pages.")

        batch_id = uuid.uuid4().hex

        # Save the full raw PDF file to disk so it can be accessed, read, or filed to the Vault
        pdf_filename = f"{batch_id}.pdf"
        pdf_out_path = UPLOADS_DIR / pdf_filename
        pdf_out_path.write_bytes(file_bytes)

        # Cap visual thumbnail rendering to first 10 pages to preserve token budgets and server latency
        MAX_RENDER_PAGES = 10
        render_page_count = min(total_pages, MAX_RENDER_PAGES)

        page_urls: list[str] = []
        first_dims = (0, 0)

        for page_idx in range(render_page_count):
            page = doc[page_idx]
            # Supersample at 2.0x (144-150 DPI) to ensure small 8pt typography, decimal points, and borders stay crisp
            zoom_matrix = pymupdf.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
            page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Cap oversized dimensions preserving aspect ratio with Lanczos antialiasing
            if page_img.width > MAX_IMAGE_DIM or page_img.height > MAX_IMAGE_DIM:
                page_img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.Resampling.LANCZOS)

            if page_idx == 0:
                first_dims = (page_img.width, page_img.height)

            page_filename = f"{batch_id}_p{page_idx + 1}.png"
            page_out_path = UPLOADS_DIR / page_filename
            page_img.save(page_out_path, format="PNG", optimize=True)
            page_urls.append(f"/api/agents/uploads/{page_filename}")

        primary_url = page_urls[0]
        return {
            "url": primary_url,
            "page_urls": page_urls,
            "filename": pdf_filename,
            "original_filename": Path(raw_filename).name or "document.pdf",
            "mime_type": "application/pdf",
            "page_count": total_pages,
            "rendered_pages": len(page_urls),
            "pdf_url": f"/api/agents/uploads/{pdf_filename}",
            "pdf_path": str(pdf_out_path),
            "width": first_dims[0],
            "height": first_dims[1],
        }

    # ── Standard Image Processing ────────────────────────────────
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
    """Removes a conversation thread by UUID, halting any in-flight run first."""
    with _active_runs_lock:
        active_run = _active_runs.get(conversation_id)
        if active_run:
            _cancel_active_run_record(active_run)
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
    - Invokes fast `tier="low"` LLM (`gemini-4-hydrogen` or `claude-sonnet-4-5`) with low temperature
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
        # Use low-tier model (Hydrogen / Sonnet) for sub-second, ultra-low-cost title summarization
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
async def ask_brain_history(
    conversation_id: str,
    limit: Optional[int] = None,
    include_trace: bool = False,
):
    """
    Returns the ordered chat history for a given conversation UUID.
    By default, excludes heavy execution telemetry traces to keep payload fast (~1KB/turn).
    """
    return get_chat_history(conversation_id=conversation_id, limit=limit, include_trace=include_trace)


@router.get("/messages/{message_id}/trace")
async def get_message_trace_endpoint(message_id: int):
    """
    Retrieves the full, untruncated trace events array for a specific message on demand.
    Enables lazy-loading ThinkingPanel visualizer drawers without bloating standard chat history payloads.
    """
    trace = get_message_trace(message_id)
    return {"message_id": message_id, "trace": trace}


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
        
        # Subscribe to trace_bus so synchronous `/ask` also captures 100% of LLM & Subagent trace steps scoped to this conversation
        trace_events = []
        def _on_sync_trace(evt):
            trace_events.append(evt)
        unsub_sync = trace_bus.subscribe(_on_sync_trace, thread_id=conversation_id)
        trace_token = set_trace_thread_id(conversation_id)

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
            reset_trace_thread_id(trace_token)

        routed_domain = result.get("domain")
        agent_name = "nexus"
        elapsed_sec = time.time() - t0
        response_text = result.get("response", "")
        used_tier = result.get("model_tier")
        used_model = result.get("model_name")

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

        # Phase 4: Persist assistant response + full trace events to SQLite chats.db
        log_message(
            role="assistant",
            content=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            trace=trace_events,
            conversation_id=conversation_id,
            model_tier=used_tier,
            model_name=used_model,
            cost_usd=turn_cost_formatted,
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
    active_run: ActiveRun,
    unsub_trace: Callable[[], None],
    model_tier: Optional[str] = None,
):
    """
    Runs agent graph execution in a background thread so the async event loop is not blocked.
    Uses ActiveRun's buffered trace stream and fan-out subscribers so clients that switch away
    and return (or reload the page) can re-attach mid-turn without losing trace history.
    Supports atomic interruption and zero-vestige turn reversion via `Stop & Revert`.
    """
    t0 = active_run.start_time
    conversation_id = active_run.conversation_id
    effective_query = active_run.query
    images = active_run.images or None
    user_msg_id = active_run.user_message_id

    trace_token = set_trace_thread_id(conversation_id)

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

        # Snapshot all trace events captured in ActiveRun under lock before persisting and publishing terminal status
        captured_traces = active_run.snapshot_trace()

        # Compute turn cost from trace events
        turn_cost_usd = sum(
            float(e.get("data", {}).get("cost_usd", 0.0) or 0.0)
            for e in captured_traces
            if e.get("type") == "info"
        )
        if not turn_cost_usd:
            tot_in = sum(int(e.get("data", {}).get("input_tokens", 0) or 0) for e in captured_traces if e.get("type") == "info")
            tot_out = sum(int(e.get("data", {}).get("output_tokens", 0) or 0) for e in captured_traces if e.get("type") == "info")
            tot_cached = sum(int(e.get("data", {}).get("cached_tokens", 0) or 0) for e in captured_traces if e.get("type") == "info")
            if tot_in or tot_out:
                turn_cost_usd = calculate_token_cost(
                    input_tokens=tot_in,
                    output_tokens=tot_out,
                    cached_tokens=tot_cached,
                    model_name=used_model,
                    tier=used_tier,
                )
        turn_cost_formatted = round(turn_cost_usd, 4) if turn_cost_usd else None

        # Persist assistant message along with full trace array to chats.db, capturing its SQLite primary key
        assistant_msg_id = log_message(
            role="assistant",
            content=response_text,
            agent=agent_name,
            domain=routed_domain,
            confidence=result.get("confidence"),
            trace=captured_traces,
            conversation_id=conversation_id,
            model_tier=used_tier,
            model_name=used_model,
            cost_usd=turn_cost_formatted,
        )

        # Persist structured JSON run snapshot to logs/runs/
        log_run(
            agent_name=agent_name,
            query=effective_query,
            response=response_text,
            thread_id=conversation_id,
            domain=routed_domain,
            confidence=result.get("confidence"),
            reasoning=result.get("reasoning"),
            tool_calls=result.get("tool_calls"),
            trace_events=captured_traces,
            latency_seconds=elapsed_sec,
            metadata={"model_tier": used_tier, "model_name": used_model},
        )

        # Publish terminal 'done' event to every active/re-attached SSE subscriber
        active_run.publish_terminal({
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
            "user_message_id": user_msg_id,
            "assistant_message_id": assistant_msg_id,
        })
    except InterruptedError:
        # Interrupted cleanly by user via Stop & Revert: push clean terminal event without recording partial error
        active_run.publish_trace({
            "type": "info",
            "message": "⏹ Agent execution stopped and reverted by user.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        active_run.publish_terminal({
            "type": "done",
            "response": "",
            "stopped": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        # Push terminal 'error' event to every active/re-attached SSE subscriber on failure
        active_run.publish_terminal({
            "type": "error",
            "message": f"Agent execution failed: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        # Ensure any attached subscriber unblocks even if the worker exited early on cancellation
        if active_run.terminal_event is None:
            active_run.publish_terminal({
                "type": "done",
                "response": "",
                "stopped": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        unsub_trace() # Unsubscribe trace listener to prevent memory leaks
        reset_trace_thread_id(trace_token)
        unregister_cancel_event(conversation_id)
        with _active_runs_lock:
            if _active_runs.get(conversation_id) is active_run:
                _active_runs.pop(conversation_id, None)


# Shared async SSE generator helper used by both initial POST /ask/stream and re-attach GET /ask/stream/{conversation_id}
async def _stream_active_run(
    active_run: ActiveRun,
    req: Request,
    initial_subscription: Optional[tuple[list[dict], Optional[dict], Optional[queue.Queue]]] = None,
):
    """
    Async generator yielding formatted SSE packets (`data: {...}\\n\\n`) from an ActiveRun.
    Replays buffered trace history first, then drains live subscriber queue events with periodic RFC 8895 pings.
    """
    backlog, terminal_evt, sub_queue = (
        initial_subscription if initial_subscription is not None else active_run.subscribe()
    )
    try:
        # Phase 1: Replay any buffered trace events emitted before this SSE stream attached
        for evt in backlog:
            if await req.is_disconnected():
                return
            yield f"data: {_safe_json_dumps(evt)}\n\n"

        # If the turn already terminated before live polling began, emit the terminal packet and close
        if terminal_evt is not None:
            yield f"data: {_safe_json_dumps(terminal_evt)}\n\n"
            return

        if sub_queue is None:
            return

        # Phase 2: Poll non-blockingly for live events while keeping idle connections alive via ': ping' comments
        last_ping_time = time.time()
        while True:
            if await req.is_disconnected():
                break

            try:
                event = sub_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                now_ts = time.time()
                if now_ts - last_ping_time >= 10.0:
                    last_ping_time = now_ts
                    yield ": ping\n\n"
                continue

            last_ping_time = time.time()
            yield f"data: {_safe_json_dumps(event)}\n\n"

            if event.get("type") in ("done", "error"):
                break
    finally:
        active_run.unsubscribe(sub_queue)


# Server-Sent Events (SSE) streaming endpoint
@router.post("/ask/stream")
async def ask_brain_stream(request: AskRequest, req: Request):
    """
    SSE streaming endpoint for live Thinking Panel updates.
    Registers an ActiveRun with buffered trace replay, spawns a background worker thread,
    and yields SSE data packets (`data: {...}\\n\\n`) as events occur.
    """
    effective_query = request.query.strip()
    if not effective_query and not request.images:
        raise HTTPException(status_code=400, detail="Query or image attachment cannot be empty.")
    if not effective_query:
        effective_query = "Analyze the attached image(s)."

    conversation_id = request.conversation_id

    # Guard against two simultaneous turns mutating the same conversation thread concurrently
    with _active_runs_lock:
        existing = _active_runs.get(conversation_id)
        if existing and not existing.is_stopped and existing.terminal_event is None:
            raise HTTPException(
                status_code=409,
                detail="An agent turn is already running in this conversation.",
            )

    # Resolve model metadata upfront so re-attaching UIs display the active turn's exact model label
    resolved_model = resolve_model_config(request.model_tier)
    pre_turn_checkpoint_id = get_latest_checkpoint_id(conversation_id)
    cancel_event = threading.Event()
    register_cancel_event(conversation_id, cancel_event)

    # Persist the initiating user message before starting the worker so reloading/switching threads immediately shows it
    user_msg_id = log_message(
        role="user",
        content=effective_query,
        conversation_id=conversation_id,
        images=request.images,
    )

    active_run = ActiveRun(
        conversation_id=conversation_id,
        query=effective_query,
        images=request.images,
        cancel_event=cancel_event,
        pre_turn_checkpoint_id=pre_turn_checkpoint_id,
        model_tier=resolved_model.get("tier"),
        model_name=resolved_model.get("model_name"),
        model_label=resolved_model.get("label"),
        user_message_id=user_msg_id,
    )

    with _active_runs_lock:
        _active_runs[conversation_id] = active_run

    # Subscribe to trace_bus and attach the initial SSE queue BEFORE starting the worker thread so step #1 is never missed
    unsub_trace = trace_bus.subscribe(active_run.publish_trace, thread_id=conversation_id)
    initial_subscription = active_run.subscribe()

    try:
        pipeline_thread = threading.Thread(
            target=_run_pipeline,
            args=(active_run, unsub_trace, request.model_tier),
            daemon=True,
        )
        pipeline_thread.start()
    except Exception:
        active_run.unsubscribe(initial_subscription[2])
        unsub_trace()
        unregister_cancel_event(conversation_id)
        with _active_runs_lock:
            if _active_runs.get(conversation_id) is active_run:
                _active_runs.pop(conversation_id, None)
        raise

    return StreamingResponse(
        _stream_active_run(active_run, req, initial_subscription=initial_subscription),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# Active-run discovery routes (placed before parameterized /{conversation_id} catch-alls)
@router.get("/ask/active")
async def list_active_runs():
    """Returns metadata snapshots for every conversation currently executing an agent turn in the background."""
    with _active_runs_lock:
        runs = [
            run.snapshot_status()
            for run in _active_runs.values()
            if not run.is_stopped and run.terminal_event is None
        ]
    return {"active_runs": runs}


@router.get("/ask/active/{conversation_id}")
async def get_active_run_status(conversation_id: str):
    """Checks whether a specific conversation has an in-flight agent turn that the UI can re-attach to."""
    with _active_runs_lock:
        run = _active_runs.get(conversation_id)
        if run and not run.is_stopped and run.terminal_event is None:
            return run.snapshot_status()
    return {"active": False, "conversation_id": conversation_id}


@router.get("/ask/stream/{conversation_id}")
async def reattach_brain_stream(conversation_id: str, req: Request):
    """
    Re-attaches a returning client to an in-flight conversation stream via SSE.
    Replays all trace steps captured since the turn began, then streams remaining live steps until completion.
    If the run finished right before connection arrived, emits a `sync_required` event so the UI fetches history.
    """
    with _active_runs_lock:
        active_run = _active_runs.get(conversation_id)

    if not active_run:
        # Run already completed (or never existed); instruct client to reconcile with SQLite history
        async def sync_generator():
            payload = {
                "type": "sync_required",
                "conversation_id": conversation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {_safe_json_dumps(payload)}\n\n"

        return StreamingResponse(
            sync_generator(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return StreamingResponse(
        _stream_active_run(active_run, req),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
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
            _cancel_active_run_record(active_run)

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
