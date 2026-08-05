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
from langgraph.graph.message import add_messages
from pathlib import Path
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver


from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI

from nexus.core.constants import AI_MODEL_MEDIUM, AI_MODEL_LOW, VAULT_PATH, IGNORE_DIRS
from nexus.core.trace import AgentTracer, _truncate, RESULT_TRUNCATE_LEN
from nexus.agents.career.prompts import CAREER_SYSTEM_PROMPT
from nexus.shared_tools.summarizer import summarize_conversation

# ── Tracer ───────────────────────────────────────────────────────────────────
career_tracer = AgentTracer("CareerAgent", color="cyan")


# ── Constants ────────────────────────────────────────────────────────────────

from nexus.agents.career.tools import (
    CAREER_DOMAIN_PATH,
    MASTER_RESUME_PATH,
    read_note,
    get_master_resume,
    search_career_domain,
    ask_librarian,
    propose_write
)

# Files to pre-load into the system prompt (DPFH Tier 2: Declared Dependencies)
DPFH_FILES = {
    "skill_context": CAREER_DOMAIN_PATH / "My Skills.md",
    "employer_requirements": CAREER_DOMAIN_PATH / "Employer Skill Requirements.md",
}


# ── State Schema ─────────────────────────────────────────────────────────────

class CareerAgentState(TypedDict):
    """State that flows through the career agent graph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    summary: str


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


# ── LLM Setup ────────────────────────────────────────────────────────────────

tools = [read_note, get_master_resume, search_career_domain, ask_librarian, propose_write]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model=AI_MODEL_MEDIUM, temperature=0.0, reasoning_effort="none")  # <-- Force reasoning off to allow tools
llm_with_tools = llm.bind_tools(tools)


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def call_model(state: CareerAgentState) -> dict:
    """Invoke the LLM with the current message history."""
    messages = state["messages"]
    
    # Build ephemeral system prompt
    system_prompt_content = build_career_system_prompt()
    if state.get("summary"):
        system_prompt_content += f"\n\n--- Conversation Summary ---\n{state['summary']}"
        
    ephemeral_sys_msg = SystemMessage(content=system_prompt_content)

    
    # Filter out dangling tool calls from interrupted graph executions
    # to prevent OpenAI "Error code: 400" (missing tool response).
    cleaned_messages = list(messages)
    for i in range(len(cleaned_messages)):
        msg = cleaned_messages[i]
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            # Look ahead for matching ToolMessage
            has_responses = True
            for tc in msg.tool_calls:
                tc_id = tc["id"]
                found = False
                for j in range(i + 1, len(cleaned_messages)):
                    next_msg = cleaned_messages[j]
                    if getattr(next_msg, "tool_call_id", None) == tc_id:
                        found = True
                        break
                if not found:
                    has_responses = False
                    break
            
            if not has_responses:
                # Strip the tool_calls since they were interrupted
                from langchain_core.messages import AIMessage
                cleaned_messages[i] = AIMessage(content=msg.content or "(tool calls dropped due to interruption)")

    # Prepend the ephemeral system prompt for this LLM invocation only
    messages_for_llm = [ephemeral_sys_msg] + cleaned_messages

    career_tracer.llm_call()
    response = llm_with_tools.invoke(messages_for_llm)

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


def summarizer_node(state: CareerAgentState) -> dict:
    """Compresses conversation history if it exceeds the limit."""
    # We use the fast model for summarization
    fast_llm = ChatOpenAI(model=AI_MODEL_LOW, temperature=0.0)
    archive_path = CAREER_DOMAIN_PATH / "Logs" / "Conversation Archive.md"
    
    career_tracer.info("Checking if summarization is needed...")
    updates = summarize_conversation(
        state=state,
        llm=fast_llm,
        archive_path=archive_path,
        max_messages=30,
        keep_messages=10
    )
    if updates:
        career_tracer.info("Conversation compressed and archived.")
    return updates


# ── Graph Assembly ───────────────────────────────────────────────────────────

workflow = StateGraph(CareerAgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)
workflow.add_node("summarize", summarizer_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition, {"tools": "tools", "__end__": "summarize"})
workflow.add_edge("tools", "agent")
workflow.add_edge("summarize", END)

# Set up co-located SQLite memory for the agent's checkpointer
db_path = Path(__file__).parent / "memory.sqlite"
conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)

career_graph = workflow.compile(checkpointer=memory)

