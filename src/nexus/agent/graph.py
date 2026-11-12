"""
graph.py — Universal NexusAgent LangGraph Implementation.

Rather than partitioning intelligence across rigid domain packages (router/, career/, librarian/)
or restricting directory access, Nexus runs ONE universal agent design (`NexusAgent`) that:
  1. Injects `Vault/Master Instructions.md` (`inject_root_instructions()`) dynamically before every LLM call
     (pre-hydrated with `{vault_structure}`, `{shared_tools}`, `{current_time}`, and `{user_name}`).
  2. Navigates any Vault section directly (`get_directory_structure`, `read_file`, `search_vault`,
     `get_recent_modifications`) and reads `<Section>/Section Instructions.md` on demand.
  3. Surgically modifies existing Vault notes via `modify_file(file_path, target, replacement, reasoning)`,
     creates new notes via `create_file`, moves notes via `move_file`, and deletes notes via `delete_file`,
     staging all changes to the SQLite HITL queue (`hitl.db`).
  4. Spawns isolated subagents via `spawn_subagent(task_prompt: str)` for parallel or deep subtasks,
     where each subagent inherits `inject_root_instructions()` and the core tool suite.
  5. Preserves 100% lossless event-bounded conversation history without message-pruning summarization,
     maximizing provider KV prompt-cache hit rates (90–97% cached tokens) across multi-turn sessions.
"""
# sqlite3: Standard library SQL engine used for local thread checkpointing (`SqliteSaver`)
import json
# re: Regular expressions used to parse provider error payloads (e.g. `retryDelay` intervals on 429)
import re
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
from nexus.core.blackboard import post_bulletin
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import (
    get_hitl_execution_context,
    reset_hitl_execution_context,
    set_hitl_execution_context,
)
from nexus.core.trace import (
    RESULT_TRUNCATE_LEN,
    AgentTracer,
    _truncate,
    reset_trace_thread_id,
    set_trace_thread_id,
)
from nexus.shared_tools.shared import (
    create_calendar_event,
    create_file,
    delete_file,
    fetch_emails,
    get_calendar_schedule,
    get_directory_structure,
    get_recent_modifications,
    get_vault_structure,
    list_browser_tabs,
    modify_file,
    move_file,
    post_to_board,
    read_board,
    read_browser_tabs,
    read_file,
    run_shared_tool_cli,
    search_vault,
    search_web,
    send_telegram_notification,
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


# ── Thread Cancellation Registry & Checkpoint Rollback (Stop & Revert) ───────
MEMORY_DB_PATH = Path(__file__).parent / "memory.sqlite"

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


def get_latest_checkpoint_id(thread_id: str) -> Optional[str]:
    """Returns the most recent checkpoint_id for a given thread_id in `memory.sqlite`, or None if none exists."""
    if not thread_id or not MEMORY_DB_PATH.exists():
        return None
    try:
        with sqlite3.connect(MEMORY_DB_PATH, timeout=30.0) as check_conn:
            check_conn.execute("PRAGMA journal_mode=WAL;")
            check_conn.execute("PRAGMA busy_timeout=30000;")
            cursor = check_conn.cursor()
            cursor.execute(
                "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC LIMIT 1",
                (thread_id,),
            )
            row = cursor.fetchone()
            return str(row[0]) if row else None
    except Exception:
        return None


def rollback_checkpoints_for_thread(thread_id: str, pre_turn_checkpoint_id: Optional[str] = None) -> int:
    """Rolls back LangGraph checkpointer SQLite database (`memory.sqlite`) to pre-turn state.

    Ensures that conversation memory in LangGraph does not remember an aborted or reverted turn.

    Parameters:
      thread_id: Unique UUID string identifying the conversation thread.
      pre_turn_checkpoint_id: Optional checkpoint ID captured immediately before this turn ran.

    Returns:
      Number of deleted checkpoint rows.
    """
    if not thread_id or not MEMORY_DB_PATH.exists():
        return 0

    deleted_checkpoints = 0
    with sqlite3.connect(MEMORY_DB_PATH, timeout=30.0) as rollback_conn:
        rollback_conn.execute("PRAGMA journal_mode=WAL;")
        rollback_conn.execute("PRAGMA busy_timeout=30000;")
        cursor = rollback_conn.cursor()

        target_checkpoint_id = pre_turn_checkpoint_id
        if target_checkpoint_id is None:
            # Fallback inspection: find the most recent checkpoint with metadata.source == 'input'
            cursor.execute(
                """
                SELECT checkpoint_id, parent_checkpoint_id, metadata
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY checkpoint_id DESC
                """,
                (thread_id,),
            )
            rows = cursor.fetchall()
            for cid, parent_id, meta_raw in rows:
                try:
                    meta = json.loads(meta_raw) if meta_raw else {}
                except Exception:
                    meta = {}
                if meta.get("source") == "input":
                    target_checkpoint_id = parent_id if parent_id else ""
                    break

        if target_checkpoint_id:
            # Delete channel writes and checkpoints newer than target_checkpoint_id
            cursor.execute(
                "DELETE FROM writes WHERE thread_id = ? AND checkpoint_id > ?",
                (thread_id, target_checkpoint_id),
            )
            cursor.execute(
                "DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id > ?",
                (thread_id, target_checkpoint_id),
            )
            deleted_checkpoints = cursor.rowcount
        else:
            # First turn of the thread or no prior checkpoint exists: prune entire thread from checkpointer
            cursor.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
            cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            deleted_checkpoints = cursor.rowcount

        rollback_conn.commit()

    return deleted_checkpoints


# ── State Schema ─────────────────────────────────────────────────────────────

# TypedDict defining the state container that flows across all nodes in `NexusAgent`
class NexusAgentState(TypedDict):
    """State that flows through the universal NexusAgent graph."""
    # Annotated[Sequence[BaseMessage], add_messages]: Appends newly returned messages into the existing list
    # without mid-conversation pruning so the entire message prefix remains KV-cached by the LLM provider.
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ── Core Tool Set (Shared by Parent NexusAgent and Subagents) ────────────────

# Most-used deterministic tools bound directly so the agent can navigate, read, surgically edit,
# check recent modifications, search the live web, inspect emails/calendar, post/read bulletins on the
# Shared Blackboard, or invoke any other `[CLI]` tool on demand.
CORE_TOOLS = [
    read_file,
    modify_file,
    create_file,
    move_file,
    delete_file,
    get_directory_structure,
    get_vault_structure,
    search_vault,
    get_recent_modifications,
    search_web,
    list_browser_tabs,
    read_browser_tabs,
    fetch_emails,
    get_calendar_schedule,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    post_to_board,
    read_board,
    send_telegram_notification,
    transcribe_media,
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


def _log_token_usage(
    tracer: AgentTracer,
    ai_msg: BaseMessage,
    model_name: Optional[str] = None,
    tier: Optional[str] = None,
) -> dict[str, Any]:
    """Extracts and logs prompt token counts, cached token hits (`cache_read`), output tokens, and estimated USD cost from an AIMessage."""
    usage = getattr(ai_msg, "usage_metadata", None)
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}
    in_tok = int(usage.get("input_tokens", 0) or 0)
    out_tok = int(usage.get("output_tokens", 0) or 0)
    details = usage.get("input_token_details") or {}
    cached_tok = int(details.get("cache_read", 0) or 0) if isinstance(details, dict) else 0
    cost_usd = calculate_token_cost(
        input_tokens=in_tok,
        output_tokens=out_tok,
        cached_tokens=cached_tok,
        model_name=model_name,
        tier=tier,
    )
    if in_tok or out_tok:
        cache_pct = int((cached_tok / in_tok) * 100) if in_tok > 0 else 0
        tracer.info(
            f"Tokens: {in_tok:,} in ({cached_tok:,} cached, {cache_pct}%) | {out_tok:,} out · ~${cost_usd:.4f}",
            data={
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cached_tokens": cached_tok,
                "cache_pct": cache_pct,
                "cost_usd": cost_usd,
                "model_name": model_name,
                "model_tier": tier,
            },
        )
    return {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cached_tokens": cached_tok,
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
# `model_name: str` is the active model identifier (e.g. `'gemini-3.8-flash'`) displayed in telemetry.
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
    """Invoke an LLM with automatic 429 rate-limit backoff and sliding token-window rollover handling.

    Why this wrapper exists:
    LangChain's default HTTP retry policies use short 1s–4s exponential backoffs intended for network blips.
    When parallel subagents burst token velocity past provider minute-level ceilings (e.g. 2M TPM on Tier 1),
    immediate retries burn all retry attempts while the sliding window remains saturated. This wrapper intercepts
    429/RESOURCE_EXHAUSTED errors, extracts the exact `retryDelay` required for the sliding window to clear,
    notifies the user via SSE trace events, cooperatively sleeps, and seamlessly retries the invocation.
    """
    last_exception: Exception | None = None
    for attempt in range(max_retries + 1):
        # Pre-inference cancellation check: abort immediately if user pressed Stop & Revert
        for tid in thread_ids:
            if tid and is_thread_cancelled(tid):
                raise InterruptedError(f"Turn execution for thread '{tid}' stopped by user.")

        try:
            return llm.invoke(messages)
        except Exception as e:
            last_exception = e
            err_msg_lower = str(e).lower()

            # Dynamic Sampling Parameter Self-Healing:
            # Newer frontier models (such as Claude Opus 5.5) deprecate custom temperature/sampling controls and return HTTP 400
            # (`temperature is deprecated for this model`). If encountered, strip the temperature attribute from the active client
            # (handling both direct BaseChatModel instances and tool-bound RunnableBinding instances) and retry immediately.
            if "temperature" in err_msg_lower and ("deprecated" in err_msg_lower or "not supported" in err_msg_lower):
                has_cleared_temp = False
                if hasattr(llm, "temperature") and getattr(llm, "temperature", None) is not None:
                    llm.temperature = None
                    has_cleared_temp = True
                if hasattr(llm, "bound") and hasattr(llm.bound, "temperature") and getattr(llm.bound, "temperature", None) is not None:
                    llm.bound.temperature = None
                    has_cleared_temp = True
                if has_cleared_temp:
                    tracer.info(
                        f"ℹ️ Model '{model_name}' deprecated custom temperature sampling. Cleared temperature parameter and retrying...",
                        data={"model": model_name, "model_tier": tier},
                    )
                    continue

            # Only intercept rate-limit / quota errors for backoff; let 504 timeouts and logic errors propagate
            if _is_rate_limit_error(e) and attempt < max_retries:
                delay = _extract_retry_delay(e, attempt=attempt)
                tracer.info(
                    f"⏳ Rate limit reached (429 RESOURCE_EXHAUSTED). Waiting {delay:.1f}s for sliding token window rollover "
                    f"before automatic retry (attempt {attempt + 1}/{max_retries})...",
                    data={
                        "model": model_name,
                        "model_tier": tier,
                        "retry_delay": delay,
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                    },
                )
                _cooperative_sleep(delay, thread_ids)
                continue
            raise e

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected failure in _invoke_llm_with_resilience")


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
    # Propagate conversation_id from parent while scoping thread_id, agent_id, and agent_role to this subagent
    parent_ctx = get_hitl_execution_context()
    parent_convo = parent_ctx.get("conversation_id") or "nexus_primary"
    parent_thread = parent_ctx.get("thread_id") or parent_convo

    # Match the parent turn's provider when chatting on Anthropic (e.g. `"anthropic:low"` -> `claude-sonnet-4-5`)
    # Scoped strictly to parent_convo so parallel swarms on different provider families never cross-contaminate
    parent_provider = get_active_turn_provider(parent_convo)
    sub_tier_arg = f"anthropic:{effective_tier}" if parent_provider == "anthropic" else effective_tier
    sub_resolved = resolve_model_config(sub_tier_arg)
    sub_model_name = sub_resolved["model_name"]

    serial, sub_id, local_tracer = _next_subagent_tracer(effective_tier, thread_id=parent_convo)
    t0 = time.time()

    # Scope trace context variable so all subagent events and tool calls inherit the conversation UUID
    trace_token = set_trace_thread_id(parent_convo)

    # Emit full, untruncated task_prompt so the Thinking Panel, Graph View, and Run Logs capture 100% of the prompt
    local_tracer.agent_start(
        f"Subtask #{serial} ({effective_tier} · {sub_model_name}): {task_prompt}",
        metadata={
            "serial": serial,
            "subagent_id": sub_id,
            "thread_id": parent_convo,
            "model_tier": effective_tier,
            "model_name": sub_model_name,
            "task_prompt": task_prompt,
        },
    )

    # Build an ephemeral, stateless subagent client (no checkpointer needed; lives only for this subtask)
    sub_base_llm = get_chat_model(tier=sub_tier_arg, temperature=0.0)
    sub_llm = sub_base_llm.bind_tools(CORE_TOOLS)
    # handle_tool_errors=True: Prebuilt LangGraph handler that intercepts unhandled tool exceptions
    # (e.g. HttpError 404/500, network disconnects, file locks) and wraps them into a ToolMessage(status="error")
    # rather than raising through ToolNode.invoke() and terminating the subagent turn mid-flight.
    sub_tool_node = ToolNode(CORE_TOOLS, handle_tool_errors=True)

    sub_sys_content = (
        inject_root_instructions()
        + "\n\n# Subagent Execution Mode\n"
        + f"You are an isolated Flash subagent (Subagent #{serial}) spawned by the parent NexusAgent (Astra) to execute the specific task below. "
        + "Read any relevant `Section Instructions.md` and Vault notes needed, execute the task thoroughly, "
        + "and return a concise, high-signal, grounded synthesis to the parent agent. "
        + "Your final synthesis will automatically be published to the Shared Agent Blackboard (`blackboard.db`), "
        + "or you may explicitly call `post_to_board(title, content, author)` to post structured bulletins."
    )

    # Run ReAct loop until the subagent finishes tool calls and returns its synthesis
    sub_messages: list[BaseMessage] = [
        SystemMessage(content=sub_sys_content),
        HumanMessage(content=task_prompt),
    ]
    posted_to_board = False
    turn_idx = 0

    sub_thread_id = f"{parent_thread}:{sub_id}" if parent_thread else sub_id
    sub_ctx_token = set_hitl_execution_context(
        conversation_id=parent_convo,
        thread_id=sub_thread_id,
        agent_id=sub_id,
        agent_role=f"Subagent #{serial} ({effective_tier})",
    )

    try:
        while True:
            # Cancellation guard: abort subagent immediately if the parent turn was stopped by user
            if is_thread_cancelled(parent_convo) or is_thread_cancelled(parent_thread):
                raise InterruptedError(f"Subagent #{serial} execution stopped by user via Stop & Revert.")

            turn_idx += 1
            local_tracer.llm_call(metadata={"turn": turn_idx, "model_tier": effective_tier, "model_name": sub_model_name})
            ai_msg = _invoke_llm_with_resilience(
                llm=sub_llm,
                messages=sub_messages,
                tracer=local_tracer,
                thread_ids=[parent_convo, parent_thread, sub_id],
                model_name=sub_model_name,
                tier=effective_tier,
                max_retries=settings.ai_max_retries,
            )
            _log_token_usage(local_tracer, ai_msg, model_name=sub_model_name, tier=effective_tier)
            sub_messages.append(ai_msg)

            if not getattr(ai_msg, "tool_calls", None):
                final_text = extract_message_text(ai_msg)
                elapsed_sub = round(time.time() - t0, 2)
                # Automatically publish the subagent's distilled report onto the Shared Blackboard if not already posted
                if final_text.strip() and not posted_to_board:
                    first_line = task_prompt.strip().splitlines()[0][:120]
                    bulletin_id = post_bulletin(
                        author=f"Subagent #{serial} ({effective_tier})",
                        title=first_line,
                        content=final_text,
                        thread_id=parent_convo,
                    )
                    local_tracer.info(
                        f"📋 Posted Bulletin #{bulletin_id} to Blackboard",
                        data={"bulletin_id": bulletin_id, "title": first_line},
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

            tool_res = _invoke_tool_node_resilient(sub_tool_node, {"messages": sub_messages})
            for t_msg in tool_res.get("messages", []):
                t_name = getattr(t_msg, "name", "unknown")
                t_call_id = getattr(t_msg, "tool_call_id", None)
                t_content = extract_message_text(t_msg)
                local_tracer.tool_result(t_name, t_content, call_id=t_call_id)
                sub_messages.append(t_msg)
    finally:
        reset_hitl_execution_context(sub_ctx_token)
        reset_trace_thread_id(trace_token)


# ── Helper: Resilient ToolNode Execution with Synchronous In-Thread Fallback ─

# `node: ToolNode` is the LangGraph tool runner (`sub_tool_node` for subagents or `tool_node` for the parent agent).
# `state_or_input: dict[str, Any]` is the state dict containing `"messages"` whose trailing `AIMessage` holds `tool_calls`.
# `-> dict[str, Any]` returns `{"messages": [ToolMessage, ...]}` matching `ToolNode.invoke()` output shape.
def _invoke_tool_node_resilient(node: ToolNode, state_or_input: dict[str, Any]) -> dict[str, Any]:
    """Execute a LangGraph `ToolNode` with an automatic synchronous in-thread fallback if the thread pool is shut down.

    Why this safeguard exists:
    `ToolNode.invoke()` always dispatches tool calls through `ContextThreadPoolExecutor` (`concurrent.futures.ThreadPoolExecutor`).
    When `uvicorn --reload` detects a `.py` file edit and initiates worker shutdown, Python's `threading._register_atexit(_python_exit)`
    flags active `ThreadPoolExecutor` instances as `_shutdown = True` before daemon request threads finish.
    Any subsequent `ToolNode.invoke()` call raises `RuntimeError('cannot schedule new futures after shutdown')`.
    Catching that specific executor shutdown error and running the requested `@tool` callables sequentially on the current
    thread allows synchronous tools (`read_file`, `search_vault`, `modify_file`) to complete cleanly instead of crashing mid-turn.
    """
    try:
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


# ── Parent Agent Tool & Model Binding ────────────────────────────────────────

# The parent NexusAgent gets all core tools plus `spawn_subagent`
TOOLS = CORE_TOOLS + [spawn_subagent]
# handle_tool_errors=True catches unhandled tool exceptions across all parent tools (including spawn_subagent)
# and returns an error ToolMessage to the model so the agent can gracefully recover, retry, or report to the user.
tool_node = ToolNode(TOOLS, handle_tool_errors=True)

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

    # Record active provider scoped to active_convo_id so parallel subagents match their exact turn's provider family
    set_active_turn_provider(active_provider, thread_id=active_convo_id)
    global _active_turn_provider
    _active_turn_provider = active_provider

    # Resolve `get_chat_model(tier=requested_tier)` dynamically on each turn so UI model switches and `.env` edits apply immediately
    nexus_tracer.llm_call(metadata={"model_tier": effective_tier, "model_name": active_model_name})
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
        # low-latency tier (`gemini-3.8-flash` / `claude-sonnet-4-5` / `low`) to preserve the user's conversation session without crashing.
        if is_deadline_or_timeout and effective_tier != "low":
            fallback_tier_arg = "anthropic:low" if active_provider == "anthropic" else "low"
            fallback_resolved = resolve_model_config(fallback_tier_arg)
            nexus_tracer.info(
                f"⚠️ Primary model tier ({effective_tier} · {active_model_name}) exceeded deadline (504 DEADLINE_EXCEEDED). "
                f"Gracefully falling back to low-latency tier ({fallback_resolved['model_name']}) to complete the turn..."
            )
            fallback_llm = get_chat_model(tier=fallback_tier_arg, temperature=0.0)
            response = _invoke_llm_with_resilience(
                llm=fallback_llm.bind_tools(TOOLS),
                messages=messages_for_llm,
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

    result = _invoke_tool_node_resilient(tool_node, state)
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        call_id = getattr(msg, "tool_call_id", None)
        content = extract_message_text(msg)
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

# 3. Persistent Checkpointer: Co-located SQLite database for multi-turn conversation state
# `check_same_thread=False` allows FastAPI background worker threads to share the SQLite connection safely
# `timeout=30.0` and Write-Ahead Logging (WAL) enable concurrent readers without blocking checkpoint writes
db_path = MEMORY_DB_PATH
conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=30000;")
memory = SqliteSaver(conn)

# 4. Compile into executable stateful LangGraph runnable
nexus_graph = workflow.compile(checkpointer=memory)
