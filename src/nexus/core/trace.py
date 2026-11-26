"""
trace.py — Lightweight console tracer and event bus for the Nexus multi-agent pipeline.

Each agent creates an AgentTracer with a unique color. All output is printed
immediately (flush=True) with a colored prefix so you can visually scan the
scrollback and see which agent did what.

Additionally, all trace events are pushed to a global TraceEventBus so they
can be streamed to the GUI via SSE and persisted live to SQLite (`trace_events`).
Console printing and event bus emission are independent — disabling one does not affect the other.

No external dependencies — uses ANSI escape codes directly.
"""

# contextvars: Provides execution-context-local variable storage for thread_id / conversation_id / run_id isolation
import contextvars
# threading: Used for thread synchronization (Lock) to prevent race conditions during concurrent subscriber registration
import threading
import time
import uuid
from datetime import datetime, timezone
# Callable: Type hint for functions passed as arguments (callbacks)
# Optional, Any, Tuple: Type hints for nullable values, arbitrary dictionary payloads, and subscriber tuples
from typing import Any, Callable, Optional, Tuple

from nexus.core.secret_scrubber import approx_token_count

# ── ANSI Escape Codes ────────────────────────────────────────────────────────
# ANSI sequences (ESC [ <code > m) instruct terminal emulators to change text color and style
# \033 is the octal representation of the ASCII Escape character (27)
COLORS = {
    "cyan":    "\033[96m", # High-intensity cyan (used by NexusAgent)
    "yellow":  "\033[93m", # High-intensity yellow (used by Content Router)
    "green":   "\033[92m", # High-intensity green (used by Librarian)
    "magenta": "\033[95m", # High-intensity magenta (used by Subagents)
    "blue":    "\033[94m", # High-intensity blue
    "red":     "\033[91m", # High-intensity red (errors / warnings)
    "white":   "\033[97m", # High-intensity white (general info)
}
RESET  = "\033[0m"  # Resets text formatting back to default terminal style
DIM    = "\033[2m"  # Reduces text brightness (useful for secondary details/results)
BOLD   = "\033[1m"  # Increases font weight for agent tags and tool names

# Keep RESULT_TRUNCATE_LEN exported for backward-compatibility imports, though trace emission is now 100% lossless
RESULT_TRUNCATE_LEN = 100000 


# ── Thread-Scoped Trace Execution Context ─────────────────────────────────────

# Context variable holding the currently active conversation/thread UUID for trace event scoping
_current_trace_thread_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_trace_thread_id", default=None
)
# Context variable holding the currently active `runs.run_id` so emitted events stream live into SQLite
_current_trace_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_trace_run_id", default=None
)

# Thread-safe fallback lookup mapping `thread_id -> run_id` for worker threads where contextvars weren't copied
_thread_run_lock = threading.Lock()
_thread_run_ids: dict[str, str] = {}


def set_trace_thread_id(thread_id: Optional[str]) -> contextvars.Token:
    """Sets the active conversation/thread UUID in the execution context, returning a reset Token."""
    return _current_trace_thread_id.set(thread_id)


def get_trace_thread_id() -> Optional[str]:
    """Retrieves the active conversation/thread UUID from the execution context, or None."""
    return _current_trace_thread_id.get()


def reset_trace_thread_id(token: contextvars.Token) -> None:
    """Restores the prior conversation/thread UUID in the execution context using the supplied Token."""
    _current_trace_thread_id.reset(token)


def set_trace_run_id(run_id: Optional[str]) -> contextvars.Token:
    """Sets the active `runs.run_id` in the execution context, returning a reset Token."""
    return _current_trace_run_id.set(run_id)


def get_trace_run_id() -> Optional[str]:
    """Retrieves the active `runs.run_id` from the execution context, or None."""
    return _current_trace_run_id.get()


def reset_trace_run_id(token: contextvars.Token) -> None:
    """Restores the prior `runs.run_id` in the execution context using the supplied Token."""
    _current_trace_run_id.reset(token)


def bind_thread_run_id(thread_id: Optional[str], run_id: Optional[str]) -> None:
    """Associate a `thread_id` with its active `run_id` so spawned worker threads inherit live DB persistence."""
    if not thread_id or not run_id:
        return
    with _thread_run_lock:
        _thread_run_ids[thread_id] = run_id


def unbind_thread_run_id(thread_id: Optional[str]) -> None:
    """Clear the `thread_id -> run_id` mapping once a turn completes or aborts."""
    if not thread_id:
        return
    with _thread_run_lock:
        _thread_run_ids.pop(thread_id, None)


def resolve_thread_run_id(thread_id: Optional[str]) -> Optional[str]:
    """Look up the active `run_id` from contextvars first, then thread mapping."""
    ctx_run = _current_trace_run_id.get()
    if ctx_run:
        return ctx_run
    if thread_id:
        with _thread_run_lock:
            return _thread_run_ids.get(thread_id)
    return None


# ── Trace Event Bus (Pub/Sub Pattern) ────────────────────────────────────────

class TraceEventBus:
    """
    Thread-safe Publish/Subscribe (Pub/Sub) event broker for agent trace events.
    Decouples agent execution from consumers: agents emit events without knowing
    who is listening (e.g., SSE streaming endpoints, logging daemons, or evaluators).
    Supports per-thread isolation so concurrent conversation streams receive only
    their own events.
    """

    def __init__(self):
        # Mutex lock ensuring thread-safe access to the subscribers dictionary
        self._lock = threading.Lock()
        # Maps unique integer subscriber IDs to a tuple of (callback, Optional[thread_id])
        self._subscribers: dict[int, Tuple[Callable[[dict], None], Optional[str]]] = {}
        # Monotonically increasing ID counter for assigning unique subscriber tokens
        self._next_id = 0

    def subscribe(
        self,
        callback: Callable[[dict], None],
        thread_id: Optional[str] = None,
    ) -> Callable[[], None]:
        """
        Registers a callback function to be invoked whenever a matching trace event is emitted.
        
        @param callback: A callable that accepts a single event dict: Callable[[dict], None].
        @param thread_id: Optional conversation/thread UUID. If specified, the callback will only
                          be invoked for events originating from this thread_id. If None, the callback
                          acts as a global subscriber receiving all trace events.
        @returns: A parameterless unsubscribe closure () -> None that cleanly removes the listener.
        """
        # Acquire lock to safely increment ID and insert into subscriber dictionary
        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            self._subscribers[sub_id] = (callback, thread_id)

        # Return a closure capturing sub_id so callers can easily unsubscribe
        def unsubscribe():
            with self._lock:
                self._subscribers.pop(sub_id, None)

        return unsubscribe

    def emit(self, event: dict):
        """
        Fans out an event dictionary to matching active subscribers.
        Takes a snapshot of subscriber entries under lock, then executes callbacks outside the lock.
        Filters by thread_id if the subscriber registered with thread scoping.
        """
        with self._lock:
            # Create a shallow list copy of (callback, thread_id) tuples to minimize lock hold time
            subscribers = list(self._subscribers.values())
            
        event_thread_id = event.get("thread_id")
        for cb, sub_thread_id in subscribers:
            # If subscriber specified a thread_id, enforce strict thread isolation
            if sub_thread_id is not None:
                # Discard events destined for a different thread, or untargeted events with no thread_id
                if event_thread_id != sub_thread_id:
                    continue

            try:
                cb(event)
            except Exception:
                # Defensive try/except: prevents a failing subscriber from interrupting agent execution
                pass


# Global singleton instance — all AgentTracer instances emit here, FastAPI SSE endpoints subscribe here
trace_bus = TraceEventBus()


# ── Agent Tracer ─────────────────────────────────────────────────────────────

class AgentTracer:
    """
    Dual-output telemetry logger for an individual agent or isolated subagent instance.
    1. Terminal Output: Formats and prints ANSI-colored logs to stdout with bounded previews.
    2. SSE & SQLite Stream: Emits lossless, content-addressed structured event dictionaries to `trace_bus`,
       enriched with hierarchical `agent_id`, `parent_id`, and `run_id` lineage.
    """

    # Optional[str] allows parent_id to be None for root agents (NexusAgent) or set to the parent's agent_id for subagents
    def __init__(
        self,
        agent_name: str,
        color: str = "white",
        agent_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self.color = color
        # Unique node identifier for DAG graph construction (e.g., "nexus", "subagent-1")
        self.agent_id = agent_id or agent_name.lower().replace(" ", "_")
        # Parent node identifier linking subagent branches back to their spawning orchestrator
        self.parent_id = parent_id
        # Explicit conversation thread UUID if bound to a specific thread lifecycle
        self.thread_id = thread_id
        # Resolves color code string; defaults to white if color is not in lookup table
        self.color_code = COLORS.get(color, COLORS["white"])
        # Monotonically increasing step counter within this agent's lifecycle
        self._step_counter = 0

    def _prefix(self) -> str:
        """Constructs the stylized terminal prefix (e.g. '[NexusAgent]' or '[Subagent #1 (low)]')."""
        return f"{self.color_code}{BOLD}[{self.agent_name}]{RESET}"

    def _print(self, icon: str, message: str):
        """Prints formatted message immediately to stdout with flush=True to avoid buffering delays."""
        try:
            print(f"  {self._prefix()} {icon} {message}", flush=True)
        except UnicodeEncodeError:
            # Windows CP1252 / charmap console fallback
            clean_msg = message.encode("ascii", errors="replace").decode("ascii")
            print(f"  {self._prefix()} [*] {clean_msg}", flush=True)

    def _emit(self, event_type: str, message: str, data: Optional[dict[str, Any]] = None):
        """Builds a standardized, lossless trace event payload and publishes it to trace_bus."""
        self._step_counter += 1
        # Resolve effective thread_id from instance property, context variable, or payload data
        effective_thread_id = (
            self.thread_id
            or get_trace_thread_id()
            or (data.get("thread_id") if isinstance(data, dict) else None)
        )
        effective_run_id = (
            (data.get("run_id") if isinstance(data, dict) else None)
            or resolve_thread_run_id(effective_thread_id)
        )
        event: dict[str, Any] = {
            "id": str(uuid.uuid4())[:8],
            "step": self._step_counter,
            "type": event_type,
            "agent": self.agent_name,
            "agent_id": self.agent_id,
            "parent_id": self.parent_id,
            "thread_id": effective_thread_id,
            "color": self.color,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if effective_run_id:
            event["run_id"] = effective_run_id
        if data is not None:
            event["data"] = data
        trace_bus.emit(event)

    # ── Lifecycle Methods ────────────────────────────────────────────────────

    def agent_start(self, context: str = "", metadata: Optional[dict[str, Any]] = None):
        """Signals that an agent has begun its execution loop, preserving the full untruncated prompt/context."""
        self._step_counter = 0
        msg = f"Starting — {context}" if context else "Starting..."
        terminal_preview = (
            msg
            if len(msg) <= 500
            else f"{msg[:500]}… ({len(msg):,} chars · ~{approx_token_count(len(msg)):,} tok)"
        )
        self._print("▶", f"{BOLD}{terminal_preview}{RESET}")
        payload: dict[str, Any] = {"context": context}
        if metadata:
            payload.update(metadata)
        self._emit("agent_start", msg, payload)

    def agent_end(self, summary: str = ""):
        """Signals that an agent has completed its execution loop."""
        msg = f"Done — {summary}" if summary else "Done."
        self._print("■", f"{DIM}{msg}{RESET}")
        self._emit("agent_end", msg, {"summary": summary} if summary else None)

    # ── LLM Telemetry ────────────────────────────────────────────────────────

    def llm_call(self, metadata: Optional[dict[str, Any]] = None):
        """Traces the dispatch of a prompt payload to the language model."""
        ctx_summary = metadata.get("context_summary") if isinstance(metadata, dict) else None
        if isinstance(ctx_summary, dict) and ctx_summary.get("approx_tokens"):
            msg = (
                f"Calling LLM (ctx: {int(ctx_summary.get('total_chars', 0)):,} chars · "
                f"~{int(ctx_summary['approx_tokens']):,} tok across {int(ctx_summary.get('section_count', 0))} blocks)..."
            )
        else:
            msg = "Calling LLM..."
        self._print("🤖", msg)
        self._emit("llm_call", msg, metadata)

    # `thinking_text: str` is the untruncated natural-language reasoning summary extracted from an AIMessage.
    # `metadata: Optional[dict[str, Any]]` optionally carries turn/model telemetry (e.g. `model_tier`, `model_name`, `turn`).
    def llm_thinking(self, thinking_text: str, metadata: Optional[dict[str, Any]] = None):
        """Traces the model's natural-language thinking/reasoning summary losslessly to trace_bus with a bounded stdout preview."""
        if not thinking_text or not thinking_text.strip():
            return
        # Bound stdout preview to 300 chars so multi-paragraph thinking blocks do not flood terminal scrollback
        terminal_preview = (
            thinking_text
            if len(thinking_text) <= 300
            else f"{thinking_text[:300]}… ({len(thinking_text):,} chars · ~{approx_token_count(len(thinking_text)):,} tok)"
        )
        self._print("🧠", f"{DIM}{terminal_preview}{RESET}")
        payload: dict[str, Any] = {"thinking": thinking_text}
        if metadata:
            payload.update(metadata)
        self._emit("llm_thinking", thinking_text, payload)

    def llm_response(self, full_text: str = "", metadata: Optional[dict[str, Any]] = None):
        """Traces the receipt of text or tool calls back from the language model without truncation."""
        if full_text:
            self._print("💬", f"{DIM}{full_text}{RESET}")
            payload: dict[str, Any] = {"response": full_text}
            if metadata:
                payload.update(metadata)
            self._emit("llm_response", full_text, payload)
        else:
            self._print("💬", f"{DIM}(response received){RESET}")
            self._emit("llm_response", "(response received)", metadata)

    # ── Tool Telemetry ───────────────────────────────────────────────────────

    def tool_call(self, tool_name: str, args: Optional[dict[str, Any]] = None, call_id: Optional[str] = None):
        """
        Traces tool invocation and preserves 100% untruncated arguments in structured data payload.
        Formats a bounded preview in terminal output and `message` to prevent duplicating multi-megabyte
        argument strings (e.g., file writes or note replacements) twice within the same event record.
        """
        args_dict = args or {}
        pairs = []
        for k, v in args_dict.items():
            val_str = str(v)
            # Bound key-value previews in the string summary while preserving full data in payload['args']
            if len(val_str) > 150:
                pairs.append(f"{k}={val_str[:150]}… ({len(val_str):,} chars · ~{approx_token_count(len(val_str)):,} tok)")
            else:
                pairs.append(f"{k}={val_str}")
        args_str = f"({', '.join(pairs)})" if pairs else ""
        self._print("🔧", f"Calling tool: {BOLD}{tool_name}{RESET}{args_str}")
        payload: dict[str, Any] = {"tool": tool_name, "args": args_dict}
        if call_id:
            payload["call_id"] = call_id
        self._emit("tool_call", f"Calling tool: {tool_name}{args_str}", payload)

    def tool_result(self, tool_name: str, result: str = "", call_id: Optional[str] = None):
        """
        Traces the return value from a completed tool execution.
        Preserves the 100% untruncated structured payload in `data["result"]` for the DAG/Graph viewer,
        while formatting a bounded summary string in `message` and terminal output to prevent multi-megabyte string duplication.
        """
        # Bounded terminal output prevents multi-hundred-kilobyte file dumps from choking stdout / console buffers
        tok_est = approx_token_count(len(result))
        terminal_preview = (
            result if len(result) <= 300 else f"{result[:300]}… ({len(result):,} chars · ~{tok_est:,} tok)"
        )
        self._print("✅", f"{tool_name} → {DIM}{terminal_preview}{RESET}")
        payload: dict[str, Any] = {"tool": tool_name, "result": result}
        if call_id:
            payload["call_id"] = call_id
        # Bounded summary message: prevents storing the exact same multi-hundred KB payload twice in the same JSON event
        summary_msg = (
            f"{tool_name} → ({len(result):,} chars output · ~{tok_est:,} tok)"
            if len(result) > 200
            else f"{tool_name} → {result}"
        )
        self._emit("tool_result", summary_msg, payload)

    def tool_error(self, tool_name: str, error: str, call_id: Optional[str] = None):
        """Traces a tool exception or failure."""
        self._print("❌", f"{tool_name} error: {error}")
        payload: dict[str, Any] = {"tool": tool_name, "error": error}
        if call_id:
            payload["call_id"] = call_id
        self._emit("tool_error", f"{tool_name} error: {error}", payload)

    # ── Routing & Delegation Telemetry ───────────────────────────────────────

    def route(self, domain: str, confidence: float = 0.0):
        """Traces a domain classification decision made by the Content Router."""
        conf_str = f" (confidence: {confidence:.2f})" if confidence else ""
        self._print("🔀", f"Routing to {BOLD}{domain}{RESET}{conf_str}")
        self._emit("route", f"Routing to {domain}{conf_str}",
                    {"domain": domain, "confidence": confidence})

    def delegate(self, target_agent: str):
        """Traces the handoff of control from Router to a specialized domain agent."""
        self._print("📤", f"Delegating to {BOLD}{target_agent}{RESET}")
        self._emit("delegate", f"Delegating to {target_agent}",
                    {"target": target_agent})

    def info(self, message: str, data: Optional[dict[str, Any]] = None):
        """Traces general operational status information (e.g. token usage, cache hits, retries)."""
        self._print("ℹ️", message)
        self._emit("info", message, data)


# ── String Utility ───────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int = RESULT_TRUNCATE_LEN) -> str:
    """
    Legacy helper retained for import compatibility.
    Returns the full text untouched so no trace steps or tool outputs are cut off.
    """
    return text.strip() if isinstance(text, str) else str(text)
