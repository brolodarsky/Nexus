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
from datetime import datetime, timezone
# Callable: Type hint for functions passed as arguments (callbacks)
# Optional: Type hint indicating a value can be of a specific type or None
from typing import Callable, Optional

# ── ANSI Escape Codes ────────────────────────────────────────────────────────
# ANSI sequences (ESC [ <code > m) instruct terminal emulators to change text color and style
# \033 is the octal representation of the ASCII Escape character (27)
COLORS = {
    "cyan":    "\033[96m", # High-intensity cyan (used by CareerAgent)
    "yellow":  "\033[93m", # High-intensity yellow (used by Content Router)
    "green":   "\033[92m", # High-intensity green (used by Librarian)
    "magenta": "\033[95m", # High-intensity magenta (used by Medical / Forge)
    "blue":    "\033[94m", # High-intensity blue
    "red":     "\033[91m", # High-intensity red (errors / warnings)
    "white":   "\033[97m", # High-intensity white (general info)
}
RESET  = "\033[0m"  # Resets text formatting back to default terminal style
DIM    = "\033[2m"  # Reduces text brightness (useful for secondary details/results)
BOLD   = "\033[1m"  # Increases font weight for agent tags and tool names

RESULT_TRUNCATE_LEN = 200 # Max characters displayed in terminal for tool outputs to prevent console spam


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
    Dual-output telemetry logger for an individual agent.
    1. Terminal Output: Formats and prints ANSI-colored logs to stdout.
    2. SSE Event Stream: Emits structured event dictionaries to the global trace_bus.
    """

    def __init__(self, agent_name: str, color: str = "white"):
        self.agent_name = agent_name
        self.color = color
        # Resolves color code string; defaults to white if color is not in lookup table
        self.color_code = COLORS.get(color, COLORS["white"])

    def _prefix(self) -> str:
        """Constructs the stylized terminal prefix (e.g. '[CareerAgent]')."""
        return f"{self.color_code}{BOLD}[{self.agent_name}]{RESET}"

    def _print(self, icon: str, message: str):
        """Prints formatted message immediately to stdout with flush=True to avoid buffering delays."""
        print(f"  {self._prefix()} {icon} {message}", flush=True)

    def _emit(self, event_type: str, message: str, data: Optional[dict] = None):
        """Builds a standardized trace event payload and publishes it to trace_bus."""
        event = {
            "type": event_type,
            "agent": self.agent_name,
            "color": self.color,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if data:
            event["data"] = data
        trace_bus.emit(event)

    # ── Lifecycle Methods ────────────────────────────────────────────────────

    def agent_start(self, context: str = ""):
        """Signals that an agent has begun its execution loop."""
        msg = f"Starting — {context}" if context else "Starting..."
        self._print("▶", f"{BOLD}{msg}{RESET}")
        self._emit("agent_start", msg, {"context": context} if context else None)

    def agent_end(self):
        """Signals that an agent has completed its execution loop."""
        self._print("■", f"{DIM}Done.{RESET}")
        self._emit("agent_end", "Done.")

    # ── LLM Telemetry ────────────────────────────────────────────────────────

    def llm_call(self):
        """Traces the dispatch of a prompt payload to the language model."""
        self._print("🤖", f"Calling LLM...")
        self._emit("llm_call", "Calling LLM...")

    def llm_response(self, snippet: str = ""):
        """Traces the receipt of text or tool calls back from the language model."""
        if snippet:
            # Flatten multi-line responses into a compact single line for console readability
            short = snippet[:120].replace("\n", " ")
            if len(snippet) > 120:
                short += "…"
            self._print("💬", f"{DIM}{short}{RESET}")
            self._emit("llm_response", short)
        else:
            self._print("💬", f"{DIM}(response received){RESET}")
            self._emit("llm_response", "(response received)")

    # ── Tool Telemetry ───────────────────────────────────────────────────────

    def tool_call(self, tool_name: str, args: dict = None):
        """Traces tool invocation and formats arguments into a compact signature string."""
        args_str = ""
        if args:
            # Format arguments as key=value pairs, truncating long strings
            pairs = [f"{k}={_truncate(str(v), 80)}" for k, v in args.items()]
            args_str = f"({', '.join(pairs)})"
        self._print("🔧", f"Calling tool: {BOLD}{tool_name}{RESET}{args_str}")
        self._emit("tool_call", f"Calling tool: {tool_name}{args_str}",
                    {"tool": tool_name, "args": args or {}})

    def tool_result(self, tool_name: str, result: str = ""):
        """Traces the return value from a completed tool execution."""
        short = _truncate(result, RESULT_TRUNCATE_LEN)
        self._print("✅", f"{tool_name} → {DIM}{short}{RESET}")
        self._emit("tool_result", f"{tool_name} → {short}",
                    {"tool": tool_name, "result": short})

    def tool_error(self, tool_name: str, error: str):
        """Traces a tool exception or failure."""
        self._print("❌", f"{tool_name} error: {error}")
        self._emit("tool_error", f"{tool_name} error: {error}",
                    {"tool": tool_name, "error": error})

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

    def info(self, message: str):
        """Traces general operational status information."""
        self._print("ℹ️", message)
        self._emit("info", message)


# ── String Utility ───────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int) -> str:
    """
    Sanitizes newlines and truncates text exceeding max_len characters.
    Appends ' [...]' indicator to clarify that output was shortened.
    """
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + " [...]"

