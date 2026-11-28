"""
subagent.py — Isolated Dynamic Subagent Worker Loop (`spawn_subagent`).

Implements the ephemeral, stateless ReAct subagent spawner used by the Head Agent
(`NexusAgent`) for parallel fan-out, Architect-Drafter delegation, fail-fast disk and
`cache://` pre-hydration, ancestor `Section Instructions.md` discovery, KV-cache-preserving
soft/hard synthesis landings, and turn / uncached-token circuit breakers.
"""
import time
# Typing primitives:
# - Optional: Explicit nullable parameter annotation (`T | None`)
# - Sequence: Immutable ordered sequence of LangChain `BaseMessage` objects
from typing import Optional, Sequence

# LangChain message & tool primitives:
# - AIMessage: Assistant responses (either conversational text or tool call requests)
# - BaseMessage: Abstract parent class for all chat messages
# - HumanMessage: Subagent initial task prompts or flattened tool-free synthesis transcripts
# - SystemMessage: Ephemeral top-level instructions injected per LLM invocation
# - ToolMessage: Output returned from executing a `@tool` function
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
# ToolNode: Prebuilt LangGraph node that executes tool calls emitted by an `AIMessage`
from langgraph.prebuilt import ToolNode

from nexus.agent.runtime import (
    CORE_TOOLS,
    _build_system_message,
    _invoke_llm_with_resilience,
    _invoke_tool_node_resilient,
    _log_token_usage,
    _next_subagent_tracer,
    get_active_turn_provider,
    is_thread_cancelled,
)
from nexus.agent.sanitization import extract_message_text, extract_message_thinking
from nexus.core.config import EngineSettings, settings
from nexus.core.constants import ModelTier, get_chat_model, resolve_model_config, resolve_resilience_max_retries
from nexus.core.context_telemetry import (
    build_llm_call_manifest,
    build_subagent_start_manifest,
)
# inject_root_instructions: Dynamically loads and hydrates `Vault/Master Instructions.md` (<1ms disk read)
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import (
    get_hitl_execution_context,
    reset_hitl_execution_context,
    set_hitl_execution_context,
)
from nexus.core.instruction_guard import clear_seen_instructions
from nexus.core.trace import (
    get_trace_run_id,
    reset_trace_thread_id,
    set_trace_thread_id,
)
from nexus.shared_tools.shared import hydrate_subagent_context_files


# ── Dynamic Subagent Spawner (`spawn_subagent`) ──────────────────────────────

# `ai_msg: AIMessage` is the subagent response containing `tool_calls` that tripped a budget cap.
# `budget_reason: str` is the human-readable limit description (e.g. `"turn limit (25/25)"`).
# `-> list[ToolMessage]` returns one synthetic `ToolMessage(status="error")` per pending `tool_call_id`.
def _build_budget_refusal_tool_messages(ai_msg: AIMessage, budget_reason: str) -> list[ToolMessage]:
    """Synthesize refusal `ToolMessage` stubs so bound `sub_llm` can synthesize while keeping its KV cache prefix intact.

    Why we prefer this over `_build_tool_free_synthesis_messages()` on the primary cutoff pass:
    1. Provider APIs (Gemini, Anthropic, OpenAI) require a `ToolMessage` for every `tool_call_id` emitted by `ai_msg`,
       and key their KV prompt caches on byte-identical leading messages + `tools` definitions.
    2. Leaving prior `sub_messages` and bound `CORE_TOOLS` untouched while appending synthetic error `ToolMessage`s keeps
       ~85–90% of the prompt cached (instead of dropping to 0% cache on flattened plain-text synthesis).
    """
    tool_calls = getattr(ai_msg, "tool_calls", None) or []
    refusal_msgs: list[ToolMessage] = []
    notice = (
        f"[SYSTEM: Subagent {budget_reason} reached — tool call skipped. "
        "Do not call any more tools. Synthesize your final answer now from the context already gathered.]"
    )
    for idx, tc in enumerate(tool_calls):
        tc_name = str(tc.get("name") or "unknown")
        # Preserve exact provider call ID (fallback ensures valid pairing if an adapter omitted `id`)
        tc_id = str(tc.get("id") or f"budget_cap_{idx}")
        refusal_msgs.append(
            ToolMessage(
                content=notice,
                name=tc_name,
                tool_call_id=tc_id,
                status="error",
            )
        )
    return refusal_msgs


# `messages: Sequence[BaseMessage]` is the subagent message list ending in an `AIMessage(tool_calls)` that exceeded budget.
# `-> list[BaseMessage]` returns provider-safe plain-text messages ending with a tool-free synthesis directive.
def _build_tool_free_synthesis_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Flatten tool-calling turns into plain text for a single unbound (`sub_base_llm`) final synthesis call.

    Why flattening is required when invoking `sub_base_llm` without `bind_tools(...)`:
    1. Provider APIs (Anthropic Messages, Google Gemini, OpenAI) reject dangling `AIMessage(tool_calls)` lacking
       matching `ToolMessage` responses, and Anthropic rejects `tool_use`/`tool_result` blocks when `tools` are omitted.
    2. Converting prior `tool_calls` and `ToolMessage` outputs into plain `AIMessage`/`HumanMessage` transcripts
       keeps the emergency synthesis call valid across every provider while leaving normal turns 100% KV-cached.
    """
    synthesis_messages: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            synthesis_messages.append(msg)
        elif isinstance(msg, AIMessage):
            text_body = extract_message_text(msg).strip()
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                called_names = ", ".join(str(tc.get("name", "unknown")) for tc in tool_calls)
                note = f"[Called tools: {called_names}]"
                combined = f"{text_body}\n{note}".strip() if text_body else note
                synthesis_messages.append(AIMessage(content=combined))
            else:
                synthesis_messages.append(AIMessage(content=text_body or "(no text)"))
        elif isinstance(msg, ToolMessage):
            t_name = getattr(msg, "name", None) or "tool"
            t_text = extract_message_text(msg).strip()
            formatted = f"[Tool Result ({t_name})]:\n{t_text}"
            # Merge consecutive HumanMessages so alternating user/assistant turn structure stays clean
            if synthesis_messages and isinstance(synthesis_messages[-1], HumanMessage):
                prev = extract_message_text(synthesis_messages[-1])
                synthesis_messages[-1] = HumanMessage(content=f"{prev}\n\n{formatted}")
            else:
                synthesis_messages.append(HumanMessage(content=formatted))
        else:
            msg_text = extract_message_text(msg)
            if synthesis_messages and isinstance(synthesis_messages[-1], HumanMessage):
                prev = extract_message_text(synthesis_messages[-1])
                synthesis_messages[-1] = HumanMessage(content=f"{prev}\n\n{msg_text}")
            else:
                synthesis_messages.append(HumanMessage(content=msg_text))

    directive = (
        "[SYSTEM: Subagent turn/token budget reached. Do not call more tools. "
        "Synthesize your findings now from the information already gathered.]"
    )
    if synthesis_messages and isinstance(synthesis_messages[-1], HumanMessage):
        prev = extract_message_text(synthesis_messages[-1])
        synthesis_messages[-1] = HumanMessage(content=f"{prev}\n\n{directive}")
    else:
        synthesis_messages.append(HumanMessage(content=directive))
    return synthesis_messages


# `task_prompt: str` is the self-contained objective and output specification for the subagent.
# `model_tier: ModelTier` selects capability/cost tier (`"low"`, `"medium"`, or `"strong"`).
# `context_files: Optional[list[str]]` optional Vault paths/titles resolved and pre-hydrated from disk before boot.
# `-> str` returns the subagent's final distilled synthesis or a fail-fast resolution error if any `context_files` path is invalid.
@tool
def spawn_subagent(
    task_prompt: str,
    model_tier: ModelTier = "low",
    context_files: Optional[list[str]] = None,
) -> str:
    """Spawn an isolated subagent for parallel research, audit, synthesis, or HITL-staged Vault edits.

    Emitting multiple `spawn_subagent` calls in one turn runs them concurrently in parallel.
    Pass verified Vault paths or `cache://...` keys via `context_files` for zero-turn pre-hydration
    (ancestor `Section Instructions.md` files are auto-discovered and fail-fast checked before boot).

    Args:
        task_prompt: Self-contained objective, target scope, constraints, and expected output format.
        model_tier: `"low"` (default), `"medium"`, or `"strong"` (clamped unless enabled).
        context_files: Optional Vault paths/titles or `cache://...` handles to pre-hydrate before Turn 1.
    """
    effective_tier: ModelTier = model_tier if model_tier in ("low", "medium", "strong") else "low"
    # Subagent Tier Clamp (`C3`): enforce Architect-Drafter cost boundary by clamping `"strong"` worker requests
    # down to `"low"` unless `NEXUS_ALLOW_STRONG_SUBAGENTS=true` is explicitly enabled in `.env` or settings.
    allow_strong_subagents = bool(
        EngineSettings().nexus_allow_strong_subagents
        or getattr(settings, "nexus_allow_strong_subagents", False)
    )
    was_tier_clamped = False
    if effective_tier == "strong" and not allow_strong_subagents:
        effective_tier = "low"
        was_tier_clamped = True

    # Propagate conversation_id from parent while scoping thread_id, agent_id, and agent_role to this subagent
    parent_ctx = get_hitl_execution_context()
    parent_convo = parent_ctx.get("conversation_id") or "nexus_primary"
    parent_thread = parent_ctx.get("thread_id") or parent_convo

    # Match the parent turn's provider when chatting on Anthropic (e.g. `"anthropic:low"` -> `claude-haiku-5-5`)
    # Scoped strictly to parent_convo so parallel swarms on different provider families never cross-contaminate
    parent_provider = get_active_turn_provider(parent_convo)
    sub_tier_arg = f"anthropic:{effective_tier}" if parent_provider == "anthropic" else effective_tier
    sub_resolved = resolve_model_config(sub_tier_arg)
    sub_model_name = sub_resolved["model_name"]

    serial, sub_id, local_tracer = _next_subagent_tracer(effective_tier, thread_id=parent_convo)
    t0 = time.time()

    # Scope trace context variable so all subagent events and tool calls inherit the conversation UUID
    trace_token = set_trace_thread_id(parent_convo)

    sub_thread_id = f"{parent_thread}:{sub_id}" if parent_thread else sub_id
    sub_ctx_token = set_hitl_execution_context(
        conversation_id=parent_convo,
        thread_id=sub_thread_id,
        agent_id=sub_id,
        agent_role=f"Subagent #{serial} ({effective_tier})",
    )
    subagent_timeout_s = max(30.0, float(getattr(settings, "nexus_subagent_timeout", 900) or 900))
    tool_timeout_s = max(15.0, float(getattr(settings, "nexus_tool_timeout", 120) or 120))
    deadline = t0 + subagent_timeout_s

    try:
        # Resolve explicit `context_files` AND auto-discovered ancestor `Section Instructions.md` files before Turn 1.
        # If any explicit path is hallucinated/missing on disk, fail fast and surface real sibling files to the Commander.
        effective_task_prompt = task_prompt
        prehydrated_block, hydration_error = hydrate_subagent_context_files(
            context_files or [],
            task_prompt=task_prompt,
            auto_discover_section_instructions=True,
        )
        if hydration_error:
            local_tracer.agent_start(
                f"Subtask #{serial} ({effective_tier} · {sub_model_name}): {task_prompt}",
                metadata={
                    "serial": serial,
                    "subagent_id": sub_id,
                    "thread_id": parent_convo,
                    "model_tier": effective_tier,
                    "model_name": sub_model_name,
                    "task_prompt": task_prompt,
                    "context_files": list(context_files) if context_files else [],
                },
            )
            err_report = (
                f"❌ Subagent #{serial} ({effective_tier} · {sub_model_name}) aborted before execution:\n\n"
                f"{hydration_error}"
            )
            local_tracer.tool_error("spawn_subagent", err_report)
            local_tracer.agent_end("Aborted (fail-fast): unresolved context_files")
            return err_report
        if prehydrated_block:
            effective_task_prompt = (
                f"{prehydrated_block}\n\n"
                f"---\n\n"
                f"# Assigned Subagent Task\n\n{task_prompt}"
            )

        # Build an ephemeral, stateless subagent client (no checkpointer needed; lives only for this subtask)
        sub_base_llm = get_chat_model(tier=sub_tier_arg, temperature=0.0)
        sub_llm = sub_base_llm.bind_tools(CORE_TOOLS)
        # handle_tool_errors=True: Prebuilt LangGraph handler that intercepts unhandled tool exceptions
        # (e.g. HttpError 404/500, network disconnects, file locks) and wraps them into a ToolMessage(status="error")
        # rather than raising through ToolNode.invoke() and terminating the subagent turn mid-flight.
        sub_tool_node = ToolNode(CORE_TOOLS, handle_tool_errors=True)

        # Static subagent system prefix (no per-subagent serial numbers) so parallel and sequential subagents
        # share the exact same byte-identical prefix for Turn-1 KV prompt caching across Gemini and Anthropic.
        root_instructions = inject_root_instructions()
        subagent_protocol = (
            "### SUBAGENT EXECUTION PROTOCOL\n"
            "You are an ephemeral, isolated Subagent worker spawned by the Supervisor (NexusAgent).\n"
            "1. Read any relevant `Section Instructions.md` and Vault notes needed to execute your assigned task thoroughly.\n"
            "2. **Batch Tool Calls:** Emit all independent `search_vault`, `read_file`, `get_directory_structure`, `fetch_emails`, `create_file`, and `modify_file` (on distinct files) calls in parallel in the same turn rather than one tool call per turn. Use `search_vault(keywords=[...])` for multi-term Vault searches, and use `start_line`/`end_line` slices on large notes when full files are unnecessary.\n"
            "3. **Two-Phase Email Sweeps:** Call `fetch_emails(...)` with default metadata + snippets first (combining related terms with `OR` in one query), then pass ONLY the relevant `message_ids=[...]` to hydrate full bodies—skip newsletters and irrelevant hits.\n"
            "4. Return a concise, high-signal, grounded synthesis of your findings in your final response "
            "so the Supervisor can integrate your work directly."
        )
        sub_sys_content = f"{root_instructions}\n\n{subagent_protocol}"

        # Build deduplicated SHA-256 context manifest after pre-hydration so `agent_start` captures the exact injected context
        active_run_id = get_trace_run_id()
        sub_manifest, sub_ctx_summary = build_subagent_start_manifest(
            root_instructions=root_instructions,
            subagent_protocol=subagent_protocol,
            tools=CORE_TOOLS,
            prehydrated_block=prehydrated_block,
            task_prompt=task_prompt,
            context_files=context_files,
            run_id=active_run_id,
        )
        local_tracer.agent_start(
            f"Subtask #{serial} ({effective_tier} · {sub_model_name}): {task_prompt}",
            metadata={
                "serial": serial,
                "subagent_id": sub_id,
                "thread_id": parent_convo,
                "model_tier": effective_tier,
                "model_name": sub_model_name,
                "task_prompt": task_prompt,
                "context_files": list(context_files) if context_files else [],
                "context_manifest": sub_manifest,
                "context_summary": sub_ctx_summary,
            },
        )
        if was_tier_clamped:
            local_tracer.info(
                "🔒 Clamped requested subagent tier 'strong' -> 'low' (set NEXUS_ALLOW_STRONG_SUBAGENTS=true to permit strong subagents).",
                data={"requested_tier": "strong", "effective_tier": "low"},
            )

        # Run ReAct loop until the subagent finishes tool calls or hits its turn / uncached-token budget cap
        max_turns = max(1, int(getattr(settings, "subagent_max_turns", 25) or 25))
        max_uncached_input_tokens = max(
            1, int(getattr(settings, "subagent_max_uncached_input_tokens", 450_000) or 450_000)
        )
        sub_messages: list[BaseMessage] = [
            _build_system_message(sub_sys_content, sub_resolved["provider"]),
            HumanMessage(content=effective_task_prompt),
        ]
        turn_idx = 0
        cumulative_input_tokens = 0
        cumulative_uncached_input_tokens = 0
        peak_context_tokens = 0
        soft_warning_sent = False

        while True:
            # Cancellation guard: abort subagent immediately if the parent turn was stopped by user
            if is_thread_cancelled(parent_convo) or is_thread_cancelled(parent_thread):
                raise InterruptedError(f"Subagent #{serial} execution stopped by user via Stop & Revert.")

            # Wall-clock deadline guard: fail cleanly with partial context if a subagent runs past its budget
            remaining_s = deadline - time.time()
            if remaining_s <= 0:
                raise TimeoutError(
                    f"Subagent #{serial} exceeded wall-clock budget of {int(subagent_timeout_s)}s after {turn_idx} turn(s)."
                )

            turn_idx += 1
            call_manifest, call_summary = build_llm_call_manifest(
                messages=sub_messages,
                tools=CORE_TOOLS,
                run_id=active_run_id,
            )
            local_tracer.llm_call(
                metadata={
                    "turn": turn_idx,
                    "model_tier": effective_tier,
                    "model_name": sub_model_name,
                    "context_manifest": call_manifest,
                    "context_summary": call_summary,
                }
            )
            ai_msg = _invoke_llm_with_resilience(
                llm=sub_llm,
                messages=sub_messages,
                tracer=local_tracer,
                thread_ids=[parent_convo, parent_thread, sub_id],
                model_name=sub_model_name,
                tier=effective_tier,
                max_retries=resolve_resilience_max_retries(effective_tier),
            )
            usage_stats = _log_token_usage(local_tracer, ai_msg, model_name=sub_model_name, tier=effective_tier)
            turn_in = int(usage_stats.get("input_tokens", 0) or 0)
            turn_cached = int(usage_stats.get("cached_tokens", 0) or 0)
            turn_uncached = max(0, turn_in - turn_cached)
            cumulative_input_tokens += turn_in
            cumulative_uncached_input_tokens += turn_uncached
            peak_context_tokens = max(peak_context_tokens, turn_in)
            thinking_text = extract_message_thinking(ai_msg)
            if thinking_text:
                local_tracer.llm_thinking(
                    thinking_text,
                    metadata={"turn": turn_idx, "model_tier": effective_tier, "model_name": sub_model_name},
                )
            sub_messages.append(ai_msg)

            if not getattr(ai_msg, "tool_calls", None):
                final_text = extract_message_text(ai_msg)
                elapsed_sub = round(time.time() - t0, 2)
                local_tracer.llm_response(final_text, metadata={"turn": turn_idx, "latency_seconds": elapsed_sub})
                local_tracer.agent_end(f"Completed in {elapsed_sub:.1f}s")
                return final_text

            # Turn & cumulative uncached input-token circuit breaker: if the model still wants tools at/past budget,
            # reject pending tool calls with synthetic `ToolMessage` stubs and invoke bound `sub_llm` so the KV cache
            # prefix stays intact (~85–90% hit rate), falling back to unbound `sub_base_llm` only if it insists on tools.
            # Note: We intentionally preserve full KV prompt-cache prefixes during turns 1..N (no sliding-window
            # ToolMessage mutation mid-loop) and rely on `context_files` + output caps to keep normal turns lean.
            budget_kind: Optional[str] = None
            budget_reason: Optional[str] = None
            if turn_idx >= max_turns:
                budget_kind = "turn_limit"
                budget_reason = f"turn limit ({turn_idx}/{max_turns})"
            elif cumulative_uncached_input_tokens >= max_uncached_input_tokens:
                budget_kind = "uncached_token_budget"
                budget_reason = (
                    f"uncached input token budget ({cumulative_uncached_input_tokens:,}/{max_uncached_input_tokens:,})"
                )

            if budget_reason:
                local_tracer.info(
                    f"⚠️ Subagent #{serial} reached {budget_reason}. Requesting cache-preserving final synthesis...",
                    data={
                        "event_kind": "subagent_budget_cap",
                        "reason": budget_kind,
                        "turn": turn_idx,
                        "max_turns": max_turns,
                        "cumulative_input_tokens": cumulative_input_tokens,
                        "cumulative_uncached_input_tokens": cumulative_uncached_input_tokens,
                        "max_uncached_input_tokens": max_uncached_input_tokens,
                        "peak_context_tokens": peak_context_tokens,
                        "cache_preserved_synthesis": True,
                    },
                )
                sub_messages.extend(_build_budget_refusal_tool_messages(ai_msg, budget_reason))
                cache_preserved = True
                synth_turn = turn_idx + 1
                synth_manifest, synth_summary = build_llm_call_manifest(
                    messages=sub_messages,
                    tools=CORE_TOOLS,
                    run_id=active_run_id,
                )
                local_tracer.llm_call(
                    metadata={
                        "turn": synth_turn,
                        "model_tier": effective_tier,
                        "model_name": sub_model_name,
                        "budget_synthesis": True,
                        "cache_preserved_synthesis": True,
                        "context_manifest": synth_manifest,
                        "context_summary": synth_summary,
                    }
                )
                final_ai_msg = _invoke_llm_with_resilience(
                    llm=sub_llm,
                    messages=sub_messages,
                    tracer=local_tracer,
                    thread_ids=[parent_convo, parent_thread, sub_id],
                    model_name=sub_model_name,
                    tier=effective_tier,
                    max_retries=resolve_resilience_max_retries(effective_tier),
                )
                _log_token_usage(local_tracer, final_ai_msg, model_name=sub_model_name, tier=effective_tier)

                # Stubborn-model safety net: if the model ignored refusal stubs and still emitted tool_calls,
                # flatten history and invoke unbound `sub_base_llm` once to guarantee loop termination.
                if getattr(final_ai_msg, "tool_calls", None):
                    cache_preserved = False
                    synth_turn = turn_idx + 2
                    local_tracer.info(
                        f"⚠️ Subagent #{serial} still emitted tool calls after cache-preserving cap; falling back to unbound synthesis...",
                        data={
                            "event_kind": "subagent_budget_cap_fallback",
                            "reason": budget_kind,
                            "turn": synth_turn,
                            "cache_preserved_synthesis": False,
                        },
                    )
                    sub_messages.append(final_ai_msg)
                    synthesis_messages = _build_tool_free_synthesis_messages(sub_messages)
                    fb_manifest, fb_summary = build_llm_call_manifest(
                        messages=synthesis_messages,
                        tools=None,
                        run_id=active_run_id,
                    )
                    local_tracer.llm_call(
                        metadata={
                            "turn": synth_turn,
                            "model_tier": effective_tier,
                            "model_name": sub_model_name,
                            "budget_synthesis": True,
                            "cache_preserved_synthesis": False,
                            "context_manifest": fb_manifest,
                            "context_summary": fb_summary,
                        }
                    )
                    final_ai_msg = _invoke_llm_with_resilience(
                        llm=sub_base_llm,
                        messages=synthesis_messages,
                        tracer=local_tracer,
                        thread_ids=[parent_convo, parent_thread, sub_id],
                        model_name=sub_model_name,
                        tier=effective_tier,
                        max_retries=resolve_resilience_max_retries(effective_tier),
                    )
                    _log_token_usage(local_tracer, final_ai_msg, model_name=sub_model_name, tier=effective_tier)

                final_thinking = extract_message_thinking(final_ai_msg)
                if final_thinking:
                    local_tracer.llm_thinking(
                        final_thinking,
                        metadata={
                            "turn": synth_turn,
                            "budget_reached": True,
                            "cache_preserved_synthesis": cache_preserved,
                            "model_tier": effective_tier,
                            "model_name": sub_model_name,
                        },
                    )
                final_text = extract_message_text(final_ai_msg).strip() or (
                    f"Subagent #{serial} reached {budget_reason} without returning synthesis text."
                )
                elapsed_sub = round(time.time() - t0, 2)
                local_tracer.llm_response(
                    final_text,
                    metadata={
                        "turn": synth_turn,
                        "budget_reached": True,
                        "cache_preserved_synthesis": cache_preserved,
                        "latency_seconds": elapsed_sub,
                    },
                )
                local_tracer.agent_end(f"Completed at budget cap in {elapsed_sub:.1f}s")
                return final_text

            # If the LLM emitted intermediate thought/explanation alongside tool calls, trace that text too
            intermediate_text = extract_message_text(ai_msg).strip()
            if intermediate_text:
                local_tracer.llm_response(intermediate_text, metadata={"turn": turn_idx, "intermediate": True})

            for tc in ai_msg.tool_calls:
                tc_name = tc.get("name", "unknown")
                tc_id = tc.get("id")
                local_tracer.tool_call(tc_name, tc.get("args", {}), call_id=tc_id)

            batch_timeout = min(tool_timeout_s, max(5.0, deadline - time.time()))
            tool_res = _invoke_tool_node_resilient(
                sub_tool_node,
                {"messages": sub_messages},
                timeout_seconds=batch_timeout,
            )
            for t_msg in tool_res.get("messages", []):
                t_name = getattr(t_msg, "name", "unknown")
                t_call_id = getattr(t_msg, "tool_call_id", None)
                t_content = extract_message_text(t_msg)
                if getattr(t_msg, "status", None) == "error":
                    local_tracer.tool_error(t_name, t_content, call_id=t_call_id)
                else:
                    local_tracer.tool_result(t_name, t_content, call_id=t_call_id)
                sub_messages.append(t_msg)

            # Soft-landing warning: notify once at `max_turns - 2` or 80% uncached budget by appending ONLY to the
            # brand-new tail `ToolMessage` so every preceding message in `sub_messages` stays byte-identical (KV-cached).
            near_turn_cap = max_turns >= 3 and turn_idx >= max_turns - 2
            near_token_cap = cumulative_uncached_input_tokens >= int(max_uncached_input_tokens * 0.80)
            if (
                not soft_warning_sent
                and (near_turn_cap or near_token_cap)
                and sub_messages
                and isinstance(sub_messages[-1], ToolMessage)
            ):
                soft_warning_sent = True
                tail_msg = sub_messages[-1]
                existing_text = extract_message_text(tail_msg)
                notice = (
                    f"\n\n[SYSTEM NOTICE: Approaching subagent budget "
                    f"(turn {turn_idx}/{max_turns}, uncached input "
                    f"{cumulative_uncached_input_tokens:,}/{max_uncached_input_tokens:,}). "
                    "Finish any critical pending writes now and return your concise final synthesis without further exploration.]"
                )
                sub_messages[-1] = ToolMessage(
                    content=f"{existing_text}{notice}",
                    name=getattr(tail_msg, "name", None),
                    tool_call_id=getattr(tail_msg, "tool_call_id", None),
                    status=getattr(tail_msg, "status", None) or "success",
                )
                local_tracer.info(
                    f"⏳ Subagent #{serial} approaching budget (turn {turn_idx}/{max_turns}, "
                    f"uncached {cumulative_uncached_input_tokens:,}/{max_uncached_input_tokens:,}); soft-landing notice injected.",
                    data={
                        "event_kind": "subagent_soft_warning",
                        "turn": turn_idx,
                        "max_turns": max_turns,
                        "cumulative_input_tokens": cumulative_input_tokens,
                        "cumulative_uncached_input_tokens": cumulative_uncached_input_tokens,
                        "max_uncached_input_tokens": max_uncached_input_tokens,
                        "peak_context_tokens": peak_context_tokens,
                    },
                )
    except InterruptedError:
        elapsed_sub = round(time.time() - t0, 2)
        local_tracer.agent_end(f"Stopped by user after {elapsed_sub:.1f}s")
        raise
    except Exception as exc:
        elapsed_sub = round(time.time() - t0, 2)
        err_report = f"❌ Subagent #{serial} ({effective_tier} · {sub_model_name}) failed after {elapsed_sub:.1f}s: {exc}"
        local_tracer.tool_error("spawn_subagent", err_report)
        local_tracer.agent_end(f"Failed after {elapsed_sub:.1f}s: {exc}")
        return err_report
    finally:
        # Prune ephemeral subagent instruction-ledger entries before restoring parent execution scope.
        clear_seen_instructions(sub_thread_id)
        reset_hitl_execution_context(sub_ctx_token)
        reset_trace_thread_id(trace_token)
