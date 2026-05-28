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
from agents.career.prompts import CAREER_SYSTEM_PROMPT


# ── Constants ────────────────────────────────────────────────────────────────

CAREER_DOMAIN_PATH = VAULT_PATH / "3. Operations & Wealth" / "3.1. Career Strategy & Revenue"

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

tools = [read_note, search_career_domain, ask_librarian, propose_write]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
llm_with_tools = llm.bind_tools(tools)


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def call_model(state: CareerAgentState) -> dict:
    """Invoke the LLM with the current message history."""
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# ── Graph Assembly ───────────────────────────────────────────────────────────

workflow = StateGraph(CareerAgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

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
    # DPFH: Build the system prompt with live Vault data injected
    system_prompt = build_career_system_prompt()

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
        last_message = final_state["messages"][-1]
        return last_message.content
    except Exception as e:
        return f"❌ Career Agent encountered an error: {e}"


# ── CLI Smoke Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_job = """\
Hi Will,

Congrats on moving on to Round 2 of interviews. We elected for the take
home in Round 2 as the team is traveling.

The project: Build a system with three agents that work together around
the use case that most excites you. Use whichever model and best practices
you would like.

Beyond getting it working, we want to see two things:
  1. How you'd evaluate it
  2. How you'd improve it

There's no single right answer. We're more interested in how you think
about agent quality than in a perfect implementation.

What to send us: A GitHub repo with your code and a short README
explaining your design, your evaluation approach, and what you'd do
differently with more time.

Best,
Bobby Trickett
Social Company
"""

    print("=" * 60)
    print("CAREER AGENT SMOKE TEST")
    print("=" * 60)
    print(f"\nInput: Bobby Trickett's Round 2 email\n")
    print("Running Career Agent with DPFH...\n")

    result = run_career_agent(
        content=test_job,
        summary="Round 2 interview take-home project from Social Company."
    )

    print(result)
