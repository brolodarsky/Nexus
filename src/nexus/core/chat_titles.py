"""
chat_titles.py — Thread-Safe Conversation Auto-Titling Service for the Nexus Engine.

Centralizes AI conversation title generation across the FastAPI Web UI, SSE streaming worker,
and Telegram mobile bridge with:
  1. Per-conversation in-flight deduplication (`_inflight_titles` + `threading.Lock` / `threading.Event`),
     preventing duplicate LLM calls when multiple clients or polling watchdogs request a title concurrently.
  2. Non-blocking async execution (`asyncio.to_thread` for SQLite I/O + `chat_model.ainvoke` for HTTP routes)
     and a bounded background `ThreadPoolExecutor` (`schedule_auto_title`) for server-side Turn-1 titling.
  3. Atomic Compare-and-Swap (`expected_title` + `only_if_placeholder`) writes in SQLite `chats.db` so
     background auto-titling never overwrites a user's manual title edit.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from typing import Any

import nexus.core.chats_db as chats_db
from nexus.core.chats_db import (
    get_chat_history,
    get_conversation,
    update_conversation_title,
)
from nexus.core.logger import logger

# Bounded worker pool for fire-and-forget Turn-1 auto-titling so burst completions never spawn unbounded OS threads
_TITLE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="nexus-auto-title")

# _inflight_lock: Mutex guarding `_inflight_titles` across FastAPI asyncio threads and background workers
_inflight_lock = threading.Lock()
# _inflight_titles: Maps `conversation_id -> {"done_event": Event, "result": dict | None, "error": Exception | None, "force": bool}`
_inflight_titles: dict[str, dict[str, Any]] = {}


def _resolve_prefix(conv: dict[str, Any], explicit_prefix: str = "") -> str:
    """Preserves channel/lineage badges (`📱 ` for Telegram, `🌿 ` for branches) across title updates."""
    if explicit_prefix:
        return explicit_prefix
    initial_title = (conv.get("title") or "").strip()
    if conv.get("parent_conversation_id") or initial_title.startswith("🌿"):
        return "🌿 "
    if initial_title.startswith("📱"):
        return "📱 "
    return ""


def _extract_prompt_and_reply(
    history: list[dict[str, Any]],
    is_branch: bool,
) -> tuple[str | None, str | None]:
    """
    Selects the focal user prompt and assistant excerpt used to summarize a conversation's topic.
    - Root conversations summarize Turn 1 (first user prompt + first assistant reply).
    - Branched conversations skip synthetic `branch_context` briefs and summarize the latest turn if
      new messages were added, avoiding summarizing an ancestor turn from a full-history fork.
    """
    if not history:
        return None, None

    if is_branch:
        # Walk backwards to locate the latest user prompt + following non-brief assistant reply in the branch
        for idx in range(len(history) - 1, -1, -1):
            msg = history[idx]
            if msg.get("role") == "user" and (msg.get("content") or "").strip():
                assistant_reply = next(
                    (
                        m.get("content")
                        for m in history[idx + 1 :]
                        if m.get("role") == "assistant" and m.get("agent") != "branch_context"
                    ),
                    None,
                )
                return msg.get("content"), assistant_reply

    first_user_msg = next(
        (m.get("content") for m in history if m.get("role") == "user" and (m.get("content") or "").strip()),
        None,
    )
    first_assistant_msg = next(
        (
            m.get("content")
            for m in history
            if m.get("role") == "assistant" and m.get("agent") != "branch_context"
        ),
        None,
    )
    return first_user_msg, first_assistant_msg


def _build_title_prompt(user_msg: str, assistant_msg: str | None, *, is_mobile: bool = False) -> str:
    """Constructs a low-token summarization prompt instructing the low-tier model to emit raw 3–6 word text."""
    channel_hint = "mobile voice/text request" if is_mobile else "chat"
    prompt = (
        f"Generate a concise, high-signal, natural conversation title (maximum 3 to 6 words) "
        f"summarizing the topic of this {channel_hint}. Do NOT use quotation marks, ending punctuation, "
        "prefixes like 'Title:', or markdown formatting. Return ONLY the raw title text.\n\n"
        f"User prompt: {user_msg.strip()[:400]}"
    )
    if assistant_msg:
        prompt += f"\nAssistant excerpt: {assistant_msg.strip()[:400]}"
    return prompt


def _clean_generated_title(raw_content: str, prefix: str = "", max_len: int = 60) -> str:
    """Strips LLM quotes, markdown artifacts, and preambles (`Title:`, emoji prefixes), enforcing max length."""
    cleaned = raw_content.strip().strip('"\'`').replace("\n", " ").strip()
    for token in ("Title:", "title:", "Topic:", "topic:", "📱", "🌿"):
        if cleaned.startswith(token):
            cleaned = cleaned[len(token) :].strip()
    cleaned = cleaned.strip('"\'`').strip()
    if not cleaned:
        return ""

    full = f"{prefix}{cleaned}" if prefix else cleaned
    if len(full) > max_len:
        full = full[: max_len - 3].rstrip() + "..."
    return full


def _build_fallback_title(user_msg: str, prefix: str = "", snippet_limit: int = 35) -> str:
    """Formats a deterministic prompt-excerpt fallback title when the LLM call is unavailable."""
    clean_query = " ".join(user_msg.strip().splitlines()).strip()
    snippet = clean_query[:snippet_limit].strip()
    if len(clean_query) > snippet_limit:
        snippet += "..."
    return f"{prefix}{snippet}" if prefix else snippet


def _acquire_inflight_slot(conversation_id: str, *, force: bool) -> tuple[bool, dict[str, Any]]:
    """
    Coordinates per-conversation auto-title exclusivity across concurrent threads and coroutines.

    Returns:
      `(is_owner, entry)`:
      - When `is_owner` is True, the caller owns the active slot and MUST call `_release_inflight_slot` in `finally`.
      - When `is_owner` is False, another worker is already running for `conversation_id`; the caller should
        wait on `entry["done_event"]` instead of issuing a duplicate LLM request.
    """
    while True:
        with _inflight_lock:
            existing = _inflight_titles.get(conversation_id)
            if existing is None:
                entry: dict[str, Any] = {
                    "done_event": threading.Event(),
                    "result": None,
                    "error": None,
                    "force": force,
                }
                _inflight_titles[conversation_id] = entry
                return True, entry
            if not force:
                # Non-forced callers (e.g. automatic UI sync + backend Turn-1 trigger) coalesce onto the active job
                return False, existing
            # A forced caller (`✨` sparkle button) waits outside the lock for the active job to settle, then re-checks
        existing["done_event"].wait(timeout=30.0)


def _release_inflight_slot(
    conversation_id: str,
    entry: dict[str, Any],
    *,
    result: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> None:
    """Publishes the outcome to waiting callers and removes the conversation from `_inflight_titles`."""
    with _inflight_lock:
        entry["result"] = result
        entry["error"] = error
        if _inflight_titles.get(conversation_id) is entry:
            _inflight_titles.pop(conversation_id, None)
        entry["done_event"].set()


def _commit_title_result(
    conversation_id: str,
    final_title: str,
    initial_title: str,
    *,
    source: str,
    force: bool,
) -> dict[str, Any]:
    """Writes `final_title` via atomic Compare-and-Swap so concurrent manual renames are never overwritten."""
    updated = update_conversation_title(
        conversation_id,
        final_title,
        source=source,
        expected_title=initial_title,
        only_if_placeholder=(not force),
    )
    if not updated:
        # Another thread (or a manual user rename during the LLM call) already updated this conversation's title
        latest = get_conversation(conversation_id)
        current_title = (latest or {}).get("title") or initial_title
        return {
            "status": "unchanged",
            "conversation_id": conversation_id,
            "title": current_title,
            "skipped_race": True,
        }
    return {
        "status": "updated",
        "conversation_id": conversation_id,
        "title": final_title,
    }


def auto_generate_title_sync(
    conversation_id: str,
    *,
    force: bool = False,
    prefix: str = "",
    user_query: str | None = None,
    assistant_reply: str | None = None,
) -> dict[str, Any]:
    """
    Synchronously generates and persists a concise 3–6 word AI title for `conversation_id`.
    Safe to invoke from background worker threads and `telegram_bridge.py`.
    """
    is_owner, slot = _acquire_inflight_slot(conversation_id, force=force)
    if not is_owner:
        slot["done_event"].wait(timeout=30.0)
        if slot.get("error") is not None:
            raise slot["error"]
        if slot.get("result") is not None:
            return dict(slot["result"])
        conv = get_conversation(conversation_id)
        return {
            "status": "unchanged",
            "conversation_id": conversation_id,
            "title": (conv or {}).get("title", "New Chat"),
        }

    try:
        conv = get_conversation(conversation_id)
        if not conv:
            raise LookupError(f"Conversation '{conversation_id}' not found.")

        initial_title = conv.get("title") or "New Chat"
        title_source = conv.get("title_source") or "placeholder"

        # Skip automatic titling if the conversation already received an AI or manual title
        if not force and title_source != "placeholder":
            res = {
                "status": "unchanged",
                "conversation_id": conversation_id,
                "title": initial_title,
            }
            _release_inflight_slot(conversation_id, slot, result=res)
            return res

        effective_prefix = _resolve_prefix(conv, explicit_prefix=prefix)
        is_branch = bool(conv.get("parent_conversation_id"))

        # Load recent messages (or full branch window) if the caller didn't provide explicit prompt/reply overrides
        first_user_msg = user_query.strip() if (user_query and user_query.strip()) else None
        first_assistant_msg = assistant_reply.strip() if (assistant_reply and assistant_reply.strip()) else None
        if not first_user_msg:
            history = get_chat_history(conversation_id=conversation_id, limit=None if is_branch else 6)
            first_user_msg, extracted_reply = _extract_prompt_and_reply(history, is_branch=is_branch)
            if not first_assistant_msg:
                first_assistant_msg = extracted_reply

        if not first_user_msg:
            res = {"status": "unchanged", "conversation_id": conversation_id, "title": initial_title}
            _release_inflight_slot(conversation_id, slot, result=res)
            return res

        fallback_title = _build_fallback_title(
            first_user_msg,
            prefix=effective_prefix,
            snippet_limit=38 if effective_prefix == "📱 " else 35,
        )

        try:
            # Local imports preserve monkeypatch compatibility with `patch("nexus.core.constants.get_chat_model", ...)`
            from nexus.core.constants import get_chat_model
            from nexus.agent.graph import extract_message_text

            chat_model = get_chat_model(tier="low", temperature=0.2)
            prompt = _build_title_prompt(
                first_user_msg,
                first_assistant_msg,
                is_mobile=(effective_prefix == "📱 "),
            )
            resp = chat_model.invoke(prompt)
            raw_content = extract_message_text(resp)
            final_title = _clean_generated_title(raw_content, prefix=effective_prefix) or fallback_title
            res = _commit_title_result(
                conversation_id,
                final_title,
                initial_title,
                source="auto",
                force=force,
            )
        except Exception as exc:
            logger.warning(f"Auto-title LLM invocation failed for conversation {conversation_id}: {exc}")
            # Keep `source="placeholder"` on LLM failure so transient errors don't permanently lock out future retries
            if force or initial_title in ("", "New Chat"):
                res = _commit_title_result(
                    conversation_id,
                    fallback_title,
                    initial_title,
                    source="placeholder",
                    force=force,
                )
            else:
                res = {
                    "status": "updated",
                    "conversation_id": conversation_id,
                    "title": initial_title,
                }
            res["fallback"] = True

        _release_inflight_slot(conversation_id, slot, result=res)
        return res
    except BaseException as exc:
        _release_inflight_slot(conversation_id, slot, error=exc)
        raise


async def auto_generate_title_async(
    conversation_id: str,
    *,
    force: bool = True,
    prefix: str = "",
) -> dict[str, Any]:
    """
    Async coroutine for FastAPI `POST /auto-title`.
    Offloads blocking SQLite I/O via `asyncio.to_thread` and awaits `chat_model.ainvoke`
    so the HTTP event loop stays non-blocking while deduplicating against background Turn-1 jobs.
    """
    # Acquire or inspect the per-conversation slot without blocking the asyncio event loop
    while True:
        with _inflight_lock:
            existing = _inflight_titles.get(conversation_id)
            if existing is None:
                slot: dict[str, Any] = {
                    "done_event": threading.Event(),
                    "result": None,
                    "error": None,
                    "force": force,
                }
                _inflight_titles[conversation_id] = slot
                break
            if not force:
                # Wait in worker thread for the active background Turn-1 job to finish instead of calling LLM twice
                await asyncio.to_thread(existing["done_event"].wait, 30.0)
                if existing.get("error") is not None:
                    raise existing["error"]
                if existing.get("result") is not None:
                    return dict(existing["result"])
                conv = await asyncio.to_thread(get_conversation, conversation_id)
                if not conv:
                    raise LookupError(f"Conversation '{conversation_id}' not found.")
                return {
                    "status": "unchanged",
                    "conversation_id": conversation_id,
                    "title": conv.get("title", "New Chat"),
                }
        # Forced refresh (`✨` button): wait outside lock for active job to settle, then loop to acquire ownership
        await asyncio.to_thread(existing["done_event"].wait, 30.0)

    try:
        conv = await asyncio.to_thread(get_conversation, conversation_id)
        if not conv:
            raise LookupError(f"Conversation '{conversation_id}' not found.")

        initial_title = conv.get("title") or "New Chat"
        title_source = conv.get("title_source") or "placeholder"

        if not force and title_source != "placeholder":
            res = {
                "status": "unchanged",
                "conversation_id": conversation_id,
                "title": initial_title,
            }
            _release_inflight_slot(conversation_id, slot, result=res)
            return res

        effective_prefix = _resolve_prefix(conv, explicit_prefix=prefix)
        is_branch = bool(conv.get("parent_conversation_id"))
        history = await asyncio.to_thread(
            get_chat_history,
            conversation_id=conversation_id,
            limit=None if is_branch else 6,
        )
        if not history:
            res = {"status": "unchanged", "title": initial_title}
            _release_inflight_slot(conversation_id, slot, result=res)
            return res

        first_user_msg, first_assistant_msg = _extract_prompt_and_reply(history, is_branch=is_branch)
        if not first_user_msg:
            res = {"status": "unchanged", "title": initial_title}
            _release_inflight_slot(conversation_id, slot, result=res)
            return res

        fallback_title = _build_fallback_title(first_user_msg, prefix=effective_prefix)

        try:
            # Local imports preserve monkeypatch compatibility with `patch("nexus.core.constants.get_chat_model", ...)`
            from nexus.core.constants import get_chat_model
            from nexus.agent.graph import extract_message_text

            chat_model = get_chat_model(tier="low", temperature=0.2)
            prompt = _build_title_prompt(
                first_user_msg,
                first_assistant_msg,
                is_mobile=(effective_prefix == "📱 "),
            )
            # BaseChatModel.ainvoke: awaits LLM HTTP response asynchronously without stalling FastAPI workers
            resp = await chat_model.ainvoke(prompt)
            raw_content = extract_message_text(resp)
            final_title = _clean_generated_title(raw_content, prefix=effective_prefix) or fallback_title
            res = await asyncio.to_thread(
                _commit_title_result,
                conversation_id,
                final_title,
                initial_title,
                source="auto",
                force=force,
            )
        except Exception as exc:
            logger.warning(f"Async auto-title failed for conversation {conversation_id}: {exc}")
            # Keep `source="placeholder"` on failure so automatic retries remain eligible
            res = await asyncio.to_thread(
                _commit_title_result,
                conversation_id,
                fallback_title,
                initial_title,
                source="placeholder",
                force=force,
            )
            res["fallback"] = True

        _release_inflight_slot(conversation_id, slot, result=res)
        return res
    except BaseException as exc:
        _release_inflight_slot(conversation_id, slot, error=exc)
        raise


def schedule_auto_title(
    conversation_id: str,
    *,
    prefix: str = "",
) -> Future[dict[str, Any]] | None:
    """
    Non-blocking background scheduler invoked by backend turn pipelines after Turn 1 completes.
    Returns the submitted `Future` (or None if the conversation is missing, already titled, or already queued).
    """
    if not conversation_id:
        return None

    conv = get_conversation(conversation_id)
    if not conv:
        return None
    if (conv.get("title_source") or "placeholder") != "placeholder":
        return None

    with _inflight_lock:
        if conversation_id in _inflight_titles:
            # Already running on a background worker or HTTP coroutine
            return None

    # Capture active `DB_PATH` so isolated pytest fixtures never receive writes from a finished test's thread
    captured_db_path = chats_db.DB_PATH

    def _run_guarded() -> dict[str, Any]:
        if chats_db.DB_PATH != captured_db_path or not captured_db_path.exists():
            return {"status": "skipped", "conversation_id": conversation_id}
        return auto_generate_title_sync(conversation_id, force=False, prefix=prefix)

    return _TITLE_EXECUTOR.submit(_run_guarded)
