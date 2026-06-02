"""
trace.py — Lightweight console tracer for the Nexus multi-agent pipeline.

Each agent creates an AgentTracer with a unique color. All output is printed
immediately (flush=True) with a colored prefix so you can visually scan the
scrollback and see which agent did what.

No external dependencies — uses ANSI escape codes directly.
"""

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


class AgentTracer:
    """
    Prints structured trace lines for a single agent.

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
        self.color_code = COLORS.get(color, COLORS["white"])

    def _prefix(self) -> str:
        return f"{self.color_code}{BOLD}[{self.agent_name}]{RESET}"

    def _print(self, icon: str, message: str):
        print(f"  {self._prefix()} {icon} {message}", flush=True)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def agent_start(self, context: str = ""):
        msg = "Starting..."
        if context:
            msg = f"Starting — {context}"
        self._print("▶", f"{BOLD}{msg}{RESET}")

    def agent_end(self):
        self._print("■", f"{DIM}Done.{RESET}")

    # ── LLM ──────────────────────────────────────────────────────────────────

    def llm_call(self):
        self._print("🤖", f"Calling LLM...")

    def llm_response(self, snippet: str = ""):
        if snippet:
            short = snippet[:120].replace("\n", " ")
            if len(snippet) > 120:
                short += "…"
            self._print("💬", f"{DIM}{short}{RESET}")
        else:
            self._print("💬", f"{DIM}(response received){RESET}")

    # ── Tools ────────────────────────────────────────────────────────────────

    def tool_call(self, tool_name: str, args: dict = None):
        args_str = ""
        if args:
            pairs = [f"{k}={_truncate(str(v), 80)}" for k, v in args.items()]
            args_str = f"({', '.join(pairs)})"
        self._print("🔧", f"Calling tool: {BOLD}{tool_name}{RESET}{args_str}")

    def tool_result(self, tool_name: str, result: str = ""):
        short = _truncate(result, RESULT_TRUNCATE_LEN)
        self._print("✅", f"{tool_name} → {DIM}{short}{RESET}")

    def tool_error(self, tool_name: str, error: str):
        self._print("❌", f"{tool_name} error: {error}")

    # ── Routing / delegation ─────────────────────────────────────────────────

    def route(self, domain: str, confidence: float = 0.0):
        conf_str = f" (confidence: {confidence:.2f})" if confidence else ""
        self._print("🔀", f"Routing to {BOLD}{domain}{RESET}{conf_str}")

    def delegate(self, target_agent: str):
        self._print("📤", f"Delegating to {BOLD}{target_agent}{RESET}")

    def info(self, message: str):
        self._print("ℹ️", message)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text and append a marker if it was shortened."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + " [...]"
