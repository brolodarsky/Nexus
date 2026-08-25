"""
graph.py — Career Agent LangGraph Implementation.
Domain-specialized LangGraph agent for career strategy, job analysis, and skill gap detection.

Implements the Deterministic Pre-flight Hydration (DPFH) pattern:
  - Before each LLM call, the agent's system prompt is hydrated with live Vault data
    (domain file listing, My Skills.md, Employer Skill Requirements.md)
  - This is pure Python orchestration — zero LLM cost for context assembly.

Also implements Librarian Escalation & Three-Tier Memory:
  - Subconscious Tier: Live DPFH context + conversation summary injected per turn.
  - Short-Term Recall: Last ~30 raw turns persisted via LangGraph SqliteSaver checkpointer.
  - Deep Recall: Episodic decision logs & archived turns in Markdown logs.
"""
import os
import sys
# Typing primitives:
# - TypedDict: Enforces key types for LangGraph state
# - Annotated: Associates reducer functions (add_messages) with state keys
# - Sequence: Immutable ordered sequence of LangChain BaseMessage objects
# - Optional: Indicates a type can be null/None
from typing import TypedDict, Annotated, Sequence, Optional
# LangGraph reducer: Appends newly emitted messages to existing history instead of overwriting
from langgraph.graph.message import add_messages
from pathlib import Path
# sqlite3: Standard library SQL engine used for local thread checkpointing
import sqlite3

# SqliteSaver: LangGraph checkpointer that persists graph state snapshots to SQLite across turns
from langgraph.checkpoint.sqlite import SqliteSaver

# LangChain message primitives:
# - BaseMessage: Abstract parent class for all chat messages
# - HumanMessage: User inputs or injected payloads
# - SystemMessage: Top-level instructions, procedural rules, and DPFH context
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
# LangGraph orchestration primitives:
# - StateGraph: Directed acyclic/cyclic graph definition
# - START / END: Virtual graph boundary nodes
from langgraph.graph import StateGraph, END, START
# tools_condition: Standard LangGraph conditional edge returning "tools" if last message has tool_calls, else "__end__"
from langgraph.prebuilt import ToolNode, tools_condition
# ChatOpenAI: Model wrapper for OpenAI API
from langchain_openai import ChatOpenAI

from nexus.core.constants import AI_MODEL_MEDIUM, AI_MODEL_LOW, VAULT_PATH, IGNORE_DIRS
from nexus.core.trace import AgentTracer, _truncate, RESULT_TRUNCATE_LEN
from nexus.agents.career.prompts import CAREER_SYSTEM_PROMPT
from nexus.shared_tools.summarizer import summarize_conversation

# ── Tracer ───────────────────────────────────────────────────────────────────
# Cyan console logger and SSE event emitter for the Career Agent
career_tracer = AgentTracer("CareerAgent", color="cyan")


# ── Constants & Declared Dependencies ────────────────────────────────────────

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
# Avoids requiring the LLM to waste a tool call searching for baseline career context
DPFH_FILES = {
    "skill_context": CAREER_DOMAIN_PATH / "My Skills.md",
    "employer_requirements": CAREER_DOMAIN_PATH / "Employer Skill Requirements.md",
}


# ── State Schema ─────────────────────────────────────────────────────────────

# TypedDict defining the state container flowing through the career graph
class CareerAgentState(TypedDict):
    """State that flows through the career agent graph."""
    # add_messages: LangGraph reducer that merges new message lists into the thread
    messages: Annotated[Sequence[BaseMessage], add_messages]
    summary: str # Subconscious memory: Compressed summary of conversation turns pruned by summarizer


# ── DPFH: Deterministic Pre-flight Hydration ─────────────────────────────────

def _list_domain_files(domain_path: Path) -> str:
    """
    DPFH Tier 1: Runs deterministic filesystem traversal over the career domain directory.
    Injects an indented file tree directly into the system prompt at zero LLM token cost.
    """
    if not domain_path.exists():
        return "(career domain directory not found)"

    lines = []
    _build_file_tree(domain_path, lines, prefix="")
    return "\n".join(lines) if lines else "(empty directory)"


def _build_file_tree(directory: Path, lines: list, prefix: str):
    """Recursively builds an indented ASCII file tree, ignoring hidden or artifact folders."""
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
    DPFH Tier 2: Reads a declared dependency file and returns its content.
    Truncates to max_chars to ensure deterministic token budget allocation.
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
    Assembles the full system prompt by resolving all DPFH file injections at query time.
    Ensures the agent always sees the latest disk state without stale cache risks.
    """
    domain_files = _list_domain_files(CAREER_DOMAIN_PATH)
    skill_context = _read_dpfh_file(DPFH_FILES["skill_context"])
    employer_requirements = _read_dpfh_file(DPFH_FILES["employer_requirements"])

    return CAREER_SYSTEM_PROMPT.format(
        domain_files=domain_files,
        skill_context=skill_context,
        employer_requirements=employer_requirements,
    )


# ── LLM Setup & Tool Binding ─────────────────────────────────────────────────

# Career domain tools: local note reading, resume fetch, domain search, librarian escalation, and HITL write proposals
tools = [read_note, get_master_resume, search_career_domain, ask_librarian, propose_write]
tool_node = ToolNode(tools)

# AI_MODEL_MEDIUM (GPT-4o): High-capacity reasoning model for strategic career analysis
# reasoning_effort="none": Explicitly disables extended thinking flags to allow native tool calling
llm = ChatOpenAI(model=AI_MODEL_MEDIUM, temperature=0.0, reasoning_effort="none")
llm_with_tools = llm.bind_tools(tools)


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def call_model(state: CareerAgentState) -> dict:
    """
    Node: Invokes the LLM with message history and ephemeral DPFH system prompt.
    Implements:
      1. Ephemeral Prompt Injection: System prompt is built fresh and prepended ONLY for this LLM call,
         preventing duplicate system prompts from polluting the checkpointer across multi-turn chats.
      2. Dangling Tool Call Sanitization: Cleans interrupted tool calls to avoid OpenAI 400 Bad Request errors.
    """
    messages = state["messages"]
    
    # 1. Assemble ephemeral system prompt with live DPFH data and conversation summary
    system_prompt_content = build_career_system_prompt()
    if state.get("summary"):
        system_prompt_content += f"\n\n--- Conversation Summary ---\n{state['summary']}"
        
    ephemeral_sys_msg = SystemMessage(content=system_prompt_content)

    # 2. Filter out dangling tool calls from previously interrupted graph executions
    # (If an AIMessage requested tool calls but the graph crashed before ToolMessage was saved,
    # OpenAI will reject future calls with a 400 error unless the orphaned request is sanitized)
    cleaned_messages = list(messages)
    for i in range(len(cleaned_messages)):
        msg = cleaned_messages[i]
        if hasattr(msg, "tool_calls") and msg.tool_calls:
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
                # Replace corrupted tool request with a benign AIMessage placeholder
                from langchain_core.messages import AIMessage
                cleaned_messages[i] = AIMessage(content=msg.content or "(tool calls dropped due to interruption)")

    # 3. Prepend ephemeral system message (in-memory only; not written to state dict)
    messages_for_llm = [ephemeral_sys_msg] + cleaned_messages

    career_tracer.llm_call()
    response = llm_with_tools.invoke(messages_for_llm)

    # Trace telemetry: record either tool invocation requests or final conversational response
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            career_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))
    else:
        career_tracer.llm_response(response.content if response.content else "")

    # Return only the new response; add_messages reducer appends it to state["messages"]
    return {"messages": [response]}


def traced_tool_node(state: CareerAgentState) -> dict:
    """
    Node: Runs tool execution and logs structured tool outputs to the console and SSE trace bus.
    """
    result = tool_node.invoke(state)
    # result is a dict {"messages": [ToolMessage, ...]}
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        content = msg.content if hasattr(msg, "content") else str(msg)
        career_tracer.tool_result(tool_name, _truncate(content, RESULT_TRUNCATE_LEN))
    return result


def summarizer_node(state: CareerAgentState) -> dict:
    """
    Node: Context window garbage collection & Three-Tier Memory compression.
    When message history exceeds max_messages (30), older turns are summarized into a compact narrative,
    appended to 'Logs/Conversation Archive.md', and pruned from active state down to keep_messages (10).
    """
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

# Initialize StateGraph parameterized with CareerAgentState schema
workflow = StateGraph(CareerAgentState)

# 1. Register Graph Nodes
workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)
workflow.add_node("summarize", summarizer_node)

# 2. Define Execution Edges & Conditional Tool Loops
workflow.add_edge(START, "agent")                                                            # Graph entry -> call_model
workflow.add_conditional_edges("agent", tools_condition, {"tools": "tools", "__end__": "summarize"}) # ReAct loop or summarize
workflow.add_edge("tools", "agent")                                                          # Tool output loops back to LLM
workflow.add_edge("summarize", END)                                                          # Summarization complete -> END

# 3. Persistent Checkpointer: Co-located SQLite database for thread state persistence
# check_same_thread=False allows FastAPI background threads to access the SQLite connection safely
db_path = Path(__file__).parent / "memory.sqlite"
conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)

# 4. Compile workflow into a stateful, checkpointer-backed runnable graph
career_graph = workflow.compile(checkpointer=memory)

