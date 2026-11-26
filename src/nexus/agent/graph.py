"""
graph.py — Universal NexusAgent LangGraph Implementation.

Rather than partitioning intelligence across rigid domain packages (router/, career/, librarian/)
or restricting directory access, Nexus runs ONE universal agent design (`NexusAgent`) that:
  1. Injects `Vault/Master Instructions.md` (`inject_root_instructions()`) dynamically before every LLM call
     (pre-hydrated with `{vault_structure}`, `{shared_tools}`, and `{user_name}`).
  2. Navigates any Vault section directly (`get_directory_structure`, `read_file`, `search_vault`,
     `get_recent_modifications`) and reads `<Section>/Section Instructions.md` on demand.
  3. Surgically modifies existing Vault notes via `modify_file(file_path, target, replacement, reasoning)`,
     creates new notes via `create_file`, moves notes via `move_file`, and deletes notes via `delete_file`,
     staging all changes to the SQLite HITL queue (`hitl.db`).
  4. Spawns isolated subagents via `spawn_subagent(task_prompt: str)` (in `nexus.agent.subagent`) for
     parallel or deep subtasks, where each subagent inherits `inject_root_instructions()` and `CORE_TOOLS`.
  5. Preserves 100% lossless event-bounded conversation history without message-pruning summarization,
     sustaining high provider KV prompt-cache hit rates (83.5% across 748 measured runs; 90–95% on static prefixes).
"""
# Typing primitives:
# - TypedDict: Enforces key-value types for the LangGraph state dictionary
# - Annotated: Attaches reducer metadata (`add_messages`) to state keys
# - Sequence: Immutable ordered sequence of LangChain `BaseMessage` objects
# - Literal: Constrains conditional edge return strings to an explicit set of node names
from typing import Annotated, Literal, Sequence, TypedDict

# BaseMessage: Abstract parent class for all LangChain chat messages
from langchain_core.messages import BaseMessage
# RunnableConfig: LangChain configuration dictionary carrying per-invocation metadata (`thread_id`, `model_tier`)
from langchain_core.runnables import RunnableConfig
# LangGraph orchestration primitives:
# - StateGraph: Directed graph orchestrating state transitions between Python nodes
# - START / END: Virtual graph entry and terminal nodes
from langgraph.graph import END, START, StateGraph
# add_messages: LangGraph reducer that appends newly returned messages to history instead of overwriting
from langgraph.graph.message import add_messages
# ToolNode: Prebuilt LangGraph node that executes tool calls emitted by an `AIMessage`
from langgraph.prebuilt import ToolNode

from nexus.agent.runtime import (
    CORE_TOOLS,
    _build_system_message,
    _invoke_llm_with_resilience,
    _invoke_tool_node_resilient,
    _log_token_usage,
    is_thread_cancelled,
    nexus_tracer,
    set_active_turn_provider,
)
from nexus.agent.sanitization import (
    _sanitize_messages,
    _sanitize_messages_for_provider,
    extract_message_text,
    extract_message_thinking,
)
from nexus.agent.subagent import spawn_subagent
from nexus.core.config import settings
from nexus.core.constants import get_chat_model, resolve_model_config
from nexus.core.context_telemetry import build_llm_call_manifest
# inject_root_instructions: Dynamically loads and hydrates `Vault/Master Instructions.md` (<1ms disk read)
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import (
    get_hitl_execution_context,
    set_hitl_execution_context,
)
from nexus.core.trace import get_trace_run_id


# ── State Schema ─────────────────────────────────────────────────────────────

# TypedDict defining the state container that flows across all nodes in `NexusAgent`
class NexusAgentState(TypedDict):
    """State that flows through the universal NexusAgent graph."""
    # Annotated[Sequence[BaseMessage], add_messages]: Appends newly returned messages into the existing list
    # without mid-conversation pruning so the entire message prefix remains KV-cached by the LLM provider.
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ── Parent Agent Tool Binding ────────────────────────────────────────────────

# The parent NexusAgent gets all core tools plus `spawn_subagent`
TOOLS = CORE_TOOLS + [spawn_subagent]
# handle_tool_errors=True catches unhandled tool exceptions across all parent tools (including spawn_subagent)
# and returns an error ToolMessage to the model so the agent can gracefully recover, retry, or report to the user.
tool_node = ToolNode(TOOLS, handle_tool_errors=True)


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

    # 1. Extract optional per-turn `model_tier` override from LangGraph `RunnableConfig` (`configurable.model_tier`).
    # Keeping `model_tier` in `RunnableConfig` rather than `messages` preserves 100% KV prompt-cache prefix stability.
    configurable = (config or {}).get("configurable") or {}
    active_thread_id = str(configurable.get("thread_id") or "nexus_primary")
    active_convo_id = str(configurable.get("conversation_id") or active_thread_id)

    # Pre-inference cancellation guard: abort immediately if user pressed Stop & Revert
    if is_thread_cancelled(active_thread_id) or is_thread_cancelled(active_convo_id):
        raise InterruptedError(f"Turn execution for thread '{active_thread_id}' stopped by user.")

    requested_tier = configurable.get("model_tier")
    resolved_model = resolve_model_config(requested_tier)
    effective_tier = resolved_model["tier"]
    active_model_name = resolved_model["model_name"]
    active_provider = resolved_model["provider"]

    # 2. Inject fresh static root instructions (`Vault/Master Instructions.md` + `{vault_structure}` + `{shared_tools}`)
    # Never mutate `SystemMessage` with rolling summaries or timestamps so Message #0 and the entire conversation prefix
    # remain byte-identical for automatic provider KV prompt caching across turns (with explicit cache_control on Anthropic).
    system_prompt_content = inject_root_instructions()
    ephemeral_sys_msg = _build_system_message(system_prompt_content, active_provider)
    # Ephemerally strip foreign-provider thinking/signature blocks (e.g., Anthropic -> Gemini) while keeping
    # same-provider signatures and persisted `SqliteSaver` checkpoints completely untouched.
    provider_safe_messages = _sanitize_messages_for_provider(cleaned_messages, active_provider)
    messages_for_llm: list[BaseMessage] = [ephemeral_sys_msg] + provider_safe_messages

    # Record active provider scoped to active_convo_id so parallel subagents match their exact turn's provider family
    set_active_turn_provider(active_provider, thread_id=active_convo_id)

    # Resolve `get_chat_model(tier=requested_tier)` dynamically on each turn so UI model switches and `.env` edits apply immediately
    call_manifest, call_summary = build_llm_call_manifest(
        messages=messages_for_llm,
        tools=TOOLS,
        run_id=get_trace_run_id(),
    )
    nexus_tracer.llm_call(
        metadata={
            "model_tier": effective_tier,
            "model_name": active_model_name,
            "context_manifest": call_manifest,
            "context_summary": call_summary,
        }
    )
    active_llm = get_chat_model(tier=requested_tier, temperature=0.0)
    try:
        response = _invoke_llm_with_resilience(
            llm=active_llm.bind_tools(TOOLS),
            messages=messages_for_llm,
            tracer=nexus_tracer,
            thread_ids=[active_thread_id, active_convo_id],
            model_name=active_model_name,
            tier=effective_tier,
            max_retries=settings.ai_max_retries,
        )
    except Exception as e:
        err_msg = str(e)
        # Check if the failure is a deadline / timeout error from the provider gateway (e.g. 504 DEADLINE_EXCEEDED)
        # Occurs when heavy reasoning models (`gemini-4-argon`, `claude-opus-5-5`) exceed HTTP deadlines on long conversation histories.
        is_deadline_or_timeout = any(
            token in err_msg.lower() or token in type(e).__name__.lower()
            for token in ("504", "deadline_exceeded", "timeout", "timed out")
        )
        # Resilient Tier Fallback: If the active strong/medium model hits a deadline timeout, fallback to the high-throughput
        # low-latency tier (`gemini-4-hydrogen` / `claude-haiku-5-5` / `low`) to preserve the user's conversation session without crashing.
        if is_deadline_or_timeout and effective_tier != "low":
            fallback_tier_arg = "anthropic:low" if active_provider == "anthropic" else "low"
            fallback_resolved = resolve_model_config(fallback_tier_arg)
            nexus_tracer.info(
                f"⚠️ Primary model tier ({effective_tier} · {active_model_name}) exceeded deadline (504 DEADLINE_EXCEEDED). "
                f"Gracefully falling back to low-latency tier ({fallback_resolved['model_name']}) to complete the turn..."
            )
            fallback_provider = fallback_resolved["provider"]
            fallback_sys_msg = _build_system_message(system_prompt_content, fallback_provider)
            fallback_messages: list[BaseMessage] = [fallback_sys_msg] + _sanitize_messages_for_provider(
                cleaned_messages,
                fallback_provider,
            )
            fallback_llm = get_chat_model(tier=fallback_tier_arg, temperature=0.0)
            response = _invoke_llm_with_resilience(
                llm=fallback_llm.bind_tools(TOOLS),
                messages=fallback_messages,
                tracer=nexus_tracer,
                thread_ids=[active_thread_id, active_convo_id],
                model_name=fallback_resolved["model_name"],
                tier="low",
                max_retries=settings.ai_max_retries,
            )
            active_model_name = fallback_resolved["model_name"]
            effective_tier = "low"
        else:
            raise e

    # Post-inference cancellation guard: prevent running subsequent tools if user stopped during LLM generation
    if is_thread_cancelled(active_thread_id) or is_thread_cancelled(active_convo_id):
        raise InterruptedError(f"Turn execution for thread '{active_thread_id}' stopped by user.")

    # Log input tokens, cached prompt tokens (`cache_read`), output tokens, and estimated cost to console and SSE trace bus
    _log_token_usage(nexus_tracer, response, model_name=active_model_name, tier=effective_tier)

    # Emit visible model thinking/reasoning summary (when returned by Gemini/Anthropic) before tool calls or final text
    thinking_text = extract_message_thinking(response)
    if thinking_text:
        nexus_tracer.llm_thinking(
            thinking_text,
            metadata={"model_tier": effective_tier, "model_name": active_model_name},
        )

    # Refresh HITL execution provenance so any tool calls executed next by `traced_tool_node` record exact session/agent metadata
    set_hitl_execution_context(
        conversation_id=active_convo_id,
        thread_id=active_thread_id,
        agent_id="nexus",
        agent_role=f"Commander ({effective_tier})",
    )

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
    # Pre-tool cancellation check
    ctx = get_hitl_execution_context()
    thread_id = ctx.get("thread_id") or ctx.get("conversation_id")
    if is_thread_cancelled(thread_id):
        raise InterruptedError(f"Tool execution for thread '{thread_id}' stopped by user.")

    # Use subagent timeout budget if this batch includes `spawn_subagent`, otherwise use per-tool timeout
    messages = state.get("messages", [])
    last_ai = messages[-1] if messages else None
    pending_calls = getattr(last_ai, "tool_calls", None) or []
    has_subagent = any(tc.get("name") == "spawn_subagent" for tc in pending_calls)
    batch_timeout = (
        float(getattr(settings, "nexus_subagent_timeout", 900) or 900) + 30.0
        if has_subagent
        else float(getattr(settings, "nexus_tool_timeout", 120) or 120)
    )

    result = _invoke_tool_node_resilient(tool_node, state, timeout_seconds=batch_timeout)
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        call_id = getattr(msg, "tool_call_id", None)
        content = extract_message_text(msg)
        if getattr(msg, "status", None) == "error":
            nexus_tracer.tool_error(tool_name, content, call_id=call_id)
        else:
            nexus_tracer.tool_result(tool_name, content, call_id=call_id)

    # Post-tool cancellation check
    if is_thread_cancelled(thread_id):
        raise InterruptedError(f"Tool execution for thread '{thread_id}' stopped by user.")

    return result


def route_after_agent(state: NexusAgentState) -> Literal["tools", "__end__"]:
    """Conditional Edge: Routes to `tools` if the LLM emitted tool calls, otherwise terminates the turn (`END`)."""
    # Cancellation check: route straight to END if turn was aborted
    ctx = get_hitl_execution_context()
    thread_id = ctx.get("thread_id") or ctx.get("conversation_id")
    if is_thread_cancelled(thread_id):
        return END

    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
    return END


# ── Graph Assembly ───────────────────────────────────────────────────────────

workflow = StateGraph(NexusAgentState)

# 1. Register Graph Nodes
workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)

# 2. Define Execution Edges
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")

# 3. Compile statelessly: durable multi-turn history lives canonically in `logs/chats.db` (`thread_messages`)
nexus_graph = workflow.compile()
