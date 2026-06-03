"""
agent.py — Career Agent.
Domain-specialized LangGraph agent for career strategy, job analysis, and skill gap detection.

Implements the Deterministic Pre-flight Hydration (DPFH) pattern:
  - Before each LLM call, the agent's system prompt is hydrated with live Vault data
    (domain file listing, My Skills.md, Employer Skill Requirements.md)
  - This is pure Python orchestration — zero LLM cost for context assembly.

Also implements Librarian Escalation:
  - The career agent can call ask_librarian() as a tool for cross-domain queries.
"""
import os
import sys
from typing import TypedDict, Annotated, Sequence, Optional
import operator
from pathlib import Path

# ── Path Setup (allows direct execution from any working directory) ──────────
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI

from core.constants import AI_MODEL, VAULT_PATH, IGNORE_DIRS
from core.trace import AgentTracer, _truncate, RESULT_TRUNCATE_LEN
from agents.career.prompts import CAREER_SYSTEM_PROMPT

# ── Tracer ───────────────────────────────────────────────────────────────────
career_tracer = AgentTracer("CareerAgent", color="cyan")


# ── Constants ────────────────────────────────────────────────────────────────

CAREER_DOMAIN_PATH = VAULT_PATH / "3. Operations & Wealth" / "3.1. Career Strategy & Revenue"
RESUMES_PATH = CAREER_DOMAIN_PATH / "3.1.3. Professional Portfolio & Evidence" / "Resumes"
MASTER_RESUME_PATH = RESUMES_PATH / "Resume - Master.md"

# Files to pre-load into the system prompt (DPFH Tier 2: Declared Dependencies)
DPFH_FILES = {
    "skill_context": CAREER_DOMAIN_PATH / "My Skills.md",
    "employer_requirements": CAREER_DOMAIN_PATH / "Employer Skill Requirements.md",
}


# ── State Schema ─────────────────────────────────────────────────────────────

class CareerAgentState(TypedDict):
    """State that flows through the career agent graph."""
    messages: Annotated[Sequence[BaseMessage], operator.add]


# ── DPFH: Deterministic Pre-flight Hydration ─────────────────────────────────

def _list_domain_files(domain_path: Path) -> str:
    """
    DPFH Tier 1: Run os.listdir() on the career domain directory
    and return a formatted file listing. Zero LLM cost.
    """
    if not domain_path.exists():
        return "(career domain directory not found)"

    lines = []
    _build_file_tree(domain_path, lines, prefix="")
    return "\n".join(lines) if lines else "(empty directory)"


def _build_file_tree(directory: Path, lines: list, prefix: str):
    """Recursively build an indented file tree."""
    try:
        entries = sorted(directory.iterdir(), key=lambda e: e.name)
    except PermissionError:
        return

    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORE_DIRS]
    files = [e for e in entries if e.is_file()]

    for d in dirs:
        lines.append(f"{prefix}{d.name}/")
        _build_file_tree(d, lines, prefix=prefix + "  ")

    for f in files:
        lines.append(f"{prefix}{f.name}")


def _read_dpfh_file(file_path: Path, max_chars: int = 4000) -> str:
    """
    DPFH Tier 2: Read a declared dependency file and return its content.
    Truncates to max_chars to stay within token budget.
    """
    if not file_path.exists():
        return f"(file not found: {file_path.name})"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... [truncated at {max_chars} chars]"
        return content
    except Exception as e:
        return f"(error reading {file_path.name}: {e})"


def build_career_system_prompt() -> str:
    """
    Assembles the full system prompt with all DPFH injections.
    Called at query time so the agent always sees the current state.
    """
    domain_files = _list_domain_files(CAREER_DOMAIN_PATH)
    skill_context = _read_dpfh_file(DPFH_FILES["skill_context"])
    employer_requirements = _read_dpfh_file(DPFH_FILES["employer_requirements"])

    return CAREER_SYSTEM_PROMPT.format(
        domain_files=domain_files,
        skill_context=skill_context,
        employer_requirements=employer_requirements,
    )


# ── Career Agent Tools ───────────────────────────────────────────────────────

@tool
def read_note(note_path: str) -> str:
    """Read a specific note from the career domain. Provide the relative path from the Vault root."""
    target = VAULT_PATH / note_path
    if not target.exists():
        # Try adding .md extension
        if not target.suffix:
            target = target.with_suffix(".md")
    if not target.exists():
        return f"File not found: {note_path}"
    try:
        with open(target, "r", encoding="utf-8") as f:
            return f"--- File: {note_path} ---\n\n{f.read()}"
    except Exception as e:
        return f"Error reading {note_path}: {e}"


@tool
def get_master_resume() -> str:
    """Read the master resume (Resume - Master.md) and return its full content.

    Use this when you need to tailor a resume for a specific job description.
    Read the master resume first, then craft a tailored version and propose it
    via propose_write.
    """
    if not MASTER_RESUME_PATH.exists():
        return "(Resume - Master.md not found)"
    try:
        with open(MASTER_RESUME_PATH, "r", encoding="utf-8") as f:
            return f"--- Resume - Master.md ---\n\n{f.read()}"
    except Exception as e:
        return f"Error reading master resume: {e}"


@tool
def search_career_domain(keyword: str) -> str:
    """Search for a keyword within the career domain files only. Returns matching file paths with context snippets."""
    results = []
    keyword_lower = keyword.lower()

    for root, dirs, files in os.walk(CAREER_DOMAIN_PATH):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            if not file.endswith(".md"):
                continue
            filepath = Path(root) / file
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if keyword_lower in content.lower():
                    idx = content.lower().find(keyword_lower)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(keyword) + 50)
                    snippet = content[start:end].replace("\n", " ")
                    rel_path = filepath.relative_to(VAULT_PATH)
                    results.append(f"- {rel_path}: \"...{snippet}...\"")
            except Exception:
                pass

    if not results:
        return f"No results found for '{keyword}' in career domain."

    output = f"Found '{keyword}' in {len(results)} career files:\n"
    for r in results[:15]:
        output += f"{r}\n"
    return output


@tool
def ask_librarian(query: str) -> str:
    """Escalate a cross-domain question to the Librarian Agent.

    Use this when you need information OUTSIDE the career domain — for example,
    checking the user's current learning targets, health constraints, or project status.
    The Librarian has global read access to the entire Vault.

    Args:
        query: A natural language question to ask the Librarian.
    """
    from agents.librarian.agent import ask_librarian as _ask_librarian
    return _ask_librarian(query)


@tool
def propose_write(target_file: str, proposed_content: str, reasoning: str) -> str:
    """Propose a write operation to the HITL (Human-In-The-Loop) queue for review.

    You NEVER write to the Vault directly. All modifications must go through HITL approval.

    Args:
        target_file: Relative path from Vault root to the file to modify.
        proposed_content: The content to write (full or partial, depending on action_type).
        reasoning: A clear explanation of WHY this change should be made.
    """
    from core.hitl_queue import add_transaction

    # Read the original content if the file exists
    original = None
    full_path = VAULT_PATH / target_file
    if full_path.exists():
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                original = f.read()
        except Exception:
            pass

    tx_id = add_transaction(
        agent_name="career_agent",
        action_type="modify" if original else "create",
        target_file=target_file,
        proposed_content=proposed_content,
        original_content=original,
        reasoning=reasoning,
    )

    return f"✅ Write proposed to HITL queue (Transaction #{tx_id}). Awaiting human approval."


# ── LLM Setup ────────────────────────────────────────────────────────────────

tools = [read_note, get_master_resume, search_career_domain, ask_librarian, propose_write]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
llm_with_tools = llm.bind_tools(tools)


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def call_model(state: CareerAgentState) -> dict:
    """Invoke the LLM with the current message history."""
    messages = state["messages"]
    career_tracer.llm_call()
    response = llm_with_tools.invoke(messages)

    # Trace tool calls or text response
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            career_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))
    else:
        career_tracer.llm_response(response.content if response.content else "")

    return {"messages": [response]}


def traced_tool_node(state: CareerAgentState) -> dict:
    """Runs tools and traces their results."""
    result = tool_node.invoke(state)
    # result is a dict with "messages" key containing ToolMessage objects
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        content = msg.content if hasattr(msg, "content") else str(msg)
        career_tracer.tool_result(tool_name, _truncate(content, RESULT_TRUNCATE_LEN))
    return result


# ── Graph Assembly ───────────────────────────────────────────────────────────

workflow = StateGraph(CareerAgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

career_graph = workflow.compile()


# ── Public API ───────────────────────────────────────────────────────────────

def run_career_agent(content: str, summary: str = "") -> str:
    """
    Entry point for the Career Agent.

    Args:
        content: The raw content to analyze (e.g., a job description email).
        summary: Optional short summary from the Router for context.

    Returns:
        The agent's final response string.
    """
    result = run_career_agent_with_trace(content, summary)
    return result["response"]


def run_career_agent_with_trace(content: str, summary: str = "") -> dict:
    """
    Entry point with full trace. Returns response + tool call metadata.

    Args:
        content: The raw content to analyze (e.g., a job description email).
        summary: Optional short summary from the Router for context.

    Returns:
        dict with keys: response (str), tool_calls (list of {name, args} dicts)
    """
    # DPFH: Build the system prompt with live Vault data injected
    career_tracer.agent_start(f"DPFH hydration + query")
    system_prompt = build_career_system_prompt()
    career_tracer.info("System prompt hydrated with live Vault data")

    # Compose the user message with routing context
    user_msg = content
    if summary:
        user_msg = f"[Router Summary: {summary}]\n\n{content}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ]

    try:
        final_state = career_graph.invoke({"messages": messages})

        # Extract tool calls from all messages in the trace
        tool_calls = []
        for msg in final_state["messages"]:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.get("name", ""),
                        "args": {k: v[:200] if isinstance(v, str) and len(v) > 200 else v
                                 for k, v in tc.get("args", {}).items()},
                    })

        last_message = final_state["messages"][-1]
        career_tracer.agent_end()
        return {
            "response": last_message.content,
            "tool_calls": tool_calls,
        }
    except Exception as e:
        career_tracer.info(f"❌ Error: {e}")
        return {
            "response": f"❌ Career Agent encountered an error: {e}",
            "tool_calls": [],
        }