"""
telegram_bridge.py — Bidirectional Telegram Mobile Voice & Notification Bridge for the Nexus Engine.

Connects a mobile phone (e.g. Google Pixel 8 Pro via Gboard Assistant Voice Typing or native Telegram
voice notes) to the universal `NexusAgent` via an asynchronous store-and-forward queue:
  1. Long-Polling Queue (`getUpdates`): When the laptop is asleep or in transit, Telegram buffers incoming
     text, voice notes (`.ogg` Opus), and photos in the cloud. When the laptop wakes and connects to Wi-Fi,
     the poller drains queued messages in chronological order with zero port forwarding or public IP needed.
  2. Dual-Input Voice Support: Accepts both on-device transcribed text (Pixel Gboard STT) and raw Telegram
     microphone voice memos (`message.voice` / `message.audio`), transcribing audio via Gemini Flash multimodal
     input (with OpenAI Whisper fallback).
  3. Conversation Continuity (`chats.db`): Each new top-level mobile message spawns a fresh conversation thread
     (`📱 <Title>`) visible in the Control Panel sidebar. Swiping-to-reply on any bot message (or prefixing with
     `/continue`) appends the turn to that existing conversation thread.
  4. Action & HITL Ping-Back: Replies directly to the phone with the agent's response, execution telemetry,
     and any staged Two-Phase Commit (`hitl.db`) file modifications.
"""
import argparse
import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# FileLock: Cross-process OS file mutex ensuring at most one local poller process calls `getUpdates` at a time
from filelock import FileLock, Timeout as FileLockTimeout
import httpx
from langchain_core.messages import HumanMessage

from nexus.core.chats_db import (
    create_conversation,
    get_chat_history,
    init_db as init_chats_db,
    log_message,
    update_conversation_title,
)
from nexus.core.config import EngineSettings
from nexus.core.constants import PROJECT_ROOT, get_chat_model, resolve_model_config
from nexus.core.cost import calculate_token_cost
from nexus.core.hitl_queue import get_db_connection as get_hitl_conn, get_pending_transactions
from nexus.core.logger import logger
from nexus.core.run_logger import log_run
from nexus.core.trace import reset_trace_thread_id, set_trace_thread_id, trace_bus

# ── Constants & Persistent State Ledger Paths ────────────────────────────────

# Base URL template for the Telegram Bot HTTP API
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
# Base URL template for downloading binary attachments (voice notes, audio, photos) from Telegram servers
TELEGRAM_FILE_BASE = "https://api.telegram.org/file/bot{token}/{file_path}"

# Persistent JSON state file tracking update offsets, auto-enrolled user/chat IDs, and message->thread mappings
STATE_FILE_PATH = PROJECT_ROOT / "logs" / "telegram_state.json"
# Cross-process OS lock file preventing duplicate local pollers (e.g. Windows Startup daemon + FastAPI) from colliding
POLLER_LOCK_PATH = PROJECT_ROOT / "logs" / "telegram_poller.lock"
# Maximum number of recent Telegram message_id -> conversation_id mappings retained for swipe-to-reply continuity
MAX_THREAD_MAP_ENTRIES = 250
# Telegram's hard single-message UTF-8 character limit is 4096; we chunk at 3800 to leave room for headers/footers
TELEGRAM_MAX_MSG_LEN = 3800

# Lock protecting concurrent reads/writes to `logs/telegram_state.json`
_state_lock = threading.Lock()

# Runtime singleton state for the background FastAPI poller task
_poller_task: Optional[asyncio.Task] = None
_poller_stop_event: Optional[asyncio.Event] = None
_poller_status: dict[str, Any] = {
    "running": False,
    "configured": False,
    "bot_username": None,
    "enrolled_user_id": None,
    "processed_count": 0,
    "last_poll_at": None,
    "last_error": None,
}


# ── 1. Persistent State Management (`logs/telegram_state.json`) ──────────────

# `-> dict[str, Any]` returns the deserialized state dictionary with guaranteed default keys.
def load_bridge_state() -> dict[str, Any]:
    """Load the persistent Telegram bridge state from `logs/telegram_state.json`.

    Guarantees default keys even if the file does not exist yet or was corrupted.
    """
    default_state: dict[str, Any] = {
        "last_update_id": 0,
        "enrolled_user_id": None,
        "enrolled_chat_id": None,
        "last_conversation_id": None,
        "message_thread_map": {},
    }
    with _state_lock:
        if not STATE_FILE_PATH.is_file():
            return default_state
        try:
            raw = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                default_state.update(raw)
                if not isinstance(default_state.get("message_thread_map"), dict):
                    default_state["message_thread_map"] = {}
        except Exception as exc:
            logger.warning(f"Telegram state load warning (using defaults): {exc}")
        return default_state


# `state: dict[str, Any]` is the updated dictionary to persist atomically to disk.
def save_bridge_state(state: dict[str, Any]) -> None:
    """Persist the Telegram bridge state to `logs/telegram_state.json`, pruning old thread mappings."""
    with _state_lock:
        STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Keep only the most recent MAX_THREAD_MAP_ENTRIES message->conversation mappings so the state file stays tiny
        thread_map = state.get("message_thread_map")
        if isinstance(thread_map, dict) and len(thread_map) > MAX_THREAD_MAP_ENTRIES:
            keys = list(thread_map.keys())
            for old_key in keys[:-MAX_THREAD_MAP_ENTRIES]:
                thread_map.pop(old_key, None)
        tmp_path = STATE_FILE_PATH.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp_path.replace(STATE_FILE_PATH)


# `message_id: int | str` is the Telegram message identifier.
# `conversation_id: str` is the Nexus `chats.db` UUID associated with that message.
def record_message_thread(message_id: int | str, conversation_id: str) -> None:
    """Link a Telegram `message_id` to a Nexus `conversation_id` so swipe-to-reply continues the same chat."""
    state = load_bridge_state()
    state["message_thread_map"][str(message_id)] = conversation_id
    state["last_conversation_id"] = conversation_id
    save_bridge_state(state)


# ── 2. Authorization & First-User Auto-Enrollment ────────────────────────────

# `user_id: int | str` is the incoming Telegram `from.id`.
# `chat_id: int | str` is the incoming Telegram `chat.id`.
# `-> tuple[bool, bool]` returns `(is_authorized, newly_enrolled)`.
def authorize_telegram_user(user_id: int | str, chat_id: int | str) -> tuple[bool, bool]:
    """Verify whether `user_id` is authorized to execute NexusAgent commands.

    Security & Zero-Friction Enrollment:
      1. If `TELEGRAM_ALLOWED_USER_ID` is explicitly set in `.env` (supports single ID or comma-separated IDs),
         only matching user IDs are permitted.
      2. If `TELEGRAM_ALLOWED_USER_ID` is omitted in `.env`, the first user who messages the private bot is
         automatically enrolled and persisted in `logs/telegram_state.json` as the sole authorized owner.
         Subsequent messages from any other user ID are strictly rejected.
    """
    live_settings = EngineSettings()
    uid_str = str(user_id).strip()
    cid_int = int(chat_id)
    state = load_bridge_state()

    configured_raw = (live_settings.telegram_allowed_user_id or "").strip()
    if configured_raw:
        allowed_set = {part.strip() for part in configured_raw.split(",") if part.strip()}
        if uid_str in allowed_set:
            # Update default outbound chat_id if needed
            if state.get("enrolled_chat_id") != cid_int or state.get("enrolled_user_id") != int(user_id):
                state["enrolled_user_id"] = int(user_id)
                state["enrolled_chat_id"] = cid_int
                save_bridge_state(state)
            return True, False
        return False, False

    # Fallback to persistent auto-enrolled owner in `logs/telegram_state.json`
    enrolled_uid = state.get("enrolled_user_id")
    if enrolled_uid is None:
        state["enrolled_user_id"] = int(user_id)
        state["enrolled_chat_id"] = cid_int
        save_bridge_state(state)
        _poller_status["enrolled_user_id"] = int(user_id)
        logger.info(f"🔒 Telegram Bridge auto-enrolled User ID {user_id} (chat_id={chat_id}) as sole owner.")
        return True, True

    if str(enrolled_uid).strip() == uid_str:
        if state.get("enrolled_chat_id") != cid_int:
            state["enrolled_chat_id"] = cid_int
            save_bridge_state(state)
        return True, False

    return False, False


# ── 3. Low-Level Telegram HTTP Client Helpers ────────────────────────────────

# `text: str` is the raw message string.
# `max_len: int` is the maximum chunk length (default 3800 chars).
# `-> list[str]` returns a list of non-empty message chunks respecting line boundaries where possible.
def split_telegram_message(text: str, max_len: int = TELEGRAM_MAX_MSG_LEN) -> list[str]:
    """Split a long response into Telegram-safe chunks (<4096 characters) along paragraph/line breaks."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ["(Empty response)"]
    if len(cleaned) <= max_len:
        return [cleaned]

    chunks: list[str] = []
    remaining = cleaned
    while len(remaining) > max_len:
        # Prefer splitting at the last newline within the safe window, else last space, else hard slice
        split_idx = remaining.rfind("\n", 0, max_len)
        if split_idx < max_len // 2:
            split_idx = remaining.rfind(" ", 0, max_len)
        if split_idx < max_len // 2:
            split_idx = max_len
        chunks.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


# `text: str` is the outbound message text.
# `chat_id: int | str | None` optional target chat ID; defaults to the enrolled owner's chat_id.
# `reply_to_message_id: int | None` optional incoming message ID to thread the reply under.
# `token: str | None` optional Bot API token override.
# `-> list[int]` returns the list of sent Telegram `message_id` integers.
def send_telegram_message(
    text: str,
    chat_id: Optional[int | str] = None,
    reply_to_message_id: Optional[int] = None,
    token: Optional[str] = None,
) -> list[int]:
    """Send a text message (or multi-chunk sequence) to the user's Telegram chat.

    Automatically attempts Markdown formatting first and falls back to plain text if Telegram's parser
    rejects unmatched markdown symbols (e.g. raw underscores in code/paths), guaranteeing 100% delivery.
    """
    live_settings = EngineSettings()
    bot_token = (token or live_settings.telegram_bot_token or "").strip()
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env.")

    state = load_bridge_state()
    target_chat = chat_id or state.get("enrolled_chat_id") or live_settings.telegram_allowed_user_id
    if not target_chat:
        raise ValueError(
            "No target Telegram chat_id known yet. Send any message from your phone to the bot first "
            "or set TELEGRAM_ALLOWED_USER_ID in .env."
        )

    url = TELEGRAM_API_BASE.format(token=bot_token, method="sendMessage")
    chunks = split_telegram_message(text)
    sent_ids: list[int] = []

    with httpx.Client(timeout=20.0) as client:
        for idx, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": target_chat,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            # Attach reply_to_message_id to the first chunk so the phone notification quotes the prompt
            if idx == 0 and reply_to_message_id is not None:
                payload["reply_to_message_id"] = reply_to_message_id

            resp = client.post(url, json=payload)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

            # Fallback: if Telegram returns HTTP 400 due to unmatched Markdown entities, resend as plain text
            if resp.status_code == 400 or not data.get("ok"):
                payload.pop("parse_mode", None)
                resp = client.post(url, json=payload)
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

            if data.get("ok") and isinstance(data.get("result"), dict):
                msg_id = data["result"].get("message_id")
                if isinstance(msg_id, int):
                    sent_ids.append(msg_id)
            else:
                logger.error(f"Telegram sendMessage failed: {resp.status_code} {resp.text[:300]}")

    return sent_ids


# `chat_id: int | str` is the target Telegram chat.
# `action: str` is the status indicator (e.g. `"typing"`, `"record_voice"`, `"upload_photo"`).
# `token: str | None` optional Bot API token override.
def send_chat_action(chat_id: int | str, action: str = "typing", token: Optional[str] = None) -> None:
    """Broadcast a transient status indicator (e.g. 'typing...') to the user's phone header."""
    live_settings = EngineSettings()
    bot_token = (token or live_settings.telegram_bot_token or "").strip()
    if not bot_token:
        return
    url = TELEGRAM_API_BASE.format(token=bot_token, method="sendChatAction")
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(url, json={"chat_id": chat_id, "action": action})
    except Exception:
        # Non-critical cosmetic indicator; ignore transient network blips
        pass


# `file_id: str` is the Telegram attachment identifier (`voice.file_id`, `audio.file_id`, `photo[-1].file_id`).
# `token: str | None` optional Bot API token override.
# `-> tuple[bytes, str]` returns `(raw_file_bytes, remote_file_path)`.
def download_telegram_file(file_id: str, token: Optional[str] = None) -> tuple[bytes, str]:
    """Resolve a Telegram `file_id` via `getFile` and download the binary payload into memory."""
    live_settings = EngineSettings()
    bot_token = (token or live_settings.telegram_bot_token or "").strip()
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env.")

    get_file_url = TELEGRAM_API_BASE.format(token=bot_token, method="getFile")
    with httpx.Client(timeout=30.0) as client:
        meta_resp = client.post(get_file_url, json={"file_id": file_id})
        meta_resp.raise_for_status()
        meta_json = meta_resp.json()
        if not meta_json.get("ok") or not isinstance(meta_json.get("result"), dict):
            raise RuntimeError(f"Telegram getFile failed for {file_id}: {meta_json}")
        remote_path = meta_json["result"].get("file_path", "")
        if not remote_path:
            raise RuntimeError(f"Telegram getFile returned empty file_path for {file_id}")

        download_url = TELEGRAM_FILE_BASE.format(token=bot_token, file_path=remote_path)
        file_resp = client.get(download_url)
        file_resp.raise_for_status()
        return file_resp.content, remote_path


# ── 4. Voice Note Audio Transcription (Telegram Mic Option) ──────────────────

# `audio_bytes: bytes` raw audio payload downloaded from Telegram (typically `.oga` / `audio/ogg` Opus).
# `mime_type: str` MIME type of the audio stream (default `"audio/ogg"`).
# `-> str` returns the verbatim natural-language transcript.
def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Transcribe a Telegram voice note or audio clip into clean text.

    Strategy:
      1. Primary (Gemini Flash Multimodal Audio): Sends base64-encoded audio directly to the configured
         low-tier Gemini Flash model (`gemini-3.8-flash`), which natively decodes `audio/ogg` Opus voice notes
         with high accuracy and punctuation.
      2. Fallback (OpenAI Whisper API): If Gemini is not configured or raises an error and `OPENAI_API_KEY`
         is available, transcribes via OpenAI's `whisper-1` endpoint.
    """
    if not audio_bytes:
        raise ValueError("Cannot transcribe empty audio payload.")

    live_settings = EngineSettings()
    gemini_key = live_settings.gemini_api_key or live_settings.google_api_key
    errors: list[str] = []

    # 1. Primary Path: Gemini Flash native multimodal audio transcription
    if gemini_key:
        try:
            from nexus.agent.graph import extract_message_text

            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            chat_model = get_chat_model(tier="gemini:low", temperature=0.0)
            msg = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "Transcribe this spoken voice note verbatim into clean, properly punctuated text. "
                            "Do NOT answer or execute the request yourself—return ONLY the exact spoken transcript "
                            "with no quotation marks, prefixes, or commentary."
                        ),
                    },
                    {
                        "type": "media",
                        "mime_type": mime_type or "audio/ogg",
                        "data": b64_audio,
                    },
                ]
            )
            resp = chat_model.invoke([msg])
            transcript = extract_message_text(resp).strip()
            if transcript:
                return transcript
        except Exception as exc:
            errors.append(f"Gemini audio transcription failed: {exc}")

    # 2. Fallback Path: OpenAI Whisper (`whisper-1`) if OPENAI_API_KEY is configured
    if live_settings.openai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=live_settings.openai_api_key)
            ext = "ogg" if "ogg" in (mime_type or "").lower() else "mp3"
            bio = io.BytesIO(audio_bytes)
            bio.name = f"voice_note.{ext}"
            tx = client.audio.transcriptions.create(model="whisper-1", file=bio)
            transcript = (getattr(tx, "text", "") or "").strip()
            if transcript:
                return transcript
        except Exception as exc:
            errors.append(f"OpenAI Whisper transcription failed: {exc}")

    err_detail = "; ".join(errors) if errors else "No multimodal audio provider (GEMINI_API_KEY or OPENAI_API_KEY) configured."
    raise RuntimeError(f"Failed to transcribe voice note: {err_detail}")


# ── 5. Conversation Naming & HITL Summary Helpers ────────────────────────────

# `conversation_id: str` is the `chats.db` conversation UUID.
# `user_query: str` is the user's transcribed voice or text prompt.
# `assistant_reply: str` is the agent's response text.
# `-> str` returns the generated `📱 <Title>` string and updates `chats.db`.
def _generate_mobile_conversation_title(
    conversation_id: str,
    user_query: str,
    assistant_reply: str = "",
) -> str:
    """Summarize the opening mobile turn into a concise `📱 <3-6 Word Title>` in `chats.db`."""
    clean_query = user_query.strip().replace("\n", " ")
    fallback = f"📱 {clean_query[:38].strip()}" + ("..." if len(clean_query) > 38 else "")
    try:
        from nexus.agent.graph import extract_message_text

        chat_model = get_chat_model(tier="low", temperature=0.2)
        prompt = (
            "Generate a concise, high-signal conversation title (maximum 3 to 6 words) summarizing this mobile "
            "voice/text request. Do NOT use quotes, ending punctuation, prefixes, or markdown. Return ONLY the title.\n\n"
            f"User prompt: {clean_query[:400]}"
        )
        if assistant_reply:
            prompt += f"\nAssistant excerpt: {assistant_reply[:300]}"
        resp = chat_model.invoke(prompt)
        raw_title = extract_message_text(resp).strip().strip('"\'`').replace("\n", " ").strip()
        for prefix in ("Title:", "title:", "Topic:", "topic:", "📱"):
            if raw_title.startswith(prefix):
                raw_title = raw_title[len(prefix) :].strip()
        raw_title = raw_title.strip('"\'`')
        if len(raw_title) > 52:
            raw_title = raw_title[:49] + "..."
        final_title = f"📱 {raw_title}" if raw_title else fallback
    except Exception:
        final_title = fallback

    update_conversation_title(conversation_id, final_title)
    return final_title


# `conversation_id: str` is the UUID of the active conversation turn.
# `-> list[dict[str, Any]]` returns all pending HITL transactions staged during this conversation.
def get_pending_hitl_for_conversation(conversation_id: str) -> list[dict[str, Any]]:
    """Query `hitl.db` for pending file modifications staged under `conversation_id`."""
    try:
        conn = get_hitl_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, action_type, target_file, destination_file
            FROM transactions
            WHERE conversation_id = ? AND status = 'pending'
            ORDER BY id ASC
            """,
            (conversation_id,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        logger.warning(f"Failed querying HITL transactions for {conversation_id}: {exc}")
        return []


# ── 6. Core Message Ingestion & Agent Dispatch Spine ─────────────────────────

# `message: dict[str, Any]` is a raw Telegram `Message` object from `getUpdates`.
# `token: str | None` optional Bot API token override.
# `-> dict[str, Any]` returns execution metadata (`status`, `conversation_id`, `response`, `hitl_count`).
def process_telegram_message(message: dict[str, Any], token: Optional[str] = None) -> dict[str, Any]:
    """Process a single incoming Telegram message (text, voice note, audio, or photo) end-to-end.

    Execution Spine:
      1. Authorize sender (`authorize_telegram_user`); drop unauthorized senders immediately.
      2. Handle fast slash commands (`/start`, `/id`, `/status`, `/hitl`) without invoking an LLM turn.
      3. If `voice` or `audio` is attached, download from Telegram and transcribe via `transcribe_audio_bytes`.
      4. If `photo` is attached, save highest-resolution image to `logs/uploads/` for multimodal inspection.
      5. Determine conversation thread:
         - If the user swiped-to-reply on an earlier message (or used `/continue`), resume that `conversation_id`.
         - Otherwise create a fresh conversation in `chats.db`.
      6. Run `run_nexus_agent_with_trace` while broadcasting a live `'typing...'` indicator to the phone.
      7. Persist messages, traces, costs, and run logs so the turn appears immediately in the Control Panel GUI.
      8. Send the structured ping-back reply to the user's phone with HITL queue counts and thread metadata.
    """
    init_chats_db()
    live_settings = EngineSettings()
    bot_token = (token or live_settings.telegram_bot_token or "").strip()

    from_user = message.get("from") or {}
    chat_obj = message.get("chat") or {}
    user_id = from_user.get("id")
    chat_id = chat_obj.get("id")
    incoming_msg_id = message.get("message_id")

    if user_id is None or chat_id is None:
        return {"status": "ignored", "reason": "missing_user_or_chat_id"}

    is_auth, newly_enrolled = authorize_telegram_user(user_id=user_id, chat_id=chat_id)
    if not is_auth:
        logger.warning(f"🚫 Ignored unauthorized Telegram message from user_id={user_id} (@{from_user.get('username')})")
        return {"status": "unauthorized", "user_id": user_id}

    raw_text = (message.get("text") or message.get("caption") or "").strip()
    voice_obj = message.get("voice") or message.get("audio")
    photo_list = message.get("photo")

    # ── Built-in Zero-Cost Slash Commands ──
    lower_text = raw_text.lower()
    if lower_text in ("/start", "/id", "/help") and not voice_obj:
        resolved = resolve_model_config(live_settings.telegram_default_tier)
        enroll_banner = (
            f"🔒 *Auto-Enrolled Owner:* Your Telegram User ID (`{user_id}`) is now locked as the sole owner.\n"
            f"*(Optional: add `TELEGRAM_ALLOWED_USER_ID={user_id}` to `.env`)*\n\n"
            if newly_enrolled
            else ""
        )
        help_reply = (
            f"🧠 *Nexus Mobile Bridge Online*\n\n"
            f"{enroll_banner}"
            f"• *User ID:* `{user_id}`\n"
            f"• *Default Model:* `{resolved['model_name']}` (`{resolved['tier']}`)\n\n"
            f"*How to use:*\n"
            f"1. *Speak (Gboard STT)* or *Hold Mic (Voice Note)* — starts a new `📱` chat thread.\n"
            f"2. *Swipe-to-Reply* on any bot message — continues that existing thread.\n"
            f"3. `/fast <prompt>` or `/strong <prompt>` — override model tier.\n"
            f"4. `/continue <prompt>` — append to your latest mobile chat.\n"
            f"5. `/hitl` — inspect pending HITL file edits."
        )
        send_telegram_message(help_reply, chat_id=chat_id, reply_to_message_id=incoming_msg_id, token=bot_token)
        return {"status": "command", "command": lower_text}

    if lower_text == "/status" and not voice_obj:
        pending_txs = get_pending_transactions()
        resolved = resolve_model_config(live_settings.telegram_default_tier)
        status_reply = (
            f"✅ *Nexus Engine Status: Online*\n"
            f"• *Active Model:* `{resolved['model_name']}` (`{resolved['tier']}`)\n"
            f"• *Pending HITL Edits:* `{len(pending_txs)}`\n"
            f"• *User ID:* `{user_id}`"
        )
        send_telegram_message(status_reply, chat_id=chat_id, reply_to_message_id=incoming_msg_id, token=bot_token)
        return {"status": "command", "command": "/status"}

    if lower_text == "/hitl" and not voice_obj:
        pending_txs = get_pending_transactions()
        if not pending_txs:
            hitl_reply = "✅ *HITL Queue Clear* — No pending file changes waiting for review."
        else:
            lines = [f"⚠️ *Pending HITL Queue ({len(pending_txs)}):*"]
            for tx in pending_txs[:15]:
                lines.append(f"• `#{tx['id']}` [{tx['action_type']}] `{tx['target_file']}`")
            if len(pending_txs) > 15:
                lines.append(f"_...and {len(pending_txs) - 15} more in the Control Panel._")
            hitl_reply = "\n".join(lines)
        send_telegram_message(hitl_reply, chat_id=chat_id, reply_to_message_id=incoming_msg_id, token=bot_token)
        return {"status": "command", "command": "/hitl"}

    # Immediately notify phone UI that Nexus is processing
    send_chat_action(chat_id=chat_id, action="typing", token=bot_token)

    # ── Phase 1: Voice Note Transcription (Telegram Mic Option) ──
    transcribed_voice_text: Optional[str] = None
    if isinstance(voice_obj, dict) and voice_obj.get("file_id"):
        try:
            audio_bytes, remote_path = download_telegram_file(voice_obj["file_id"], token=bot_token)
            mime_type = voice_obj.get("mime_type") or ("audio/ogg" if remote_path.endswith(".oga") else "audio/mpeg")
            transcribed_voice_text = transcribe_audio_bytes(audio_bytes, mime_type=mime_type)
            logger.info(f"🎙️ Transcribed Telegram voice note ({len(audio_bytes)} bytes): {transcribed_voice_text}")
        except Exception as exc:
            err_msg = f"❌ *Voice Transcription Error:* {exc}"
            send_telegram_message(err_msg, chat_id=chat_id, reply_to_message_id=incoming_msg_id, token=bot_token)
            return {"status": "error", "error": str(exc)}

    # Combine transcribed voice note and any text/caption
    if transcribed_voice_text and raw_text:
        effective_query = f"{raw_text}\n\n{transcribed_voice_text}".strip()
    elif transcribed_voice_text:
        effective_query = transcribed_voice_text.strip()
    else:
        effective_query = raw_text

    # ── Phase 2: Optional Photo Attachment Ingestion ──
    uploaded_images: list[str] = []
    if isinstance(photo_list, list) and photo_list:
        try:
            # Telegram sends an array of photo sizes; the last element is the highest resolution
            best_photo = photo_list[-1]
            file_id = best_photo.get("file_id")
            unique_id = best_photo.get("file_unique_id") or int(time.time())
            if file_id:
                img_bytes, remote_path = download_telegram_file(file_id, token=bot_token)
                ext = Path(remote_path).suffix or ".jpg"
                uploads_dir = PROJECT_ROOT / "logs" / "uploads"
                uploads_dir.mkdir(parents=True, exist_ok=True)
                img_filename = f"tg_{unique_id}{ext}"
                (uploads_dir / img_filename).write_bytes(img_bytes)
                uploaded_images.append(f"/api/agents/uploads/{img_filename}")
        except Exception as exc:
            logger.warning(f"Failed downloading Telegram photo attachment: {exc}")

    if not effective_query and not uploaded_images:
        return {"status": "ignored", "reason": "empty_message"}

    # ── Phase 3: Parse Optional Tier / Thread Directives (`/fast`, `/strong`, `/continue`) ──
    requested_tier: Optional[str] = live_settings.telegram_default_tier or None
    force_continue = False
    force_new = False

    if effective_query.startswith("/"):
        parts = effective_query.split(maxsplit=1)
        cmd = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if cmd in ("/fast", "/low"):
            requested_tier = "low"
            effective_query = rest
        elif cmd in ("/strong", "/argon", "/opus"):
            requested_tier = "strong"
            effective_query = rest
        elif cmd in ("/continue", "/c"):
            force_continue = True
            effective_query = rest
        elif cmd in ("/new", "/n"):
            force_new = True
            effective_query = rest

    if not effective_query and uploaded_images:
        effective_query = "Analyze the attached image(s)."
    elif not effective_query:
        send_telegram_message(
            "ℹ️ Provide a prompt after the command (e.g. `/fast check my schedule tomorrow`).",
            chat_id=chat_id,
            reply_to_message_id=incoming_msg_id,
            token=bot_token,
        )
        return {"status": "ignored", "reason": "empty_command_body"}

    # ── Phase 4: Resolve Conversation Thread (`chats.db`) ──
    state = load_bridge_state()
    thread_map: dict[str, str] = state.get("message_thread_map") or {}
    reply_to_obj = message.get("reply_to_message") or {}
    replied_msg_id = reply_to_obj.get("message_id")

    conversation_id: Optional[str] = None
    is_new_conversation = False

    if not force_new:
        if replied_msg_id and str(replied_msg_id) in thread_map:
            conversation_id = thread_map[str(replied_msg_id)]
        elif force_continue and state.get("last_conversation_id"):
            conversation_id = state.get("last_conversation_id")

    if not conversation_id:
        snippet = effective_query.replace("\n", " ")[:36].strip()
        initial_title = f"📱 {snippet}" + ("..." if len(effective_query) > 36 else "")
        conversation_id = create_conversation(title=initial_title)
        is_new_conversation = True

    if incoming_msg_id is not None:
        record_message_thread(incoming_msg_id, conversation_id)

    # Log user message to `chats.db`
    user_display_content = (
        f"🎙️ {effective_query}" if transcribed_voice_text and not raw_text else effective_query
    )
    log_message(
        role="user",
        content=user_display_content,
        conversation_id=conversation_id,
        images=uploaded_images if uploaded_images else None,
    )

    # ── Phase 5: Execute `NexusAgent` with Background Typing Heartbeat ──
    stop_typing = threading.Event()

    def _typing_heartbeat() -> None:
        # Telegram's 'typing...' status expires after ~5 seconds; refresh every 4s while agent reasons
        while not stop_typing.wait(4.0):
            send_chat_action(chat_id=chat_id, action="typing", token=bot_token)

    heartbeat_thread = threading.Thread(target=_typing_heartbeat, daemon=True)
    heartbeat_thread.start()

    trace_events: list[dict[str, Any]] = []

    def _on_trace(evt: dict[str, Any]) -> None:
        trace_events.append(evt)

    unsub = trace_bus.subscribe(_on_trace, thread_id=conversation_id)
    trace_token = set_trace_thread_id(conversation_id)
    t0 = time.time()

    try:
        from nexus.agent.api import run_nexus_agent_with_trace

        result = run_nexus_agent_with_trace(
            query=effective_query,
            thread_id=conversation_id,
            model_tier=requested_tier,
            images=uploaded_images if uploaded_images else None,
        )
    finally:
        stop_typing.set()
        unsub()
        reset_trace_thread_id(trace_token)

    elapsed_sec = time.time() - t0
    response_text = (result.get("response") or "").strip() or "(Completed with no text output)"
    used_tier = result.get("model_tier")
    used_model = result.get("model_name")
    routed_domain = result.get("domain")

    # Compute turn USD cost from trace events
    turn_cost_usd = sum(
        float(e.get("data", {}).get("cost_usd", 0.0) or 0.0)
        for e in trace_events
        if e.get("type") == "info"
    )
    if not turn_cost_usd:
        tot_in = sum(int(e.get("data", {}).get("input_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
        tot_out = sum(int(e.get("data", {}).get("output_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
        tot_cached = sum(int(e.get("data", {}).get("cached_tokens", 0) or 0) for e in trace_events if e.get("type") == "info")
        if tot_in or tot_out:
            turn_cost_usd = calculate_token_cost(
                input_tokens=tot_in,
                output_tokens=tot_out,
                cached_tokens=tot_cached,
                model_name=used_model,
                tier=used_tier,
            )
    turn_cost_formatted = round(turn_cost_usd, 4) if turn_cost_usd else None

    # Persist assistant message + trace to `chats.db`
    log_message(
        role="assistant",
        content=response_text,
        agent="nexus",
        domain=routed_domain,
        confidence=result.get("confidence"),
        trace=trace_events,
        conversation_id=conversation_id,
        model_tier=used_tier,
        model_name=used_model,
        cost_usd=turn_cost_formatted,
    )

    # Persist run log snapshot to `logs/runs/`
    log_run(
        agent_name="nexus",
        query=effective_query,
        response=response_text,
        thread_id=conversation_id,
        domain=routed_domain,
        confidence=result.get("confidence"),
        reasoning=result.get("reasoning"),
        tool_calls=result.get("tool_calls"),
        trace_events=trace_events,
        latency_seconds=elapsed_sec,
        metadata={"source": "telegram", "model_tier": used_tier, "model_name": used_model},
    )

    # Auto-title new mobile conversation using fast low-tier model
    if is_new_conversation:
        final_title = _generate_mobile_conversation_title(conversation_id, effective_query, response_text)
    else:
        history_convs = get_chat_history(conversation_id=conversation_id, limit=1)
        final_title = f"📱 Thread ({conversation_id[:8]})"

    # ── Phase 6: Inspect Staged HITL Transactions & Assemble Ping-Back ──
    staged_hitl = get_pending_hitl_for_conversation(conversation_id)
    reply_sections: list[str] = []

    if newly_enrolled:
        reply_sections.append(f"🔒 _Auto-locked bot to your Telegram ID (`{user_id}`)._")

    if transcribed_voice_text:
        reply_sections.append(f"🎙️ _{transcribed_voice_text}_")

    reply_sections.append(response_text)

    if staged_hitl:
        hitl_lines = [f"⚠️ *HITL Staged ({len(staged_hitl)}):*"]
        for tx in staged_hitl[:8]:
            hitl_lines.append(f"• `#{tx['id']}` [{tx['action_type']}] `{tx['target_file']}`")
        reply_sections.append("\n".join(hitl_lines))

    cost_badge = f" · ${turn_cost_formatted:.4f}" if turn_cost_formatted else ""
    footer = f"───────────────────\n{final_title} · `{used_tier}` · {elapsed_sec:.1f}s{cost_badge}"
    reply_sections.append(footer)

    full_reply_text = "\n\n".join(reply_sections)
    sent_msg_ids = send_telegram_message(
        text=full_reply_text,
        chat_id=chat_id,
        reply_to_message_id=incoming_msg_id,
        token=bot_token,
    )

    # Record all outbound message IDs so swiping-to-reply on the bot's answer continues this exact conversation
    for mid in sent_msg_ids:
        record_message_thread(mid, conversation_id)

    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "title": final_title,
        "response": response_text,
        "transcribed_voice": transcribed_voice_text,
        "hitl_staged_count": len(staged_hitl),
        "elapsed_seconds": round(elapsed_sec, 2),
    }


# ── 7. Long-Polling Queue Loop (FastAPI Background Task & Standalone CLI) ────

# `token: str | None` optional Bot API token override.
# `-> dict[str, Any]` returns bot identity metadata (`id`, `username`, `first_name`) from Telegram `getMe`.
def verify_telegram_bot(token: Optional[str] = None) -> dict[str, Any]:
    """Validate `TELEGRAM_BOT_TOKEN` against Telegram's `getMe` endpoint."""
    live_settings = EngineSettings()
    bot_token = (token or live_settings.telegram_bot_token or "").strip()
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env.")
    url = TELEGRAM_API_BASE.format(token=bot_token, method="getMe")
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getMe failed: {data}")
        return data.get("result") or {}


# `-> dict[str, Any]` returns a snapshot of the background poller's health and configuration state.
def get_telegram_bridge_status() -> dict[str, Any]:
    """Return current runtime status of the Telegram Mobile Bridge for `/api/health` and UI diagnostics."""
    live_settings = EngineSettings()
    state = load_bridge_state()
    configured = bool((live_settings.telegram_bot_token or "").strip())
    return {
        **_poller_status,
        "configured": configured,
        "enabled": bool(live_settings.telegram_enabled),
        "enrolled_user_id": live_settings.telegram_allowed_user_id or state.get("enrolled_user_id"),
        "enrolled_chat_id": state.get("enrolled_chat_id"),
        "last_update_id": state.get("last_update_id", 0),
    }


# `stop_event: asyncio.Event` signals cooperative shutdown when Uvicorn exits or reloads.
async def telegram_polling_loop(stop_event: asyncio.Event) -> None:
    """Asynchronous Telegram `getUpdates` long-polling worker loop.

    Why Long-Polling + Cross-Process FileLock is ideal for a traveling laptop:
      - Requires zero public IP, port forwarding, or webhook tunnels.
      - When the laptop lid closes or enters sleep, Telegram buffers all messages in the cloud.
      - When the laptop wakes and reconnects to Wi-Fi, `httpx.AsyncClient` resumes polling and
        drains the queued backlog in exact chronological order (`offset = last_update_id + 1`).
      - Acquires `logs/telegram_poller.lock` (`FileLock`) so if both a Windows Startup background
        daemon AND `start.ps1` (FastAPI) are running, only one polls Telegram at a time (zero 409 conflicts),
        with automatic failover if either process stops.
    """
    _poller_status["running"] = True
    backoff_sec = 2.0
    POLLER_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    process_lock = FileLock(str(POLLER_LOCK_PATH), timeout=0.0)
    has_lock = False

    try:
        while not stop_event.is_set():
            live_settings = EngineSettings()
            bot_token = (live_settings.telegram_bot_token or "").strip()
            _poller_status["configured"] = bool(bot_token)

            # If token is not configured yet in `.env`, sleep quietly and re-check every 10s
            # so adding TELEGRAM_BOT_TOKEN to `.env` activates the bridge live without restarting!
            if not bot_token or not live_settings.telegram_enabled:
                if has_lock:
                    process_lock.release()
                    has_lock = False
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    pass
                continue

            # Ensure only one process on this machine polls Telegram at a time
            if not has_lock:
                try:
                    process_lock.acquire(timeout=0.0)
                    has_lock = True
                except FileLockTimeout:
                    # Another local process (e.g. FastAPI or background startup daemon) currently holds the lock
                    _poller_status["last_error"] = "Standby (another local Nexus process is actively polling)"
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

            # Resolve bot username once on first connect
            if not _poller_status.get("bot_username"):
                try:
                    me = await asyncio.to_thread(verify_telegram_bot, bot_token)
                    _poller_status["bot_username"] = me.get("username")
                    logger.info(f"📱 Telegram Mobile Bridge connected to @{me.get('username')} (long-polling active)")
                except Exception as exc:
                    _poller_status["last_error"] = str(exc)
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=min(backoff_sec, 30.0))
                    except asyncio.TimeoutError:
                        pass
                    backoff_sec = min(backoff_sec * 1.5, 30.0)
                    continue

            state = load_bridge_state()
            offset = int(state.get("last_update_id", 0)) + 1
            url = TELEGRAM_API_BASE.format(token=bot_token, method="getUpdates")

            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.post(
                        url,
                        json={
                            "offset": offset,
                            "timeout": 25,
                            "allowed_updates": ["message"],
                        },
                    )
                _poller_status["last_poll_at"] = datetime.now(timezone.utc).isoformat()
                _poller_status["last_error"] = None
                backoff_sec = 2.0

                if resp.status_code == 409:
                    # 409 Conflict occurs briefly if a prior Uvicorn reload worker hasn't closed its socket yet
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                if not data.get("ok"):
                    _poller_status["last_error"] = str(data.get("description") or resp.status_code)
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
                    continue

                updates = data.get("result") or []
                for upd in updates:
                    if stop_event.is_set():
                        break
                    upd_id = upd.get("update_id")
                    msg = upd.get("message")

                    # Advance offset BEFORE or immediately upon processing so a crash never loops the same update
                    if isinstance(upd_id, int):
                        st = load_bridge_state()
                        st["last_update_id"] = max(int(st.get("last_update_id", 0)), upd_id)
                        save_bridge_state(st)

                    if isinstance(msg, dict):
                        try:
                            # Offload synchronous LangGraph execution to a worker thread so FastAPI stays responsive
                            await asyncio.to_thread(process_telegram_message, msg, bot_token)
                            _poller_status["processed_count"] = int(_poller_status.get("processed_count", 0)) + 1
                        except Exception as msg_exc:
                            logger.error(f"Error processing Telegram update {upd_id}: {msg_exc}")
                            _poller_status["last_error"] = str(msg_exc)

            except asyncio.CancelledError:
                break
            except Exception as poll_exc:
                # Expected when laptop is waking from sleep and Wi-Fi is still re-associating
                _poller_status["last_error"] = str(poll_exc)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=min(backoff_sec, 30.0))
                except asyncio.TimeoutError:
                    pass
                backoff_sec = min(backoff_sec * 1.5, 30.0)
    finally:
        if has_lock:
            try:
                process_lock.release()
            except Exception:
                pass
        _poller_status["running"] = False


async def start_telegram_poller() -> None:
    """Start the background Telegram long-polling task inside the FastAPI lifespan."""
    global _poller_task, _poller_stop_event
    if _poller_task and not _poller_task.done():
        return
    _poller_stop_event = asyncio.Event()
    _poller_task = asyncio.create_task(telegram_polling_loop(_poller_stop_event))


async def stop_telegram_poller() -> None:
    """Gracefully stop the background Telegram long-polling task on FastAPI shutdown."""
    global _poller_task, _poller_stop_event
    if _poller_stop_event:
        _poller_stop_event.set()
    if _poller_task and not _poller_task.done():
        _poller_task.cancel()
        try:
            await asyncio.wait_for(_poller_task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    _poller_task = None
    _poller_stop_event = None
    _poller_status["running"] = False


# ── 8. Windows Logon Autostart Installer (`shell:startup`) ───────────────────

# `-> Path` returns the path to the user's Windows Startup folder launcher (`NexusTelegramBridge.vbs`).
def get_windows_startup_script_path() -> Path:
    """Resolve the user's Windows `Startup` directory path for zero-admin logon autostart."""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "NexusTelegramBridge.vbs"


# `spawn_now: bool = True` also launches the background daemon immediately if not already running.
# `-> Path` returns the written `.vbs` startup script path.
def install_windows_autostart(spawn_now: bool = True) -> Path:
    """Register a windowless Windows Startup launcher so the Telegram Mobile Bridge spins up at user login.

    Also safe to run alongside `start.ps1`: `POLLER_LOCK_PATH` (`FileLock`) guarantees that only one
    local process polls Telegram at a time, failing over automatically when `start.ps1` closes.
    """
    vbs_path = get_windows_startup_script_path()
    vbs_path.parent.mkdir(parents=True, exist_ok=True)
    pythonw_exe = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    python_exe = pythonw_exe if pythonw_exe.is_file() else (PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

    # VBScript `WScript.Shell.Run(..., 0, False)` launches the Python daemon with window style 0 (completely hidden)
    vbs_content = (
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{PROJECT_ROOT}"\n'
        f'WshShell.Run """{python_exe}"" -m nexus.shared_tools.telegram_bridge --poll", 0, False\n'
    )
    vbs_path.write_text(vbs_content, encoding="utf-8")

    if spawn_now and sys.platform == "win32":
        # Check if another poller already holds the lock before spawning
        lock = FileLock(str(POLLER_LOCK_PATH), timeout=0.0)
        try:
            lock.acquire(timeout=0.0)
            lock.release()
            # No process holds the lock yet; spawn detached background daemon
            subprocess.Popen(
                [str(python_exe), "-m", "nexus.shared_tools.telegram_bridge", "--poll"],
                cwd=str(PROJECT_ROOT),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileLockTimeout:
            pass

    return vbs_path


def uninstall_windows_autostart() -> bool:
    """Remove the Windows Startup launcher if present."""
    vbs_path = get_windows_startup_script_path()
    if vbs_path.is_file():
        vbs_path.unlink()
        return True
    return False


# ── 9. Standalone CLI Entrypoint (`python -m nexus.shared_tools.telegram_bridge`) ─

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Nexus Telegram Mobile Voice & Notification Bridge (Daemon & CLI)."
    )
    parser.add_argument(
        "--send",
        type=str,
        default=None,
        help="Send a proactive notification message to your phone via Telegram.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check Telegram Bot connectivity and enrolled owner status.",
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Run the standalone Telegram long-polling daemon in the foreground.",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Register the Telegram Mobile Bridge to spin up automatically on Windows login.",
    )
    parser.add_argument(
        "--uninstall-autostart",
        action="store_true",
        help="Remove the Windows login autostart launcher.",
    )
    args = parser.parse_args()

    if args.install_autostart:
        path = install_windows_autostart(spawn_now=True)
        print(f"✅ Installed Windows Startup launcher and started background poller: {path}")
    elif args.uninstall_autostart:
        removed = uninstall_windows_autostart()
        print(f"✅ Removed Windows Startup launcher: {removed}")
    elif args.status:
        status = get_telegram_bridge_status()
        status["autostart_installed"] = get_windows_startup_script_path().is_file()
        if status["configured"]:
            try:
                bot_info = verify_telegram_bot()
                status["bot_username"] = bot_info.get("username")
                status["bot_id"] = bot_info.get("id")
            except Exception as err:
                status["error"] = str(err)
        print(json.dumps(status, indent=2))
    elif args.send:
        sent = send_telegram_message(args.send)
        print(f"✅ Sent Telegram notification (message_ids={sent}).")
    else:
        print("📱 Starting standalone Nexus Telegram Mobile Bridge (Ctrl+C to stop)...")
        stop_evt = asyncio.Event()
        try:
            asyncio.run(telegram_polling_loop(stop_evt))
        except KeyboardInterrupt:
            print("\n👋 Telegram Mobile Bridge stopped.")
