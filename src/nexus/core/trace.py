"""
trace.py — Lightweight console tracer for the Nexus multi-agent pipeline.

Each agent creates an AgentTracer with a unique color. All output is printed
immediately (flush=True) with a colored prefix so you can visually scan the
scrollback and see which agent did what.

Additionally, all trace events are pushed to a global TraceEventBus so they
can be streamed to the GUI via SSE. Console printing and event bus emission
are independent — disabling one does not affect the other.

No external dependencies — uses ANSI escape codes directly.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

# ── ANSI color codes ─────────────────────────────────────────────────────────

COLORS = {
    "cyan":    "\033[96m",
    "yellow":  "\033[93m",
    "green":   "\033[92m",
    "magenta": "\033[95m",
    "blue":    "\033[94m",
    "red":     "\033[91m",
    "white":   "\033[97m",
}
RESET  = "\033[0m"
DIM    = "\033[2m"
BOLD   = "\033[1m"

RESULT_TRUNCATE_LEN = 200


# ── Trace Event Bus ──────────────────────────────────────────────────────────

class TraceEventBus:
    """
    Thread-safe pub/sub for trace events. Agents emit structured dicts;
    subscribers (e.g., SSE endpoints) receive them via registered callbacks.

    Usage:
        bus = TraceEventBus()
        unsub = bus.subscribe(lambda event: my_queue.put(event))
        # ... agent pipeline runs, events are fanned out ...
        unsub()  # clean up
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: dict[int, Callable[[dict], None]] = {}
        self._next_id = 0

    def subscribe(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        """
        Register a callback to receive all future trace events.
        Returns an unsubscribe function.
        """
        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            self._subscribers[sub_id] = callback

        def unsubscribe():
            with self._lock:
                self._subscribers.pop(sub_id, None)

        return unsubscribe

    def emit(self, event: dict):
        """Fan out an event to all current subscribers."""
        with self._lock:
            callbacks = list(self._subscribers.values())
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                pass  # Never let a bad subscriber crash the pipeline


# Global singleton — all AgentTracers push here, SSE endpoints subscribe here
trace_bus = TraceEventBus()


# ── Agent Tracer ─────────────────────────────────────────────────────────────

class AgentTracer:
    """
    Prints structured trace lines for a single agent AND emits structured
    events to the global trace_bus for GUI streaming.

    Usage:
        tracer = AgentTracer("CareerAgent", color="cyan")
        tracer.agent_start("Analyzing job description")
        tracer.tool_call("search_career_domain", {"keyword": "Python"})
        tracer.tool_result("search_career_domain", "Found 3 files...")
        tracer.llm_call()
        tracer.llm_response("Here is my analysis...")
        tracer.agent_end()
    """

    def __init__(self, agent_name: str, color: str = "white"):
        self.agent_name = agent_name
        self.color = color
        self.color_code = COLORS.get(color, COLORS["white"])

    def _prefix(self) -> str:
        return f"{self.color_code}{BOLD}[{self.agent_name}]{RESET}"

    def _print(self, icon: str, message: str):
        print(f"  {self._prefix()} {icon} {message}", flush=True)

    def _emit(self, event_type: str, message: str, data: Optional[dict] = None):
        """Push a structured event to the global trace bus."""
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

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def agent_start(self, context: str = ""):
        msg = "Starting..."
        if context:
            msg = f"Starting — {context}"
        self._print("▶", f"{BOLD}{msg}{RESET}")
        self._emit("agent_start", msg, {"context": context} if context else None)

    def agent_end(self):
        self._print("■", f"{DIM}Done.{RESET}")
        self._emit("agent_end", "Done.")

    # ── LLM ──────────────────────────────────────────────────────────────────

    def llm_call(self):
        self._print("🤖", f"Calling LLM...")
        self._emit("llm_call", "Calling LLM...")

    def llm_response(self, snippet: str = ""):
        if snippet:
            short = snippet[:120].replace("\n", " ")
            if len(snippet) > 120:
                short += "…"
            self._print("💬", f"{DIM}{short}{RESET}")
            self._emit("llm_response", short)
        else:
            self._print("💬", f"{DIM}(response received){RESET}")
            self._emit("llm_response", "(response received)")

    # ── Tools ────────────────────────────────────────────────────────────────

    def tool_call(self, tool_name: str, args: dict = None):
        args_str = ""
        if args:
            pairs = [f"{k}={_truncate(str(v), 80)}" for k, v in args.items()]
            args_str = f"({', '.join(pairs)})"
        self._print("🔧", f"Calling tool: {BOLD}{tool_name}{RESET}{args_str}")
        self._emit("tool_call", f"Calling tool: {tool_name}{args_str}",
                    {"tool": tool_name, "args": args or {}})

    def tool_result(self, tool_name: str, result: str = ""):
        short = _truncate(result, RESULT_TRUNCATE_LEN)
        self._print("✅", f"{tool_name} → {DIM}{short}{RESET}")
        self._emit("tool_result", f"{tool_name} → {short}",
                    {"tool": tool_name, "result": short})

    def tool_error(self, tool_name: str, error: str):
        self._print("❌", f"{tool_name} error: {error}")
        self._emit("tool_error", f"{tool_name} error: {error}",
                    {"tool": tool_name, "error": error})

    # ── Routing / delegation ─────────────────────────────────────────────────

    def route(self, domain: str, confidence: float = 0.0):
        conf_str = f" (confidence: {confidence:.2f})" if confidence else ""
        self._print("🔀", f"Routing to {BOLD}{domain}{RESET}{conf_str}")
        self._emit("route", f"Routing to {domain}{conf_str}",
                    {"domain": domain, "confidence": confidence})

    def delegate(self, target_agent: str):
        self._print("📤", f"Delegating to {BOLD}{target_agent}{RESET}")
        self._emit("delegate", f"Delegating to {target_agent}",
                    {"target": target_agent})

    def info(self, message: str):
        self._print("ℹ️", message)
        self._emit("info", message)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text and append a marker if it was shortened."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + " [...]"
