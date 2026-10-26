"""
trace.py — Lightweight console tracer and event bus for the Nexus multi-agent pipeline.

Each agent creates an AgentTracer with a unique color. All output is printed
immediately (flush=True) with a colored prefix so you can visually scan the
scrollback and see which agent did what.

Additionally, all trace events are pushed to a global TraceEventBus so they
can be streamed to the GUI via SSE. Console printing and event bus emission
are independent — disabling one does not affect the other.

No external dependencies — uses ANSI escape codes directly.
"""

# threading: Used for thread synchronization (Lock) to prevent race conditions during concurrent subscriber registration
import threading
import time
import uuid
from datetime import datetime, timezone
# Callable: Type hint for functions passed as arguments (callbacks)
# Optional, Any: Type hints for nullable values and arbitrary dictionary payloads
from typing import Any, Callable, Optional

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


# ── Trace Event Bus (Pub/Sub Pattern) ────────────────────────────────────────

class TraceEventBus:
    """
    Thread-safe Publish/Subscribe (Pub/Sub) event broker for agent trace events.
    Decouples agent execution from consumers: agents emit events without knowing
    who is listening (e.g., SSE streaming endpoints, logging daemons, or evaluators).
    """

    def __init__(self):
        # Mutex lock ensuring thread-safe access to the subscribers dictionary
        self._lock = threading.Lock()
        # Maps unique integer subscriber IDs to their corresponding callback functions
        self._subscribers: dict[int, Callable[[dict], None]] = {}
        # Monotonically increasing ID counter for assigning unique subscriber tokens
        self._next_id = 0

    def subscribe(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        """
        Registers a callback function to be invoked whenever a trace event is emitted.
        
        @param callback: A callable that accepts a single event dict: Callable[[dict], None].
        @returns: A parameterless unsubscribe closure () -> None that cleanly removes the listener.
        """
        # Acquire lock to safely increment ID and insert into subscriber dictionary
        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            self._subscribers[sub_id] = callback

        # Return a closure capturing sub_id so callers can easily unsubscribe
        def unsubscribe():
            with self._lock:
                self._subscribers.pop(sub_id, None)

        return unsubscribe

    def emit(self, event: dict):
        """
        Fans out an event dictionary to all active subscribers.
        Takes a snapshot of subscriber callbacks under lock, then executes them outside the lock.
        """
        with self._lock:
            # Create a shallow list copy of callbacks to minimize lock hold time
            callbacks = list(self._subscribers.values())
            
        for cb in callbacks:
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
    1. Terminal Output: Formats and prints ANSI-colored logs to stdout with full fidelity.
    2. SSE Event Stream: Emits 100% lossless, untruncated structured event dictionaries to the global trace_bus,
       enriched with hierarchical `agent_id` and `parent_id` lineage for DAG/Graph visualization.
    """

    # Optional[str] allows parent_id to be None for root agents (NexusAgent) or set to the parent's agent_id for subagents
    def __init__(
        self,
        agent_name: str,
        color: str = "white",
        agent_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self.color = color
        # Unique node identifier for DAG graph construction (e.g., "nexus", "subagent-1")
        self.agent_id = agent_id or agent_name.lower().replace(" ", "_")
        # Parent node identifier linking subagent branches back to their spawning orchestrator
        self.parent_id = parent_id
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
        event: dict[str, Any] = {
            "id": str(uuid.uuid4())[:8],
            "step": self._step_counter,
            "type": event_type,
            "agent": self.agent_name,
            "agent_id": self.agent_id,
            "parent_id": self.parent_id,
            "color": self.color,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if data is not None:
            event["data"] = data
        trace_bus.emit(event)

    # ── Lifecycle Methods ────────────────────────────────────────────────────

    def agent_start(self, context: str = "", metadata: Optional[dict[str, Any]] = None):
        """Signals that an agent has begun its execution loop, preserving the full untruncated prompt/context."""
        self._step_counter = 0
        msg = f"Starting — {context}" if context else "Starting..."
        self._print("▶", f"{BOLD}{msg}{RESET}")
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
        self._print("🤖", "Calling LLM...")
        self._emit("llm_call", "Calling LLM...", metadata)

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
        """Traces tool invocation and preserves 100% untruncated arguments in both message and structured data."""
        args_dict = args or {}
        args_str = ""
        if args_dict:
            # Format arguments as key=value pairs without cutting off strings
            pairs = [f"{k}={v}" for k, v in args_dict.items()]
            args_str = f"({', '.join(pairs)})"
        self._print("🔧", f"Calling tool: {BOLD}{tool_name}{RESET}{args_str}")
        payload: dict[str, Any] = {"tool": tool_name, "args": args_dict}
        if call_id:
            payload["call_id"] = call_id
        self._emit("tool_call", f"Calling tool: {tool_name}{args_str}", payload)

    def tool_result(self, tool_name: str, result: str = "", call_id: Optional[str] = None):
        """Traces the full, untruncated return value from a completed tool execution."""
        self._print("✅", f"{tool_name} → {DIM}{result}{RESET}")
        payload: dict[str, Any] = {"tool": tool_name, "result": result}
        if call_id:
            payload["call_id"] = call_id
        self._emit("tool_result", f"{tool_name} → {result}", payload)

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
        """Traces general operational status information (e.g. token usage, blackboard bulletins)."""
        self._print("ℹ️", message)
        self._emit("info", message, data)


# ── String Utility ───────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int = RESULT_TRUNCATE_LEN) -> str:
    """
    Legacy helper retained for import compatibility.
    Returns the full text untouched so no trace steps or tool outputs are cut off.
    """
    return text.strip() if isinstance(text, str) else str(text)


