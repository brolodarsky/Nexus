"""
graph.py — Universal NexusAgent LangGraph Implementation.

Rather than partitioning intelligence across rigid domain packages (router/, career/, librarian/)
or restricting directory access, Nexus runs ONE universal agent design (`NexusAgent`) that:
  1. Injects `Vault/Master Instructions.md` (`inject_root_instructions()`) dynamically before every LLM call
     (pre-hydrated with `{vault_structure}`, `{shared_tools}`, `{current_time}`, and `{user_name}`).
  2. Navigates any Vault section directly (`get_directory_structure`, `read_file`, `search_vault`,
     `get_recent_modifications`) and reads `<Section>/Section Instructions.md` on demand.
  3. Surgically modifies existing Vault notes via `modify_file(file_path, target, replacement, reasoning)`
     or creates new notes via `create_file`, staging all changes to the SQLite HITL queue (`hitl.db`).
  4. Spawns isolated subagents via `spawn_subagent(task_prompt: str)` for parallel or deep subtasks,
     where each subagent inherits `inject_root_instructions()` and the core tool suite.
  5. Enforces a deterministic <= 5 tool-iteration circuit breaker per turn to prevent runaway loops.
"""
# sqlite3: Standard library SQL engine used for local thread checkpointing (`SqliteSaver`)
import sqlite3
from pathlib import Path
# Typing primitives:
# - TypedDict: Enforces key-value types for the LangGraph state dictionary
# - Annotated: Attaches reducer metadata (`add_messages`) to state keys
# - Sequence: Immutable ordered sequence of LangChain `BaseMessage` objects
# - Literal: Constrains conditional edge return strings to an explicit set of node names
from typing import Annotated, Literal, Sequence, TypedDict

# LangChain message primitives:
# - AIMessage: Assistant responses (either conversational text or tool call requests)
# - BaseMessage: Abstract parent class for all chat messages
# - HumanMessage: User inputs or subagent task prompts
# - SystemMessage: Ephemeral top-level instructions injected per LLM invocation
# - ToolMessage: Output returned from executing a `@tool` function
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
# SqliteSaver: LangGraph checkpointer that persists graph state snapshots across turns
from langgraph.checkpoint.sqlite import SqliteSaver
# LangGraph orchestration primitives:
# - StateGraph: Directed graph orchestrating state transitions between Python nodes
# - START / END: Virtual graph entry and terminal nodes
from langgraph.graph import END, START, StateGraph
# add_messages: LangGraph reducer that appends newly returned messages to history instead of overwriting
from langgraph.graph.message import add_messages
# ToolNode: Prebuilt LangGraph node that executes tool calls emitted by an `AIMessage`
from langgraph.prebuilt import ToolNode
# ChatOpenAI: LangChain wrapper for OpenAI chat models
from langchain_openai import ChatOpenAI

from nexus.core.constants import AI_MODEL_LOW, AI_MODEL_MEDIUM, VAULT_PATH
# inject_root_instructions: Dynamically loads and hydrates `Vault/Master Instructions.md` (<1ms disk read)
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.trace import RESULT_TRUNCATE_LEN, AgentTracer, _truncate
from nexus.shared_tools.shared import (
    create_calendar_event,
    create_file,
    fetch_emails,
    get_calendar_schedule,
    get_directory_structure,
    get_recent_modifications,
    get_vault_structure,
    modify_file,
    read_file,
    run_shared_tool_cli,
    search_vault,
    update_calendar_event,
)
from nexus.shared_tools.summarizer import summarize_conversation

# ── Tracer & Circuit Breaker Constants ───────────────────────────────────────

# Cyan console logger and SSE event emitter for the primary NexusAgent
nexus_tracer = AgentTracer("NexusAgent", color="cyan")
# Magenta console logger and SSE event emitter for dynamically spawned subagents
subagent_tracer = AgentTracer("Subagent", color="magenta")

# Hard limit on consecutive tool-calling iterations within a single turn (`Master Instructions.md` Integrity Gate)
MAX_TOOL_ITERATIONS_PER_TURN: int = 5


# ── State Schema ─────────────────────────────────────────────────────────────

# TypedDict defining the state container that flows across all nodes in `NexusAgent`
class NexusAgentState(TypedDict):
    """State that flows through the universal NexusAgent graph."""
    # Annotated[Sequence[BaseMessage], add_messages]: Appends newly returned messages into the existing list
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # Subconscious Tier 1 memory: Compressed narrative summary of older turns pruned by `summarizer_node`
    summary: str


# ── Core Tool Set (Shared by Parent NexusAgent and Subagents) ────────────────

# Most-used deterministic tools bound directly so the agent can navigate, read, surgically edit,
# check recent modifications, inspect emails/calendar, or invoke any other `[CLI]` tool on demand.
CORE_TOOLS = [
    read_file,
    modify_file,
    create_file,
    get_directory_structure,
    get_vault_structure,
    search_vault,
    get_recent_modifications,
    fetch_emails,
    get_calendar_schedule,
    create_calendar_event,
    update_calendar_event,
    run_shared_tool_cli,
]


# ── Dynamic Subagent Spawner (`spawn_subagent`) ──────────────────────────────

@tool
def spawn_subagent(task_prompt: str) -> str:
    """Spawn an isolated subagent to execute a focused research, audit, or synthesis subtask.

    The subagent boots automatically with `inject_root_instructions()` (`Master Instructions.md` +
    `{vault_structure}` + `{shared_tools}`) and has full access to all Vault navigation, reading,
    search, and HITL file tools. You do NOT need to pass tool lists or file arrays—just make
    `task_prompt` self-contained, specific, and crystal clear:
      1. State the exact objective and which Vault section(s) or note(s) to inspect.
      2. Specify any constraints (e.g. read-only vs. staging a surgical edit via `modify_file`).
      3. Specify the exact output format and distilled takeaways to return to you.

    Args:
        task_prompt: A clear, self-contained, actionable prompt instructing the subagent what to do and return.
    """
    subagent_tracer.agent_start(f"Subtask: {task_prompt[:90]}")

    # Build an ephemeral, stateless subagent graph (no checkpointer needed; lives only for this subtask)
    sub_llm = ChatOpenAI(model=AI_MODEL_MEDIUM, temperature=0.0, reasoning_effort="none").bind_tools(CORE_TOOLS)
    sub_tool_node = ToolNode(CORE_TOOLS)

    sub_sys_content = (
        inject_root_instructions()
        + "\n\n# Subagent Execution Mode\n"
        + "You are an isolated subagent spawned by the parent NexusAgent to execute the specific task below. "
        + "Read any relevant `Section Instructions.md` and Vault notes needed, execute the task thoroughly, "
        + "and return a concise, high-signal, grounded synthesis to the parent agent."
    )

    # Run bounded ReAct loop (up to MAX_TOOL_ITERATIONS_PER_TURN tool rounds)
    sub_messages: list[BaseMessage] = [
        SystemMessage(content=sub_sys_content),
        HumanMessage(content=task_prompt),
    ]

    for step in range(MAX_TOOL_ITERATIONS_PER_TURN + 1):
        subagent_tracer.llm_call()
        ai_msg = sub_llm.invoke(sub_messages)
        sub_messages.append(ai_msg)

        if not getattr(ai_msg, "tool_calls", None):
            final_text = ai_msg.content if isinstance(ai_msg.content, str) else str(ai_msg.content)
            subagent_tracer.llm_response(final_text)
            subagent_tracer.agent_end()
            return final_text

        # If the subagent hit the tool-iteration cap, ask for final synthesis without further tool calls
        if step >= MAX_TOOL_ITERATIONS_PER_TURN:
            subagent_tracer.info("Subagent reached max tool iterations; synthesizing current findings...")
            sub_messages.append(
                SystemMessage(
                    content="Tool iteration limit reached. Synthesize your findings from the data gathered so far without calling additional tools."
                )
            )
            final_ai = ChatOpenAI(model=AI_MODEL_MEDIUM, temperature=0.0, reasoning_effort="none").invoke(sub_messages)
            final_text = final_ai.content if isinstance(final_ai.content, str) else str(final_ai.content)
            subagent_tracer.llm_response(final_text)
            subagent_tracer.agent_end()
            return final_text

        for tc in ai_msg.tool_calls:
            subagent_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))

        tool_res = sub_tool_node.invoke({"messages": sub_messages})
        for t_msg in tool_res.get("messages", []):
            t_name = getattr(t_msg, "name", "unknown")
            t_content = t_msg.content if hasattr(t_msg, "content") else str(t_msg)
            subagent_tracer.tool_result(t_name, _truncate(t_content, RESULT_TRUNCATE_LEN))
            sub_messages.append(t_msg)

    subagent_tracer.agent_end()
    return "(Subagent completed without text output)"


# ── Parent Agent Tool & Model Binding ────────────────────────────────────────

# The parent NexusAgent gets all core tools plus `spawn_subagent`
TOOLS = CORE_TOOLS + [spawn_subagent]
tool_node = ToolNode(TOOLS)

# AI_MODEL_MEDIUM: Primary reasoning model for universal Vault navigation, synthesis, and tool orchestration
llm = ChatOpenAI(model=AI_MODEL_MEDIUM, temperature=0.0, reasoning_effort="none")
llm_with_tools = llm.bind_tools(TOOLS)


# ── Helper: Sanitize Dangling Tool Calls & Count Current Turn Iterations ─────

def _sanitize_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Replaces any orphaned AIMessage tool_calls (from prior interrupted runs) so OpenAI does not return HTTP 400."""
    cleaned = list(messages)
    for i, msg in enumerate(cleaned):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            has_all_responses = True
            for tc in msg.tool_calls:
                tc_id = tc.get("id")
                if not any(getattr(m, "tool_call_id", None) == tc_id for m in cleaned[i + 1 :]):
                    has_all_responses = False
                    break
            if not has_all_responses:
                cleaned[i] = AIMessage(content=msg.content or "(tool calls dropped due to prior interruption)")
    return cleaned


def _count_tool_iterations_since_last_human(messages: Sequence[BaseMessage]) -> int:
    """Counts how many AI tool-calling steps have occurred since the latest `HumanMessage` in this turn."""
    count = 0
    # Iterate backward from the end of the message list until we hit the current turn's HumanMessage
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            count += 1
    return count


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def call_model(state: NexusAgentState) -> dict:
    """
    Node: Invokes the LLM with the ephemeral root instructions (`inject_root_instructions()`) and thread history.
    Enforces:
      1. Ephemeral System Prompt Injection (Standard 9): `Master Instructions.md` is read fresh from disk
         on every call (<1ms) and never persisted into the SQLite checkpointer.
      2. Circuit Breaker (`MAX_TOOL_ITERATIONS_PER_TURN` = 5): If the agent has already executed 5 tool
         rounds in the current turn, forces convergence with an explanation rather than looping infinitely.
    """
    raw_messages = state.get("messages", [])
    cleaned_messages = _sanitize_messages(raw_messages)

    # 1. Inject fresh root instructions (`Vault/Master Instructions.md` + `{vault_structure}` + `{shared_tools}`)
    system_prompt_content = inject_root_instructions()
    if state.get("summary"):
        system_prompt_content += f"\n\n--- Conversation Summary (Tier 1 Memory) ---\n{state['summary']}"

    ephemeral_sys_msg = SystemMessage(content=system_prompt_content)
    messages_for_llm: list[BaseMessage] = [ephemeral_sys_msg] + cleaned_messages

    # 2. Check the <= 5 tool-iteration circuit breaker for the current turn
    iterations_used = _count_tool_iterations_since_last_human(cleaned_messages)
    nexus_tracer.llm_call()

    if iterations_used >= MAX_TOOL_ITERATIONS_PER_TURN:
        nexus_tracer.info(
            f"Circuit breaker reached ({iterations_used}/{MAX_TOOL_ITERATIONS_PER_TURN} tool iterations). Converging turn..."
        )
        circuit_breaker_msg = SystemMessage(
            content=(
                f"CIRCUIT BREAKER: You have reached the maximum of {MAX_TOOL_ITERATIONS_PER_TURN} tool iterations "
                f"for this turn. Do NOT call any more tools. Synthesize what you have found so far and ask the user "
                f"how they would like to proceed."
            )
        )
        # Invoke `llm` (without tools bound) to guarantee a text response that closes the turn cleanly
        response = llm.invoke(messages_for_llm + [circuit_breaker_msg])
    else:
        response = llm_with_tools.invoke(messages_for_llm)

    # 3. Emit trace telemetry for either tool invocations or final conversational text
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            nexus_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))
    else:
        nexus_tracer.llm_response(response.content if response.content else "")

    return {"messages": [response]}


def traced_tool_node(state: NexusAgentState) -> dict:
    """Node: Executes requested tool calls and broadcasts structured tool results to console and SSE trace bus."""
    result = tool_node.invoke(state)
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        content = msg.content if hasattr(msg, "content") else str(msg)
        nexus_tracer.tool_result(tool_name, _truncate(content, RESULT_TRUNCATE_LEN))
    return result


def route_after_agent(state: NexusAgentState) -> Literal["tools", "summarize"]:
    """Conditional Edge: Routes to `tools` if the LLM emitted tool calls, otherwise proceeds to `summarize`."""
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
    return "summarize"


def summarizer_node(state: NexusAgentState) -> dict:
    """
    Node: Tier 1 Session Memory compression.
    When message history exceeds 30 messages, summarizes older turns into `state["summary"]`
    and prunes raw messages down to the most recent 10 turns.
    """
    messages = state.get("messages", [])
    if len(messages) <= 30:
        return {}

    fast_llm = ChatOpenAI(model=AI_MODEL_LOW, temperature=0.0)
    archive_path = VAULT_PATH.parent / "logs" / "conversation_archive.md"

    nexus_tracer.info("Compressing long conversation history...")
    updates = summarize_conversation(
        state=state,
        llm=fast_llm,
        archive_path=archive_path,
        max_messages=30,
        keep_messages=10,
    )
    if updates:
        nexus_tracer.info("Conversation history compressed.")
    return updates


# ── Graph Assembly & SQLite Checkpointer ─────────────────────────────────────

workflow = StateGraph(NexusAgentState)

# 1. Register Graph Nodes
workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)
workflow.add_node("summarize", summarizer_node)

# 2. Define Execution Edges
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "summarize": "summarize"})
workflow.add_edge("tools", "agent")
workflow.add_edge("summarize", END)

# 3. Persistent Checkpointer: Co-located SQLite database for multi-turn conversation state
# `check_same_thread=False` allows FastAPI background worker threads to share the SQLite connection safely
db_path = Path(__file__).parent / "memory.sqlite"
conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)

# 4. Compile into executable stateful LangGraph runnable
nexus_graph = workflow.compile(checkpointer=memory)
