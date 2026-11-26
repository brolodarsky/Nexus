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
  4. Spawns isolated subagents via `spawn_subagent(task_prompt: str)` for parallel or deep subtasks,
     where each subagent inherits `inject_root_instructions()` and the core tool suite.
  5. Preserves 100% lossless event-bounded conversation history without message-pruning summarization,
     sustaining high provider KV prompt-cache hit rates (83.5% across 748 measured runs; 90–95% on static prefixes).
"""
# contextvars: Propagates active thread_id and HITL execution context across timeout wrapper threads
import contextvars
# concurrent.futures: Enables bounded wall-clock timeouts on tool batches without blocking on hung sockets
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
# re: Regular expressions used to parse provider error payloads (e.g. `retryDelay` intervals on 429)
import re
# threading: Provides thread-safe locking (`Lock`) for assigning unique serial numbers to parallel subagents
import threading
import time
import uuid
from pathlib import Path
# Typing primitives:
# - TypedDict: Enforces key-value types for the LangGraph state dictionary
# - Annotated: Attaches reducer metadata (`add_messages`) to state keys
# - Sequence: Immutable ordered sequence of LangChain `BaseMessage` objects
# - Literal: Constrains conditional edge return strings to an explicit set of node names
from typing import Annotated, Any, Literal, Optional, Sequence, TypedDict

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
from nexus.core.context_telemetry import (
    build_llm_call_manifest,
    build_subagent_start_manifest,
)
from nexus.core.cost import calculate_token_cost
from nexus.core.constants import (
    AI_MODEL_LOW,
    AI_MODEL_MEDIUM,
    VAULT_PATH,
    ModelTier,
    get_chat_model,
    resolve_model_config,
)
# inject_root_instructions: Dynamically loads and hydrates `Vault/Master Instructions.md` (<1ms disk read)
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import (
    get_hitl_execution_context,
    reset_hitl_execution_context,
    set_hitl_execution_context,
)
from nexus.core.instruction_guard import (
    clear_seen_instructions,
    reset_instruction_batch_id,
    set_instruction_batch_id,
)
from nexus.core.trace import (
    RESULT_TRUNCATE_LEN,
    AgentTracer,
    _truncate,
    get_trace_run_id,
    reset_trace_thread_id,
    set_trace_thread_id,
)
from nexus.shared_tools.shared import (
    create_calendar_event,
    create_file,
    delete_file,
    fetch_emails,
    fill_browser_form,
    get_calendar_schedule,
    get_directory_structure,
    get_recent_modifications,
    hydrate_subagent_context_files,
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
    delete_calendar_event,
)

# ── Agent Tracers & Subagent Serial Counter ──────────────────────────────────

# Cyan console logger and SSE event emitter for the primary Head Agent (root node `agent_id="nexus"`)
nexus_tracer = AgentTracer("Head Agent", color="cyan", agent_id="nexus", parent_id=None)
# Default magenta tracer kept for backward-compatible module imports; individual subagents instantiate their own serial-numbered AgentTracer
subagent_tracer = AgentTracer("Subagent", color="magenta", agent_id="subagent", parent_id="nexus")

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


# ── State Schema ─────────────────────────────────────────────────────────────

# TypedDict defining the state container that flows across all nodes in `NexusAgent`
class NexusAgentState(TypedDict):
    """State that flows through the universal NexusAgent graph."""
    # Annotated[Sequence[BaseMessage], add_messages]: Appends newly returned messages into the existing list
    # without mid-conversation pruning so the entire message prefix remains KV-cached by the LLM provider.
    messages: Annotated[Sequence[BaseMessage], add_messages]


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


# `msg: BaseMessage | None` is a LangChain message (typically an `AIMessage` returned by Gemini or Anthropic).
# `-> str` returns concatenated readable thinking/reasoning summaries without mutating `msg` or its signatures.
def extract_message_thinking(msg: BaseMessage | None) -> str:
    """Extract readable model thinking/reasoning text from an `AIMessage` without mutating persisted state.

    Supports:
    - Anthropic & Gemini structured content blocks (`{'type': 'thinking', 'thinking': '...'}`).
    - Reasoning/summary blocks (`{'type': 'reasoning'|'reasoning_content', 'reasoning'|'summary'|'text': ...}`).
    - Legacy provider `additional_kwargs['reasoning_content']` strings.

    Never mutates `msg.content` or strips cryptographic signatures so `SqliteSaver` and KV caches stay intact.
    """
    if msg is None:
        return ""
    parts: list[str] = []
    raw_content = getattr(msg, "content", None)

    if isinstance(raw_content, list):
        for block in raw_content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "thinking":
                thought_val = block.get("thinking")
                if not isinstance(thought_val, str) or not thought_val.strip():
                    thought_val = block.get("text")
                if isinstance(thought_val, str) and thought_val.strip():
                    parts.append(thought_val.strip())
            elif btype in ("reasoning", "reasoning_content"):
                # Inspect flat string fields first, then OpenAI-style `summary` lists
                for key in ("reasoning", "reasoning_content", "text"):
                    val = block.get(key)
                    if isinstance(val, str) and val.strip():
                        parts.append(val.strip())
                        break
                summary_items = block.get("summary")
                if isinstance(summary_items, list):
                    for item in summary_items:
                        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                            parts.append(item["text"].strip())

    if not parts:
        ak = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(ak, dict):
            rc = ak.get("reasoning_content")
            if isinstance(rc, str) and rc.strip():
                parts.append(rc.strip())

    return "\n\n".join(parts)


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
    """Spawn an isolated subagent to execute a focused research, audit, or synthesis subtask.

    PARALLEL SWARMING: Emitting multiple `spawn_subagent` tool calls in a single turn executes all
    subagents concurrently in parallel via the runtime thread pool (`ToolNode`). Use parallel fan-out
    whenever inspecting multiple files, auditing multiple sections, or running independent subtasks so
    raw file contents stay out of your primary context window.

    PRE-HYDRATED DISK & CACHE CONTEXT (`context_files`):
    Never summarize user credentials, degrees, section rules, or captured webpages/emails from memory into `task_prompt`!
    Pass shared baseline Vault paths/titles (e.g. `["3. Operations/3.1. Career Strategy & Revenue/Section Instructions.md", "Resume - Master.md"]`)
    AND/OR per-conversation external capture keys (`"cache://tab/<slug>"`, `"cache://web/<slug>"`, `"cache://email/<id>"`, `"cache://"` manifest, or cached URLs)
    via `context_files`. Python resolves them directly (zero Commander context bloat, zero extra subagent tool turns)
    and prepends `# Pre-Hydrated Disk Context` to the subagent's initial prompt.
    Governing ancestor `Section Instructions.md` files referenced by `context_files` or `task_prompt` are also discovered and pre-hydrated automatically.
    If any path or cache key cannot be resolved, `spawn_subagent` fails fast before calling the LLM
    and surfaces actual sibling files or available `cache://` keys in this conversation.

    ARCHITECT-DRAFTER PATTERN (WRITING & EDIT DELEGATION):
    Subagents are not just for reading; they are your execution workforce. When multiple notes need to be created
    or surgically modified, do NOT pull full note bodies into your primary window to execute `modify_file` yourself.
    Instead, decide the architecture and strategy as the Commander, and instruct the subagent exactly what to write:
    provide the target note path, the exact replacement guidelines or markdown blocks, and instruct it to call
    `modify_file` or `create_file` to stage the changes to the HITL queue. The subagent absorbs the raw file contents,
    executes the tool loop, and returns only a concise confirmation receipt (Transaction ID and summary) to your context.

    The subagent boots automatically with `inject_root_instructions()` (`Master Instructions.md` +
    `{vault_structure}` + `{shared_tools}`) and has full access to all Vault navigation, reading,
    search, HITL file tools, and `spawn_conversation` (when instructed to spin up seeded discussion
    threads directly from raw tool payloads without dumping them back into the Commander window).
    Make `task_prompt` self-contained, specific, and crystal clear:
      1. State the exact objective and which Vault section(s) or note(s) to inspect (plus `context_files` for shared baseline notes).
      2. Specify any constraints (e.g. read-only vs. staging a surgical edit via `modify_file`).
      3. Specify the exact output format and distilled takeaways to return to you.

    Args:
        task_prompt: A clear, self-contained, actionable prompt instructing the subagent what to do and return.
        model_tier: Capability/cost tier (`"low"`, `"medium"`, or `"strong"`). Defaults to `"low"` for fast,
                    cost-efficient execution; pass `"medium"` or `"strong"` only for complex synthesis subtasks.
        context_files: Optional list of Vault-relative paths, unique note titles, or `cache://...` capture handles/URLs
                       to pre-hydrate directly under `# Pre-Hydrated Disk Context` (fails fast if any ref cannot be resolved).
    """
    effective_tier: ModelTier = model_tier if model_tier in ("low", "medium", "strong") else "low"
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
            "2. **Batch Tool Calls:** Emit all independent `search_vault`, `read_file`, `get_directory_structure`, and `fetch_emails` calls in parallel in the same turn rather than one lookup per turn. Use `search_vault(keywords=[...])` for multi-term Vault searches, and use `start_line`/`end_line` slices on large notes when full files are unnecessary.\n"
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
                max_retries=settings.ai_max_retries,
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
                    max_retries=settings.ai_max_retries,
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
                        max_retries=settings.ai_max_retries,
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


# ── Parent Agent Tool & Model Binding ────────────────────────────────────────

# The parent NexusAgent gets all core tools plus `spawn_subagent`
TOOLS = CORE_TOOLS + [spawn_subagent]
# handle_tool_errors=True catches unhandled tool exceptions across all parent tools (including spawn_subagent)
# and returns an error ToolMessage to the model so the agent can gracefully recover, retry, or report to the user.
tool_node = ToolNode(TOOLS, handle_tool_errors=True)

# Primary reasoning model resolved via `get_chat_model` (uses Gemini 4 Argon/Hydrogen when GEMINI_API_KEY is set, else OpenAI tier)
_primary_tier: ModelTier = (
    settings.nexus_primary_tier if settings.nexus_primary_tier in ("low", "medium", "strong") else "medium"
)
llm = get_chat_model(tier=_primary_tier, temperature=0.0)
llm_with_tools = llm.bind_tools(TOOLS)


# ── Helper: Cross-Provider Thought & Signature Isolation ─────────────────────

# frozenset: Immutable set of provider-specific content block types that carry thinking payloads, cryptographic
# signatures, or Anthropic-native tool envelopes (`tool_use`) which must not leak across provider families.
_FOREIGN_BLOCK_TYPES = frozenset({
    "thinking",
    "redacted_thinking",
    "reasoning",
    "reasoning_content",
    "tool_use",
    "server_tool_use",
    "mcp_tool_use",
})


# `provider: Optional[str]` is a raw provider identifier from `AIMessage.response_metadata["model_provider"]` or config.
# `-> Optional[str]` maps LangChain provider strings to canonical Nexus keys (`"gemini"`, `"anthropic"`, `"openai"`).
def _normalize_provider_name(provider: Optional[str]) -> Optional[str]:
    """Normalize provider metadata strings across LangChain integrations into canonical provider keys."""
    if not provider:
        return None
    norm = str(provider).strip().lower()
    if norm in ("google_genai", "google_vertexai", "google", "gemini"):
        return "gemini"
    if norm == "anthropic":
        return "anthropic"
    if norm == "openai":
        return "openai"
    return None


# `msg: BaseMessage` is any message in LangGraph conversation history.
# `-> Optional[str]` infers the originating provider (`"gemini"`, `"anthropic"`, `"openai"`) for `AIMessage`s, or None.
def _infer_message_provider(msg: BaseMessage) -> Optional[str]:
    """Infer which LLM provider produced an `AIMessage` using metadata first, then structural block signatures."""
    if not isinstance(msg, AIMessage):
        return None

    # 1. Explicit `model_provider` recorded by LangChain (`"google_genai"`, `"anthropic"`, `"openai"`)
    rm = getattr(msg, "response_metadata", None) or {}
    norm = _normalize_provider_name(rm.get("model_provider"))
    if norm:
        return norm

    # 2. Fallback to model name substrings when older checkpoints omitted `model_provider`
    model_name = str(rm.get("model_name") or rm.get("model") or "").strip().lower()
    if model_name:
        if any(tok in model_name for tok in ("gemini", "argon", "hydrogen")):
            return "gemini"
        if any(tok in model_name for tok in ("claude", "opus", "sonnet", "haiku")):
            return "anthropic"
        if any(tok in model_name for tok in ("gpt", "o1", "o3", "o4")):
            return "openai"

    # 3. Structural marker fallback for checkpoints lacking `response_metadata`
    ak = getattr(msg, "additional_kwargs", None) or {}
    if "__gemini_function_call_thought_signatures__" in ak:
        return "gemini"

    if isinstance(msg.content, list):
        for block in msg.content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype in ("redacted_thinking", "tool_use", "server_tool_use", "mcp_tool_use"):
                return "anthropic"
            if btype == "text":
                extras = block.get("extras")
                if isinstance(extras, dict) and ("signature" in extras or "thought_signature" in extras):
                    return "gemini"

    return None


# `msg: AIMessage` is a historical assistant message in thread state.
# `-> bool` returns True if `msg` contains provider-bound thinking blocks, signatures, or native tool_use blocks.
def _has_provider_thought_artifacts(msg: AIMessage) -> bool:
    """Check whether an `AIMessage` carries provider-specific thought blocks or cryptographic signatures."""
    ak = getattr(msg, "additional_kwargs", None) or {}
    if "__gemini_function_call_thought_signatures__" in ak or "thought_signature" in ak:
        return True

    if isinstance(msg.content, list):
        for block in msg.content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in _FOREIGN_BLOCK_TYPES:
                return True
            if any(k in block for k in ("signature", "thought_signature", "cache_control")):
                return True
            extras = block.get("extras")
            if isinstance(extras, dict) and ("signature" in extras or "thought_signature" in extras):
                return True

    return False


# `msg: AIMessage` is a foreign-provider (or rejected-signature) assistant message.
# `-> AIMessage` returns an ephemeral `model_copy` stripped of thought/signature metadata while leaving `msg` unmutated.
def _strip_ai_message_thought_artifacts(msg: AIMessage) -> AIMessage:
    """Create an ephemeral copy of `msg` with cross-provider thinking/signature blocks and tool envelopes removed.

    Why `model_copy` instead of mutating `msg` in place:
    `SqliteSaver` checkpoints hold references to historical `AIMessage` objects. Mutating them in place would
    corrupt persisted Anthropic/Gemini signatures if the user later switches back to the original provider.
    Tool call invocations (`msg.tool_calls`) and plain conversational text are preserved intact.
    """
    has_tool_calls = bool(getattr(msg, "tool_calls", None))
    new_content: Any = msg.content

    if isinstance(msg.content, list):
        cleaned_blocks: list[Any] = []
        for block in msg.content:
            if isinstance(block, str):
                cleaned_blocks.append(block)
            elif isinstance(block, dict):
                # Drop thinking/reasoning blocks and provider-specific tool_use wrappers (`msg.tool_calls` retains calls)
                if block.get("type") in _FOREIGN_BLOCK_TYPES:
                    continue
                b_copy = dict(block)
                b_copy.pop("signature", None)
                b_copy.pop("thought_signature", None)
                b_copy.pop("cache_control", None)
                if isinstance(b_copy.get("extras"), dict):
                    ex = dict(b_copy["extras"])
                    ex.pop("signature", None)
                    ex.pop("thought_signature", None)
                    if ex:
                        b_copy["extras"] = ex
                    else:
                        b_copy.pop("extras", None)
                cleaned_blocks.append(b_copy)
            else:
                cleaned_blocks.append(block)

        # Collapse pure-text (or empty) block lists to a plain string so neither Gemini (`parts=[]`)
        # nor Anthropic (whitespace-only text blocks) rejects empty content turns.
        only_text_or_empty = all(
            isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "text")
            for b in cleaned_blocks
        )
        if only_text_or_empty:
            non_empty_texts = [
                t for t in (
                    b if isinstance(b, str) else str(b.get("text", ""))
                    for b in cleaned_blocks
                )
                if t and t.strip()
            ]
            if non_empty_texts:
                new_content = "\n".join(non_empty_texts)
            else:
                new_content = "" if has_tool_calls else "(no text)"
        else:
            # Non-text blocks (e.g. multimodal image/file blocks) survive: prune blank text dicts only
            filtered_blocks = [
                b for b in cleaned_blocks
                if not (isinstance(b, dict) and b.get("type") == "text" and not str(b.get("text", "")).strip())
            ]
            new_content = filtered_blocks if filtered_blocks else ("" if has_tool_calls else "(no text)")
    elif isinstance(new_content, str) and not new_content.strip() and not has_tool_calls:
        new_content = "(no text)"

    # Shallow-copy `additional_kwargs` and remove Gemini/provider signature keys (plus redundant `function_call`)
    new_ak = dict(getattr(msg, "additional_kwargs", None) or {})
    new_ak.pop("__gemini_function_call_thought_signatures__", None)
    new_ak.pop("thought_signature", None)
    if has_tool_calls:
        new_ak.pop("function_call", None)

    # Shallow-copy `response_metadata` and strip `output_version` so v1 block unpackers do not re-run on cleaned text
    new_rm = dict(getattr(msg, "response_metadata", None) or {})
    new_rm.pop("output_version", None)

    return msg.model_copy(
        update={
            "content": new_content,
            "additional_kwargs": new_ak,
            "response_metadata": new_rm,
        }
    )


# `messages: Sequence[BaseMessage]` is the turn-ordered conversation history from `_sanitize_messages()`.
# `target_provider: str` is the destination provider key (`"gemini"`, `"anthropic"`, `"openai"`).
# `strip_all_signatures: bool = False` forces stripping across ALL `AIMessage`s (used by reactive 400 recovery).
# `-> list[BaseMessage]` returns a list safe for the target provider, preserving same-provider message identity.
def _sanitize_messages_for_provider(
    messages: Sequence[BaseMessage],
    target_provider: str,
    *,
    strip_all_signatures: bool = False,
) -> list[BaseMessage]:
    """Strip foreign-provider thinking blocks and thought signatures before cross-provider model invocation.

    Preserves exact object identity (`msg` untouched) whenever a message originates from `target_provider`,
    guaranteeing zero KV prompt-cache prefix churn on single-provider conversations (e.g. Gemini -> Gemini
    or Anthropic -> Anthropic), while preventing `400 INVALID_THOUGHT_SIGNATURE` / `ValueError` crashes when
    switching models mid-thread (e.g. Claude Opus -> Gemini Flash).
    """
    norm_target = _normalize_provider_name(target_provider)
    result: list[BaseMessage] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            result.append(msg)
            continue

        if strip_all_signatures:
            result.append(
                _strip_ai_message_thought_artifacts(msg)
                if _has_provider_thought_artifacts(msg)
                else msg
            )
            continue

        src_provider = _infer_message_provider(msg)
        if src_provider is not None and src_provider == norm_target:
            # Same provider: preserve cryptographic signatures and original object identity for KV caching
            result.append(msg)
        elif _has_provider_thought_artifacts(msg):
            # Foreign or unattributed message carrying provider signatures/thinking blocks: strip ephemerally
            result.append(_strip_ai_message_thought_artifacts(msg))
        else:
            result.append(msg)

    return result


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
    global _active_turn_provider
    _active_turn_provider = active_provider

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


# ── Graph Assembly & SQLite Checkpointer ─────────────────────────────────────

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
