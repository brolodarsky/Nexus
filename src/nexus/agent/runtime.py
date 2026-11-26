"""
runtime.py — Shared Execution Runtime Primitives for NexusAgent & Subagents.

Houses thread-isolated subagent tracking, Stop & Revert cancellation registries,
core tool bindings (`CORE_TOOLS`), provider-aware prompt-cache system messages,
token usage telemetry, resilient LLM rate-limit/signature retry handling, and
bounded-timeout `ToolNode` execution shared by `subagent.py` and `graph.py`.
"""
# contextvars: Propagates active thread_id and HITL execution context across timeout wrapper threads
import contextvars
# concurrent.futures: Enables bounded wall-clock timeouts on tool batches without blocking on hung sockets
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
# re: Regular expressions used to parse provider error payloads (e.g. `retryDelay` intervals on 429)
import re
# threading: Provides thread-safe locking (`Lock`) for assigning unique serial numbers to parallel subagents
import threading
import time
import uuid
# Typing primitives:
# - Any: Dynamic LangChain runnable / payload container where concrete model wrappers vary by provider
# - Optional: Explicit nullable parameter or return annotation (`T | None`)
# - Sequence: Immutable ordered sequence of LangChain `BaseMessage` objects or thread IDs
from typing import Any, Optional, Sequence

# LangChain message primitives:
# - BaseMessage: Abstract parent class for all chat messages
# - SystemMessage: Ephemeral top-level instructions injected per LLM invocation
# - ToolMessage: Output returned from executing a `@tool` function
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
# ToolNode: Prebuilt LangGraph node that executes tool calls emitted by an `AIMessage`
from langgraph.prebuilt import ToolNode

from nexus.agent.sanitization import _sanitize_messages_for_provider
from nexus.core.cost import calculate_token_cost
from nexus.core.instruction_guard import (
    reset_instruction_batch_id,
    set_instruction_batch_id,
)
from nexus.core.trace import AgentTracer
from nexus.shared_tools.shared import (
    create_calendar_event,
    create_file,
    delete_calendar_event,
    delete_file,
    fetch_emails,
    fill_browser_form,
    get_calendar_schedule,
    get_directory_structure,
    get_recent_modifications,
    list_browser_tabs,
    modify_file,
    move_file,
    open_browser_tabs,
    read_browser_tabs,
    read_file,
    run_shared_tool_cli,
    search_vault,
    search_web,
    send_telegram_notification,
    spawn_conversation,
    transcribe_media,
    update_calendar_event,
)

# ── Agent Tracers & Subagent Serial Counter ──────────────────────────────────

# Cyan console logger and SSE event emitter for the primary Head Agent (root node `agent_id="nexus"`)
nexus_tracer = AgentTracer("Head Agent", color="cyan", agent_id="nexus", parent_id=None)

# Thread-safe serial counter and color palette so concurrent `spawn_subagent` worker threads get distinct IDs (`subagent-1`, `subagent-2`, ...)
# _subagent_counter_lock: Re-entrant or mutual exclusion lock protecting per-thread counter allocations and provider lookups
_subagent_counter_lock = threading.Lock()
# _thread_subagent_counters: Maps conversation/thread UUID string -> int serial counter, isolating concurrent swarms
_thread_subagent_counters: dict[str, int] = {}
# _thread_active_providers: Maps conversation/thread UUID string -> str ("gemini", "anthropic", "openai") for provider consistency
_thread_active_providers: dict[str, str] = {}
# Global fallback counter and provider for single-turn CLI runs or unit tests invoked without explicit thread IDs
_subagent_serial_counter = 0
_default_active_provider: Optional[str] = None
# Tracks the active parent turn's LLM provider (`"gemini"`, `"anthropic"`, `"openai"`) so spawned subagents match the turn's provider family
_active_turn_provider: Optional[str] = None
_SUBAGENT_COLORS = ["magenta", "yellow", "green", "blue"]


def set_active_turn_provider(provider: str, thread_id: Optional[str] = None) -> None:
    """Sets the active LLM provider for the specified thread_id and updates process fallback state.

    Args:
        provider: Provider identifier string (e.g. "anthropic", "gemini", "openai").
        thread_id: Optional conversation/thread UUID. When provided, isolates this turn's provider family
                   from other conversations executing concurrently in background worker threads.
    """
    global _active_turn_provider, _default_active_provider
    with _subagent_counter_lock:
        _active_turn_provider = provider
        _default_active_provider = provider
        if thread_id:
            _thread_active_providers[thread_id] = provider


def get_active_turn_provider(thread_id: Optional[str] = None) -> Optional[str]:
    """Retrieves the active LLM provider for the specified thread_id, falling back to ambient context or global default.

    Args:
        thread_id: Optional conversation/thread UUID. If omitted, attempts lookup via ambient HITL execution context.

    Returns:
        Provider identifier string (e.g. "anthropic", "gemini", "openai") or None if unconfigured.
    """
    effective_thread = thread_id
    if not effective_thread:
        try:
            from nexus.core.hitl_queue import get_hitl_execution_context
            ctx = get_hitl_execution_context()
            effective_thread = ctx.get("conversation_id") or ctx.get("thread_id")
        except Exception:
            pass

    with _subagent_counter_lock:
        if effective_thread and effective_thread in _thread_active_providers:
            return _thread_active_providers[effective_thread]
        return _active_turn_provider or _default_active_provider


def reset_subagent_counter(thread_id: Optional[str] = None) -> None:
    """Resets the subagent serial number counter and active provider.

    Args:
        thread_id: Optional conversation/thread UUID. If provided (or resolved from ambient HITL context),
                   resets ONLY that thread's subagent counter and provider state, leaving concurrent swarms
                   in other conversations unaffected. If omitted and no context exists, resets global defaults.
    """
    global _subagent_serial_counter, _active_turn_provider, _default_active_provider
    effective_thread = thread_id
    if not effective_thread:
        try:
            from nexus.core.hitl_queue import get_hitl_execution_context
            ctx = get_hitl_execution_context()
            effective_thread = ctx.get("conversation_id") or ctx.get("thread_id")
        except Exception:
            pass

    with _subagent_counter_lock:
        if effective_thread:
            _thread_subagent_counters[effective_thread] = 0
            _thread_active_providers.pop(effective_thread, None)
        else:
            _thread_subagent_counters.clear()
            _thread_active_providers.clear()
            _default_active_provider = None
        _subagent_serial_counter = 0
        _active_turn_provider = None


def _next_subagent_tracer(tier: str, thread_id: Optional[str] = None) -> tuple[int, str, AgentTracer]:
    """Allocates a thread-safe sequential serial number and dedicated `AgentTracer` linked to `parent_id="nexus"`.

    Args:
        tier: Capability tier string (e.g. "low", "medium", "strong") for the tracer badge label.
        thread_id: Optional conversation UUID. Scopes the sequential counter strictly to this conversation thread.

    Returns:
        tuple[int, str, AgentTracer]: (serial_number, subagent_id, AgentTracer_instance).
    """
    global _subagent_serial_counter
    effective_thread = thread_id
    if not effective_thread:
        try:
            from nexus.core.hitl_queue import get_hitl_execution_context
            ctx = get_hitl_execution_context()
            effective_thread = ctx.get("conversation_id") or ctx.get("thread_id")
        except Exception:
            pass

    with _subagent_counter_lock:
        if effective_thread:
            current = _thread_subagent_counters.get(effective_thread, 0) + 1
            _thread_subagent_counters[effective_thread] = current
            serial = current
        else:
            _subagent_serial_counter += 1
            serial = _subagent_serial_counter

    sub_id = f"subagent-{serial}"
    color = _SUBAGENT_COLORS[(serial - 1) % len(_SUBAGENT_COLORS)]
    tracer = AgentTracer(
        agent_name=f"Subagent #{serial} ({tier})",
        color=color,
        agent_id=sub_id,
        parent_id="nexus",
        thread_id=thread_id,
    )
    return serial, sub_id, tracer


# ── Thread Cancellation Registry (Stop & Revert) ───────────────────────────────
# Thread-safe dictionary mapping active conversation UUIDs to cancellation events (`threading.Event`)
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.Lock()


def register_cancel_event(thread_id: str, event: threading.Event) -> None:
    """Registers a threading.Event used to signal immediate interruption for an in-flight agent turn."""
    if not thread_id:
        return
    with _CANCEL_LOCK:
        _CANCEL_EVENTS[thread_id] = event


def unregister_cancel_event(thread_id: str) -> None:
    """Removes a conversation's cancellation event after execution settles or is aborted."""
    if not thread_id:
        return
    with _CANCEL_LOCK:
        _CANCEL_EVENTS.pop(thread_id, None)


def is_thread_cancelled(thread_id: Optional[str]) -> bool:
    """Checks whether the given conversation thread has been signaled to stop and revert."""
    if not thread_id:
        return False
    # Normalize subagent threads (e.g., 'conv_123:subagent-1' -> 'conv_123') to check root status
    root_thread = thread_id.split(":")[0] if ":" in thread_id else thread_id
    with _CANCEL_LOCK:
        event = _CANCEL_EVENTS.get(thread_id) or _CANCEL_EVENTS.get(root_thread)
        return event.is_set() if event else False


# ── Core Tool Set (Shared by Parent NexusAgent and Subagents) ────────────────

# Most-used deterministic tools bound directly so the agent can navigate, read, surgically edit,
# check recent modifications, search the live web, inspect emails/calendar, or invoke any other `[CLI]` tool on demand.
CORE_TOOLS = [
    read_file,
    modify_file,
    create_file,
    move_file,
    delete_file,
    get_directory_structure,
    search_vault,
    get_recent_modifications,
    search_web,
    list_browser_tabs,
    read_browser_tabs,
    open_browser_tabs,
    fill_browser_form,
    fetch_emails,
    get_calendar_schedule,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    send_telegram_notification,
    transcribe_media,
    spawn_conversation,
    run_shared_tool_cli,
]


# ── Helper: Provider-Aware SystemMessage Builder for Prompt Caching ──────────

# `content: str` is the hydrated markdown system instructions from `inject_root_instructions()`.
# `provider: str` is the normalized provider key (`"gemini"`, `"anthropic"`, `"openai"`).
# `-> SystemMessage` returns a SystemMessage with an explicit ephemeral cache breakpoint when targeting Anthropic,
# or a clean plain-string SystemMessage for Gemini/OpenAI automatic prefix caching.
def _build_system_message(content: str, provider: str) -> SystemMessage:
    """Construct a SystemMessage configured for optimal provider KV prompt caching.

    For Anthropic Claude models, wraps the static constitutional prompt in a content block with
    `cache_control: {"type": "ephemeral"}` so the large root instructions block is cached cleanly across
    distinct threads and parallel subagent invocations (90-95% input cost savings on hits).
    """
    if provider == "anthropic":
        return SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )
    return SystemMessage(content=content)


# ── Helper: Token Telemetry & Cost Logging ───────────────────────────────────

def _log_token_usage(
    tracer: AgentTracer,
    ai_msg: BaseMessage,
    model_name: Optional[str] = None,
    tier: Optional[str] = None,
) -> dict[str, Any]:
    """Extracts and logs prompt token counts, cached token hits (`cache_read`), output tokens, and estimated USD cost from an AIMessage."""
    usage = getattr(ai_msg, "usage_metadata", None)
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
    in_tok = int(usage.get("input_tokens", 0) or 0)
    out_tok = int(usage.get("output_tokens", 0) or 0)
    details = usage.get("input_token_details") or {}
    cached_tok = int(details.get("cache_read", 0) or 0) if isinstance(details, dict) else 0
    # `output_token_details.reasoning` is already included in `out_tok` by LangChain's Gemini/Anthropic adapters;
    # log it separately for observability without adding it to `out_tok` (prevents double-counting cost).
    out_details = usage.get("output_token_details") or {}
    reasoning_tok = int(out_details.get("reasoning", 0) or 0) if isinstance(out_details, dict) else 0
    cost_usd = calculate_token_cost(
        input_tokens=in_tok,
        output_tokens=out_tok,
        cached_tokens=cached_tok,
        model_name=model_name,
        tier=tier,
    )
    if in_tok or out_tok:
        cache_pct = int((cached_tok / in_tok) * 100) if in_tok > 0 else 0
        reasoning_suffix = f" ({reasoning_tok:,} reasoning)" if reasoning_tok > 0 else ""
        info_data: dict[str, Any] = {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cached_tokens": cached_tok,
            "cache_pct": cache_pct,
            "cost_usd": cost_usd,
            "model_name": model_name,
            "model_tier": tier,
        }
        if reasoning_tok > 0:
            info_data["reasoning_tokens"] = reasoning_tok
        tracer.info(
            f"Tokens: {in_tok:,} in ({cached_tok:,} cached, {cache_pct}%) | {out_tok:,} out{reasoning_suffix} · ~${cost_usd:.4f}",
            data=info_data,
        )
    return {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cached_tokens": cached_tok,
        "reasoning_tokens": reasoning_tok,
        "cost_usd": cost_usd,
    }


# ── Helper: Resilient LLM Invocation with Cooperative 429 Rate-Limit Backoff ─

# `error: Exception` is the raw provider or LangChain exception intercepted during `.invoke()`.
# `-> bool` returns True if the exception represents an HTTP 429 Too Many Requests, Google RESOURCE_EXHAUSTED,
# or provider rate-limit quota exhaustion event.
def _is_rate_limit_error(error: Exception) -> bool:
    """Determine whether an exception represents an AI provider 429 rate limit or quota exhaustion.

    Catches:
      1. HTTP 429 status codes across all provider clients (Google, Anthropic, OpenAI).
      2. Google gRPC `RESOURCE_EXHAUSTED` errors (`generativelanguage.googleapis.com` TPM/RPM quota breaches).
      3. Provider SDK exception classes (`RateLimitError`, `ResourceExhausted`).
    """
    err_str = str(error)
    err_lower = err_str.lower()
    type_name = type(error).__name__.lower()

    # Check status code attributes if present on the exception or its nested response
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if status_code in (429, "429", "RESOURCE_EXHAUSTED"):
        return True

    # Check error string for HTTP 429 or Google RESOURCE_EXHAUSTED tokens
    if "429" in err_str:
        return True
    if "RESOURCE_EXHAUSTED" in err_str.upper() or "resourceexhausted" in type_name:
        return True
    if "ratelimit" in type_name or "rate_limit" in err_lower or "rate limit" in err_lower or "quota exceeded" in err_lower:
        return True

    return False


# `error: Exception` is the raw provider or LangChain exception intercepted during `.invoke()`.
# `-> bool` returns True if the provider rejected a historical thought/thinking signature (HTTP 400 INVALID_ARGUMENT).
def _is_invalid_signature_error(error: Exception) -> bool:
    """Detect provider 400 rejections caused by foreign, stale, or corrupted reasoning/thought signatures.

    Occurs when conversation checkpoints contain cryptographic thinking signatures from one provider or model
    (e.g. Anthropic `thinking.signature` or an older reasoning token) and are replayed to a strict verifier
    such as Google Gemini (`INVALID_THOUGHT_SIGNATURE`) or Anthropic (`invalid signature`).
    """
    err_lower = str(error).lower()
    if "invalid_thought_signature" in err_lower or "invalid thought signature" in err_lower:
        return True
    if ("thought_signature" in err_lower or "thought signature" in err_lower) and any(
        tok in err_lower for tok in ("invalid", "400", "invalid_argument", "missing")
    ):
        return True
    if "thinking" in err_lower and "signature" in err_lower and any(
        tok in err_lower for tok in ("invalid", "400", "invalid_request_error", "mismatch", "corrupt")
    ):
        return True
    return False


# `error: Exception` is the rate-limit exception containing optional provider retry delay metadata.
# `attempt: int` is the zero-based retry attempt index used for exponential backoff fallback.
# `default_base_delay: float = 15.0` is the starting backoff in seconds if no provider hint is found.
# `-> float` returns the delay in seconds to sleep before retrying (clamped to [2.0, 60.0] seconds).
def _extract_retry_delay(error: Exception, attempt: int = 0, default_base_delay: float = 15.0) -> float:
    """Extract recommended wait time from provider error payload, or compute exponential backoff.

    Why dynamic delay extraction is critical:
    Google AI Studio Tier 1 applies a 2,000,000 input tokens per minute (2M TPM) sliding window. When breached,
    the API payload specifies exact remaining time until window rollover (e.g. `'retryDelay': '23s'` or
    `Please retry in 23.991883049s`). Sleeping standard SDK backoffs (1s, 2s, 4s) prematurely exhausts retries
    while the window is still closed; extracting the true delay guarantees the retry executes on a fresh window.
    """
    err_str = str(error)

    # 1. Match Google RPC `RetryInfo` dictionary pattern (e.g. `'retryDelay': '23s'` or `"retryDelay": "23.99s"`)
    m = re.search(r"""['"]retryDelay['"]:\s*['"](\d+(?:\.\d+)?)s?['"]""", err_str, re.IGNORECASE)
    if m:
        # Add 1.5s safety buffer so clock drift between local host and Google gateway does not trigger immediate re-rejection
        return min(60.0, max(2.0, float(m.group(1)) + 1.5))

    # 2. Match natural-language diagnostic text (e.g. 'retry in 23.991883049s' or 'try again in 20s')
    m = re.search(r"""(?:retry|try again) in (\d+(?:\.\d+)?)s""", err_str, re.IGNORECASE)
    if m:
        return min(60.0, max(2.0, float(m.group(1)) + 1.5))

    # 3. Match standard HTTP `retry-after` header syntax (e.g. 'retry-after: 25')
    m = re.search(r"""retry-after:\s*(\d+(?:\.\d+)?)""", err_str, re.IGNORECASE)
    if m:
        return min(60.0, max(2.0, float(m.group(1)) + 1.5))

    # 4. Fallback exponential backoff: 15s -> 30s -> 60s (scaled by attempt index)
    return min(60.0, float(default_base_delay * (2 ** attempt)))


# `seconds: float` is the total duration to wait.
# `thread_ids: Sequence[Optional[str]]` list of thread/conversation identifiers to inspect for user Stop & Revert.
def _cooperative_sleep(seconds: float, thread_ids: Sequence[Optional[str]]) -> None:
    """Sleep for `seconds` in 0.5s increments while polling for user Stop & Revert cancellation.

    Prevents UI hangs: if a user clicks 'Stop & Revert' while an agent is paused for 24s waiting for a rate-limit
    window to roll over, slicing sleep into 500ms intervals ensures the turn aborts cleanly in <500ms instead of
    blocking the worker thread for the entire delay.
    """
    deadline = time.time() + max(0.0, seconds)
    while time.time() < deadline:
        # Check cancellation across all associated thread and conversation UUIDs
        for tid in thread_ids:
            if tid and is_thread_cancelled(tid):
                raise InterruptedError(f"Turn execution for thread '{tid}' stopped by user during rate-limit backoff.")
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(0.5, remaining))


# `llm: Any` is the bound LangChain runnable (e.g. `active_llm.bind_tools(TOOLS)` or `sub_llm`).
# `messages: list[BaseMessage]` is the message history submitted to `.invoke()`.
# `tracer: AgentTracer` is the telemetry tracer emitting structured events to terminal and SSE stream.
# `thread_ids: Sequence[Optional[str]]` contains thread and conversation IDs for cooperative cancellation checks.
# `model_name: str` is the active model identifier (e.g. `'gemini-4-hydrogen'`) displayed in telemetry.
# `tier: str` is the capability tier (e.g. `'low'`, `'strong'`).
# `max_retries: int = 3` maximum number of rate-limit backoff retry attempts before re-raising.
# `-> BaseMessage` returns the model output (`AIMessage`).
def _invoke_llm_with_resilience(
    llm: Any,
    messages: list[BaseMessage],
    tracer: AgentTracer,
    thread_ids: Sequence[Optional[str]],
    model_name: str,
    tier: str,
    max_retries: int = 3,
) -> BaseMessage:
    """Invoke an LLM with automatic 429 rate-limit backoff, parameter self-healing, and signature recovery.

    Why this wrapper exists:
    1. Sliding Token-Window Backoff: LangChain's default HTTP retry policies use short 1s–4s exponential backoffs
       intended for network blips. When parallel subagents burst token velocity past provider minute-level ceilings
       (e.g. 2M TPM on Tier 1), immediate retries burn all attempts while the window remains saturated. This wrapper
       extracts exact `retryDelay` hints, notifies the user via SSE trace events, cooperatively sleeps, and retries.
    2. Ephemeral Self-Healing: Handles one-shot compatibility fixes (deprecated `temperature` dials or rejected
       historical thought signatures) on the outgoing request payload without mutating persisted checkpoints.
    """
    # Copy message list reference so one-shot reactive sanitization never mutates caller's list in place
    active_messages: list[BaseMessage] = list(messages)
    # Bounded retry/self-healing state: each one-shot flag may fire at most once; rate_limit_attempts <= max_retries
    rate_limit_attempts = 0
    has_cleared_temp = False
    has_cleared_thinking = False
    has_stripped_signatures = False

    while True:
        # Pre-inference cancellation check: abort immediately if user pressed Stop & Revert
        for tid in thread_ids:
            if tid and is_thread_cancelled(tid):
                raise InterruptedError(f"Turn execution for thread '{tid}' stopped by user.")

        try:
            return llm.invoke(active_messages)
        except Exception as e:
            err_msg_lower = str(e).lower()

            # Dynamic Sampling Parameter Self-Healing:
            # Newer frontier models (such as Claude Opus 5.5) deprecate custom temperature/sampling controls and return HTTP 400
            # (`temperature is deprecated for this model`). If encountered, strip the temperature attribute from the active client
            # (handling both direct BaseChatModel instances and tool-bound RunnableBinding instances) and retry once.
            if not has_cleared_temp and "temperature" in err_msg_lower and ("deprecated" in err_msg_lower or "not supported" in err_msg_lower):
                cleared_temp_now = False
                if hasattr(llm, "temperature") and getattr(llm, "temperature", None) is not None:
                    llm.temperature = None
                    cleared_temp_now = True
                if hasattr(llm, "bound") and hasattr(llm.bound, "temperature") and getattr(llm.bound, "temperature", None) is not None:
                    llm.bound.temperature = None
                    cleared_temp_now = True
                if cleared_temp_now:
                    has_cleared_temp = True
                    tracer.info(
                        f"ℹ️ Model '{model_name}' deprecated custom temperature sampling. Cleared temperature parameter and retrying...",
                        data={"model": model_name, "model_tier": tier},
                    )
                    continue

            # Dynamic Thinking Parameter Self-Healing:
            # If an Anthropic/Gemini model variant rejects `thinking` (or `include_thoughts`), clear the parameter
            # once from the active client (direct BaseChatModel or tool-bound RunnableBinding) and retry cleanly.
            if (
                not has_cleared_thinking
                and not _is_invalid_signature_error(e)
                and "thinking" in err_msg_lower
                and any(
                    tok in err_msg_lower
                    for tok in (
                        "not supported",
                        "unsupported",
                        "does not support",
                        "not allowed",
                        "invalid_request_error",
                        "extra inputs",
                        "unknown field",
                    )
                )
            ):
                cleared_thinking_now = False
                if hasattr(llm, "thinking") and getattr(llm, "thinking", None) is not None:
                    llm.thinking = None
                    cleared_thinking_now = True
                if hasattr(llm, "bound") and hasattr(llm.bound, "thinking") and getattr(llm.bound, "thinking", None) is not None:
                    llm.bound.thinking = None
                    cleared_thinking_now = True
                if cleared_thinking_now:
                    has_cleared_thinking = True
                    tracer.info(
                        f"ℹ️ Model '{model_name}' rejected thinking parameter. Cleared thinking configuration and retrying...",
                        data={"model": model_name, "model_tier": tier, "self_healed": "thinking"},
                    )
                    continue

            # Reactive Thought-Signature Self-Healing:
            # Safety net if a provider rejects a historical signature that slipped past proactive provider matching
            # (e.g. a legacy Gemini checkpoint with an incompatible signature format across model upgrades). Strip all
            # signatures ephemerally once and retry immediately; never loops if retry still fails.
            if not has_stripped_signatures and _is_invalid_signature_error(e):
                stripped = _sanitize_messages_for_provider(
                    active_messages,
                    target_provider="",
                    strip_all_signatures=True,
                )
                # Compare object identity (`is not`) so we only retry if sanitization actually altered at least one message
                if any(orig is not new for orig, new in zip(active_messages, stripped)):
                    has_stripped_signatures = True
                    active_messages = stripped
                    tracer.info(
                        f"ℹ️ Model '{model_name}' rejected a historical thought signature. Stripped incompatible signature metadata from ephemeral context and retrying...",
                        data={"model": model_name, "model_tier": tier, "self_healed": "thought_signature"},
                    )
                    continue

            # Only intercept rate-limit / quota errors for backoff; let 504 timeouts and logic errors propagate
            if _is_rate_limit_error(e) and rate_limit_attempts < max_retries:
                delay = _extract_retry_delay(e, attempt=rate_limit_attempts)
                rate_limit_attempts += 1
                tracer.info(
                    f"⏳ Rate limit reached (429 RESOURCE_EXHAUSTED). Waiting {delay:.1f}s for sliding token window rollover "
                    f"before automatic retry (attempt {rate_limit_attempts}/{max_retries})...",
                    data={
                        "model": model_name,
                        "model_tier": tier,
                        "retry_delay": delay,
                        "attempt": rate_limit_attempts,
                        "max_retries": max_retries,
                    },
                )
                _cooperative_sleep(delay, thread_ids)
                continue
            raise e


# ── Helper: Resilient ToolNode Execution with Timeout & Synchronous Fallback ─

def _build_timeout_tool_messages(state_or_input: dict[str, Any], timeout_seconds: float) -> list[ToolMessage]:
    """Synthesize error `ToolMessage`s for every pending tool call in the trailing `AIMessage` on timeout."""
    messages = state_or_input.get("messages", [])
    last_ai = messages[-1] if messages else None
    tool_calls = getattr(last_ai, "tool_calls", None) or []
    error_msgs: list[ToolMessage] = []
    for tc in tool_calls:
        tc_name = tc.get("name", "unknown")
        tc_id = tc.get("id") or "timeout_call"
        error_msgs.append(
            ToolMessage(
                content=f"Error: Tool '{tc_name}' timed out after {int(timeout_seconds)}s without returning a response.",
                name=tc_name,
                tool_call_id=tc_id,
                status="error",
            )
        )
    return error_msgs


# `node: ToolNode` is the LangGraph tool runner (`sub_tool_node` for subagents or `tool_node` for the parent agent).
# `state_or_input: dict[str, Any]` is the state dict containing `"messages"` whose trailing `AIMessage` holds `tool_calls`.
# `timeout_seconds: Optional[float]` optionally caps wall-clock wait for the tool batch, detaching hung threads cleanly.
# `-> dict[str, Any]` returns `{"messages": [ToolMessage, ...]}` matching `ToolNode.invoke()` output shape.
def _invoke_tool_node_resilient(
    node: ToolNode,
    state_or_input: dict[str, Any],
    timeout_seconds: Optional[float] = None,
) -> dict[str, Any]:
    """Execute a LangGraph `ToolNode` with bounded timeout protection and synchronous shutdown fallback.

    Why both safeguards exist:
    1. Bounded timeout: If a tool blocks indefinitely on an external socket or C extension, waiting with
       `executor.shutdown(wait=False)` prevents a single hung call from freezing the FastAPI worker thread forever,
       returning structured `ToolMessage(status='error')` responses so the agent/GUI sees an explicit error.
    2. Shutdown fallback: When `uvicorn --reload` flags `ThreadPoolExecutor` instances as `_shutdown = True`,
       `ToolNode.invoke()` raises `RuntimeError('cannot schedule new futures after shutdown')`; running tools
       sequentially on the current OS thread lets synchronous operations complete cleanly.
    """
    # Bind one batch UUID before `copy_context()` so parallel tool calls in a single `ToolNode` step
    # share the same batch tag and cannot bypass the write gate using a sibling read in the same turn.
    batch_token = set_instruction_batch_id(uuid.uuid4().hex)
    try:
        if timeout_seconds is not None and timeout_seconds > 0:
            # Copy ContextVars into the timeout wrapper thread so trace_thread_id, HITL context, and batch_id propagate
            ctx = contextvars.copy_context()
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(ctx.run, node.invoke, state_or_input)
            try:
                res = future.result(timeout=timeout_seconds)
                executor.shutdown(wait=False)
                return res
            except FuturesTimeoutError:
                # Never call `shutdown(wait=True)` on timeout, or the caller blocks until the hung tool exits
                executor.shutdown(wait=False, cancel_futures=True)
                return {"messages": _build_timeout_tool_messages(state_or_input, timeout_seconds)}
        return node.invoke(state_or_input)
    except RuntimeError as exc:
        if "cannot schedule new futures after" not in str(exc).lower():
            raise
        # Fallback: extract tool_calls from the trailing AIMessage and execute each tool sequentially on the current thread
        messages = state_or_input.get("messages", [])
        last_ai = messages[-1] if messages else None
        tool_calls = getattr(last_ai, "tool_calls", None) or []
        tools_by_name = getattr(node, "tools_by_name", {})
        fallback_outputs: list[ToolMessage] = []
        for tc in tool_calls:
            tc_name = tc.get("name", "unknown")
            tc_id = tc.get("id") or "fallback_call"
            tc_args = tc.get("args") or {}
            target_tool = tools_by_name.get(tc_name)
            if target_tool is None:
                fallback_outputs.append(
                    ToolMessage(
                        content=f"Error: Tool '{tc_name}' is not registered with ToolNode.",
                        name=tc_name,
                        tool_call_id=tc_id,
                        status="error",
                    )
                )
                continue
            try:
                # Invoke the StructuredTool directly on the current OS thread without spawning a Future
                raw_out = target_tool.invoke(tc_args)
                content_str = raw_out if isinstance(raw_out, str) else str(raw_out)
                fallback_outputs.append(
                    ToolMessage(content=content_str, name=tc_name, tool_call_id=tc_id)
                )
            except Exception as tool_exc:
                fallback_outputs.append(
                    ToolMessage(
                        content=f"Error executing {tc_name}: {tool_exc}",
                        name=tc_name,
                        tool_call_id=tc_id,
                        status="error",
                    )
                )
        return {"messages": fallback_outputs}
    finally:
        reset_instruction_batch_id(batch_token)
