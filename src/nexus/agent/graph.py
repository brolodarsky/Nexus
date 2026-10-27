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
  5. Preserves 100% lossless event-bounded conversation history without message-pruning summarization,
     maximizing provider KV prompt-cache hit rates (90–97% cached tokens) across multi-turn sessions.
"""
# sqlite3: Standard library SQL engine used for local thread checkpointing (`SqliteSaver`)
import sqlite3
# threading: Provides thread-safe locking (`Lock`) for assigning unique serial numbers to parallel subagents
import threading
import time
from pathlib import Path
# Typing primitives:
# - TypedDict: Enforces key-value types for the LangGraph state dictionary
# - Annotated: Attaches reducer metadata (`add_messages`) to state keys
# - Sequence: Immutable ordered sequence of LangChain `BaseMessage` objects
# - Literal: Constrains conditional edge return strings to an explicit set of node names
from typing import Annotated, Any, Literal, Sequence, TypedDict

# LangChain message primitives:
# - AIMessage: Assistant responses (either conversational text or tool call requests)
# - BaseMessage: Abstract parent class for all chat messages
# - HumanMessage: User inputs or subagent task prompts
# - SystemMessage: Ephemeral top-level instructions injected per LLM invocation
# - ToolMessage: Output returned from executing a `@tool` function
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
# RunnableConfig: LangChain configuration dictionary carrying per-invocation metadata (`thread_id`, `model_tier`)
from langchain_core.runnables import RunnableConfig
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
# ChatOpenAI: LangChain wrapper for OpenAI and OpenAI-compatible (e.g. Gemini) chat models
from langchain_openai import ChatOpenAI

from nexus.core.config import settings
from nexus.core.constants import (
    AI_MODEL_LOW,
    AI_MODEL_MEDIUM,
    VAULT_PATH,
    ModelTier,
    get_chat_model,
    resolve_model_config,
)
# inject_root_instructions: Dynamically loads and hydrates `Vault/Master Instructions.md` (<1ms disk read)
from nexus.core.blackboard import infer_channel, post_bulletin
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
    post_to_board,
    read_board,
    read_file,
    run_shared_tool_cli,
    search_vault,
    update_calendar_event,
)

# ── Agent Tracers & Subagent Serial Counter ──────────────────────────────────

# Cyan console logger and SSE event emitter for the primary NexusAgent (root node `agent_id="nexus"`)
nexus_tracer = AgentTracer("NexusAgent", color="cyan", agent_id="nexus", parent_id=None)
# Default magenta tracer kept for backward-compatible module imports; individual subagents instantiate their own serial-numbered AgentTracer
subagent_tracer = AgentTracer("Subagent", color="magenta", agent_id="subagent", parent_id="nexus")

# Thread-safe serial counter and color palette so concurrent `spawn_subagent` worker threads get distinct IDs (`subagent-1`, `subagent-2`, ...)
_subagent_counter_lock = threading.Lock()
_subagent_serial_counter = 0
_SUBAGENT_COLORS = ["magenta", "yellow", "green", "blue"]


def reset_subagent_counter() -> None:
    """Resets the subagent serial number counter at the start of a new parent agent run so subagents start cleanly at #1."""
    global _subagent_serial_counter
    with _subagent_counter_lock:
        _subagent_serial_counter = 0


def _next_subagent_tracer(tier: str) -> tuple[int, str, AgentTracer]:
    """Allocates a thread-safe sequential serial number and dedicated `AgentTracer` linked to `parent_id="nexus"`."""
    global _subagent_serial_counter
    with _subagent_counter_lock:
        _subagent_serial_counter += 1
        serial = _subagent_serial_counter
    sub_id = f"subagent-{serial}"
    color = _SUBAGENT_COLORS[(serial - 1) % len(_SUBAGENT_COLORS)]
    tracer = AgentTracer(
        agent_name=f"Subagent #{serial} ({tier})",
        color=color,
        agent_id=sub_id,
        parent_id="nexus",
    )
    return serial, sub_id, tracer


# ── State Schema ─────────────────────────────────────────────────────────────

# TypedDict defining the state container that flows across all nodes in `NexusAgent`
class NexusAgentState(TypedDict):
    """State that flows through the universal NexusAgent graph."""
    # Annotated[Sequence[BaseMessage], add_messages]: Appends newly returned messages into the existing list
    # without mid-conversation pruning so the entire message prefix remains KV-cached by the LLM provider.
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ── Core Tool Set (Shared by Parent NexusAgent and Subagents) ────────────────

# Most-used deterministic tools bound directly so the agent can navigate, read, surgically edit,
# check recent modifications, inspect emails/calendar, post/read bulletins on the Shared Blackboard,
# or invoke any other `[CLI]` tool on demand.
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
    post_to_board,
    read_board,
    run_shared_tool_cli,
]


# ── Helper: Telemetry & Structured Content Block Text Extraction ─────────────

def extract_message_text(msg: BaseMessage | None) -> str:
    """Extracts plain-text markdown from a LangChain BaseMessage across both string and Gemini block-list formats.

    Gemini 3+ thinking models return structured content blocks (`[{'type': 'text', 'text': '...', 'extras': {'signature': '...'}}]`)
    to preserve reasoning signatures in checkpointer state. This helper extracts the clean text string for UI/CLI display
    without mutating the underlying message's signature blocks.
    """
    if msg is None:
        return ""
    if hasattr(msg, "text") and isinstance(msg.text, str):
        return msg.text
    raw_content = getattr(msg, "content", "")
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        parts: list[str] = []
        for block in raw_content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(raw_content)


def _log_token_usage(tracer: AgentTracer, ai_msg: BaseMessage) -> dict[str, int]:
    """Extracts and logs prompt token counts, cached token hits (`cache_read`), and output tokens from an AIMessage."""
    usage = getattr(ai_msg, "usage_metadata", None)
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    in_tok = int(usage.get("input_tokens", 0) or 0)
    out_tok = int(usage.get("output_tokens", 0) or 0)
    details = usage.get("input_token_details") or {}
    cached_tok = int(details.get("cache_read", 0) or 0) if isinstance(details, dict) else 0
    if in_tok or out_tok:
        cache_pct = int((cached_tok / in_tok) * 100) if in_tok > 0 else 0
        tracer.info(
            f"Tokens: {in_tok:,} in ({cached_tok:,} cached, {cache_pct}%) | {out_tok:,} out",
            data={
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cached_tokens": cached_tok,
                "cache_pct": cache_pct,
            },
        )
    return {"input_tokens": in_tok, "output_tokens": out_tok, "cached_tokens": cached_tok}


# ── Dynamic Subagent Spawner (`spawn_subagent`) ──────────────────────────────

@tool
def spawn_subagent(task_prompt: str, model_tier: ModelTier = "low") -> str:
    """Spawn an isolated subagent to execute a focused research, audit, or synthesis subtask.

    PARALLEL SWARMING: Emitting multiple `spawn_subagent` tool calls in a single turn executes all
    subagents concurrently in parallel via the runtime thread pool (`ToolNode`). Use parallel fan-out
    whenever inspecting multiple files, auditing multiple sections, or running independent subtasks so
    raw file contents stay out of your primary context window.

    ARCHITECT-DRAFTER PATTERN (WRITING & EDIT DELEGATION):
    Subagents are not just for reading; they are your execution workforce. When multiple notes need to be created
    or surgically modified, do NOT pull full note bodies into your primary window to execute `modify_file` yourself.
    Instead, decide the architecture and strategy as the Commander, and instruct the subagent exactly what to write:
    provide the target note path, the exact replacement guidelines or markdown blocks, and instruct it to call
    `modify_file` or `create_file` to stage the changes to the HITL queue. The subagent absorbs the raw file contents,
    executes the tool loop, and returns only a concise confirmation receipt (Transaction ID and summary) to your context.

    The subagent boots automatically with `inject_root_instructions()` (`Master Instructions.md` +
    `{vault_structure}` + `{shared_tools}`) and has full access to all Vault navigation, reading,
    search, and HITL file tools. You do NOT need to pass tool lists or file arrays—just make
    `task_prompt` self-contained, specific, and crystal clear:
      1. State the exact objective and which Vault section(s) or note(s) to inspect.
      2. Specify any constraints (e.g. read-only vs. staging a surgical edit via `modify_file`).
      3. Specify the exact output format and distilled takeaways to return to you.

    Args:
        task_prompt: A clear, self-contained, actionable prompt instructing the subagent what to do and return.
        model_tier: Capability/cost tier (`"low"`, `"medium"`, or `"strong"`). Defaults to `"low"` for fast,
                    cost-efficient execution; pass `"medium"` or `"strong"` only for complex synthesis subtasks.
    """
    effective_tier: ModelTier = model_tier if model_tier in ("low", "medium", "strong") else "low"
    serial, sub_id, local_tracer = _next_subagent_tracer(effective_tier)
    t0 = time.time()

    # Emit full, untruncated task_prompt so the Thinking Panel, Graph View, and Run Logs capture 100% of the prompt
    local_tracer.agent_start(
        f"Subtask #{serial} ({effective_tier}): {task_prompt}",
        metadata={
            "serial": serial,
            "subagent_id": sub_id,
            "model_tier": effective_tier,
            "task_prompt": task_prompt,
        },
    )

    # Build an ephemeral, stateless subagent client (no checkpointer needed; lives only for this subtask)
    sub_base_llm = get_chat_model(tier=effective_tier, temperature=0.0)
    sub_llm = sub_base_llm.bind_tools(CORE_TOOLS)
    sub_tool_node = ToolNode(CORE_TOOLS)

    sub_sys_content = (
        inject_root_instructions()
        + "\n\n# Subagent Execution Mode\n"
        + f"You are an isolated Flash subagent (Subagent #{serial}) spawned by the parent NexusAgent (Astra) to execute the specific task below. "
        + "Read any relevant `Section Instructions.md` and Vault notes needed, execute the task thoroughly, "
        + "and return a concise, high-signal, grounded synthesis to the parent agent. "
        + "Your final synthesis will automatically be published to the Shared Agent Blackboard (`blackboard.db`), "
        + "or you may explicitly call `post_to_board(title, content, channel, author)` to post structured bulletins."
    )

    # Run ReAct loop until the subagent finishes tool calls and returns its synthesis
    sub_messages: list[BaseMessage] = [
        SystemMessage(content=sub_sys_content),
        HumanMessage(content=task_prompt),
    ]
    posted_to_board = False
    turn_idx = 0

    while True:
        turn_idx += 1
        local_tracer.llm_call(metadata={"turn": turn_idx, "model_tier": effective_tier})
        ai_msg = sub_llm.invoke(sub_messages)
        _log_token_usage(local_tracer, ai_msg)
        sub_messages.append(ai_msg)

        if not getattr(ai_msg, "tool_calls", None):
            final_text = extract_message_text(ai_msg)
            elapsed_sub = round(time.time() - t0, 2)
            # Automatically publish the subagent's distilled report onto the Shared Blackboard if not already posted
            if final_text.strip() and not posted_to_board:
                auto_channel = infer_channel(task_prompt)
                first_line = task_prompt.strip().splitlines()[0][:120]
                bulletin_id = post_bulletin(
                    author=f"Subagent #{serial} ({effective_tier})",
                    title=first_line,
                    content=final_text,
                    channel=auto_channel,
                )
                local_tracer.info(
                    f"📋 Posted Bulletin #{bulletin_id} to Blackboard [{auto_channel}]",
                    data={"bulletin_id": bulletin_id, "channel": auto_channel, "title": first_line},
                )
            local_tracer.llm_response(final_text, metadata={"turn": turn_idx, "latency_seconds": elapsed_sub})
            local_tracer.agent_end(f"Completed in {elapsed_sub:.1f}s")
            return final_text

        # If the LLM emitted intermediate thought/explanation alongside tool calls, trace that text too
        intermediate_text = extract_message_text(ai_msg).strip()
        if intermediate_text:
            local_tracer.llm_response(intermediate_text, metadata={"turn": turn_idx, "intermediate": True})

        for tc in ai_msg.tool_calls:
            tc_name = tc.get("name", "unknown")
            tc_id = tc.get("id")
            if tc_name == "post_to_board":
                posted_to_board = True
            local_tracer.tool_call(tc_name, tc.get("args", {}), call_id=tc_id)

        tool_res = sub_tool_node.invoke({"messages": sub_messages})
        for t_msg in tool_res.get("messages", []):
            t_name = getattr(t_msg, "name", "unknown")
            t_call_id = getattr(t_msg, "tool_call_id", None)
            t_content = extract_message_text(t_msg)
            local_tracer.tool_result(t_name, t_content, call_id=t_call_id)
            sub_messages.append(t_msg)


# ── Parent Agent Tool & Model Binding ────────────────────────────────────────

# The parent NexusAgent gets all core tools plus `spawn_subagent`
TOOLS = CORE_TOOLS + [spawn_subagent]
tool_node = ToolNode(TOOLS)

# Primary reasoning model resolved via `get_chat_model` (uses Gemini 3.8 Flash when GEMINI_API_KEY is set, else OpenAI tier)
_primary_tier: ModelTier = (
    settings.nexus_primary_tier if settings.nexus_primary_tier in ("low", "medium", "strong") else "medium"
)
llm = get_chat_model(tier=_primary_tier, temperature=0.0)
llm_with_tools = llm.bind_tools(TOOLS)


# ── Helper: Sanitize Dangling Tool Calls & Mid-Turn Pruned History ───────────

def _sanitize_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Ensures message history obeys strict `HumanMessage -> AIMessage(tool_calls) -> ToolMessage` ordering.

    Self-heals two edge cases that otherwise cause HTTP 400 `INVALID_ARGUMENT` on Gemini / OpenAI:
      1. Mid-turn history pruning: If an older summarizer pass sliced history inside a tool loop, strips leading
         `ToolMessage` and `AIMessage(tool_calls)` fragments that lack a preceding `HumanMessage`, and prepends a
         lightweight `HumanMessage` anchor if the history begins with a standalone conversational `AIMessage`.
      2. Interrupted tool calls: Replaces any `AIMessage(tool_calls)` missing its `ToolMessage` responses with a
         plain-text `AIMessage` and drops any partial orphaned `ToolMessage`s.
    """
    cleaned = list(messages)

    # 1. Strip leading mid-turn tool fragments (`ToolMessage` or `AIMessage` with tool_calls) before the first `HumanMessage`
    while cleaned and (
        isinstance(cleaned[0], ToolMessage)
        or (isinstance(cleaned[0], AIMessage) and bool(getattr(cleaned[0], "tool_calls", None)))
    ):
        cleaned.pop(0)

    # If the slice begins with a final conversational `AIMessage` from the prior turn, anchor it with a `HumanMessage`
    if cleaned and isinstance(cleaned[0], AIMessage):
        cleaned.insert(0, HumanMessage(content="[Prior turn context summarized in SystemMessage]"))

    # 2. Sanitize any interrupted `AIMessage(tool_calls)` missing matching `ToolMessage` responses
    dropped_tc_ids: set[str] = set()
    for i, msg in enumerate(cleaned):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            has_all_responses = True
            for tc in msg.tool_calls:
                tc_id = tc.get("id")
                if not any(getattr(m, "tool_call_id", None) == tc_id for m in cleaned[i + 1 :]):
                    has_all_responses = False
                    break
            if not has_all_responses:
                for tc in msg.tool_calls:
                    if tc.get("id"):
                        dropped_tc_ids.add(tc["id"])
                cleaned[i] = AIMessage(content=extract_message_text(msg) or "(tool calls dropped due to prior interruption)")

    if dropped_tc_ids:
        cleaned = [
            m for m in cleaned
            if not (isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None) in dropped_tc_ids)
        ]

    return cleaned


# ── Graph Nodes ──────────────────────────────────────────────────────────────

# `config: RunnableConfig | None` carries per-turn runtime options (`thread_id`, `model_tier`) injected by `nexus_graph.invoke(..., config=config)`.
def call_model(state: NexusAgentState, config: RunnableConfig | None = None) -> dict:
    """
    Node: Invokes the LLM with the ephemeral root instructions (`inject_root_instructions()`) and thread history.
    Enforces Ephemeral System Prompt Injection (Standard 9): `Master Instructions.md` is read fresh from disk
    on every call (<1ms) and never persisted into the SQLite checkpointer.
    """
    raw_messages = state.get("messages", [])
    cleaned_messages = _sanitize_messages(raw_messages)

    # 1. Inject fresh root instructions (`Vault/Master Instructions.md` + `{vault_structure}` + `{shared_tools}`)
    # Never mutate `SystemMessage` with rolling summaries so Message #0 and the entire conversation prefix remain
    # byte-identical for automatic provider KV prompt caching across turns.
    system_prompt_content = inject_root_instructions()

    ephemeral_sys_msg = SystemMessage(content=system_prompt_content)
    messages_for_llm: list[BaseMessage] = [ephemeral_sys_msg] + cleaned_messages

    # 2. Extract optional per-turn `model_tier` override from LangGraph `RunnableConfig` (`configurable.model_tier`).
    # Keeping `model_tier` in `RunnableConfig` rather than `messages` preserves 100% KV prompt-cache prefix stability.
    configurable = (config or {}).get("configurable") or {}
    requested_tier = configurable.get("model_tier")
    resolved_model = resolve_model_config(requested_tier)
    effective_tier = resolved_model["tier"]
    active_model_name = resolved_model["model_name"]

    # Resolve `get_chat_model(tier=requested_tier)` dynamically on each turn so UI model switches and `.env` edits apply immediately
    nexus_tracer.llm_call(metadata={"model_tier": effective_tier, "model_name": active_model_name})
    active_llm = get_chat_model(tier=requested_tier, temperature=0.0)
    try:
        response = active_llm.bind_tools(TOOLS).invoke(messages_for_llm)
    except Exception as e:
        err_msg = str(e)
        # Check if the failure is a deadline / timeout error from the provider gateway (e.g. 504 DEADLINE_EXCEEDED)
        # Occurs when heavy reasoning models (`gemini-4-argon`) exceed HTTP deadlines on long conversation histories.
        is_deadline_or_timeout = any(
            token in err_msg.lower() or token in type(e).__name__.lower()
            for token in ("504", "deadline_exceeded", "timeout", "timed out")
        )
        # Resilient Tier Fallback: If the active strong/medium model hits a deadline timeout, fallback to the high-throughput
        # low-latency tier (`gemini-3.8-flash` / `low`) to preserve the user's conversation session without crashing.
        if is_deadline_or_timeout and effective_tier != "low":
            nexus_tracer.info(
                f"⚠️ Primary model tier ({effective_tier} · {active_model_name}) exceeded deadline (504 DEADLINE_EXCEEDED). "
                "Gracefully falling back to low-latency tier (Flash) to complete the turn..."
            )
            fallback_llm = get_chat_model(tier="low", temperature=0.0)
            response = fallback_llm.bind_tools(TOOLS).invoke(messages_for_llm)
        else:
            raise e

    # Log input tokens, cached prompt tokens (`cache_read`), and output tokens to console and SSE trace bus
    _log_token_usage(nexus_tracer, response)

    # 3. Emit trace telemetry for either tool invocations or final conversational text
    if hasattr(response, "tool_calls") and response.tool_calls:
        # If the LLM emitted reasoning/text alongside its tool calls, emit that text first so no thought is hidden
        intermediate_text = extract_message_text(response).strip()
        if intermediate_text:
            nexus_tracer.llm_response(intermediate_text, metadata={"intermediate": True})
        for tc in response.tool_calls:
            nexus_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}), call_id=tc.get("id"))
    else:
        nexus_tracer.llm_response(extract_message_text(response))

    return {"messages": [response]}


def traced_tool_node(state: NexusAgentState) -> dict:
    """Node: Executes requested tool calls and broadcasts full, untruncated tool results to console and SSE trace bus."""
    result = tool_node.invoke(state)
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        call_id = getattr(msg, "tool_call_id", None)
        content = extract_message_text(msg)
        nexus_tracer.tool_result(tool_name, content, call_id=call_id)
    return result


def route_after_agent(state: NexusAgentState) -> Literal["tools", "__end__"]:
    """Conditional Edge: Routes to `tools` if the LLM emitted tool calls, otherwise terminates the turn (`END`)."""
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
    return END


# ── Graph Assembly & SQLite Checkpointer ─────────────────────────────────────

workflow = StateGraph(NexusAgentState)

# 1. Register Graph Nodes
workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)

# 2. Define Execution Edges
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")

# 3. Persistent Checkpointer: Co-located SQLite database for multi-turn conversation state
# `check_same_thread=False` allows FastAPI background worker threads to share the SQLite connection safely
db_path = Path(__file__).parent / "memory.sqlite"
conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)

# 4. Compile into executable stateful LangGraph runnable
nexus_graph = workflow.compile(checkpointer=memory)
