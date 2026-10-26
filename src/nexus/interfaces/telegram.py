"""
telegram.py — Telegram bot interface for the Nexus Engine.
Provides remote mobile access to the Universal NexusAgent via text, voice messages,
session thread management (/new), and remote HITL transaction review (/pending, /approve, /reject).
"""
import asyncio
import os
import sys
import time
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
from nexus.agent.api import route_content
from nexus.core.audio import transcribe_audio
from nexus.core.config import settings
from nexus.core.constants import PROJECT_ROOT
from nexus.core.hitl_queue import (
    HitlCommitError,
    StaleBaseError,
    TransactionNotFoundError,
    commit_transaction,
    get_pending_transactions,
    init_db,
    update_transaction_status,
)

# Telegram enforces a strict 4096 UTF-8 character limit per message; 4000 leaves safety headroom for Markdown tags
TELEGRAM_MAX_MSG_LEN = 4000

TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
ALLOWED_USER_IDS_STR = settings.allowed_user_ids
# List comprehension: parses comma-separated user IDs from `.env` into integers, ignoring whitespace/empty entries
ALLOWED_USER_IDS = [int(x.strip()) for x in ALLOWED_USER_IDS_STR.split(",") if x.strip()]

# Per-chat active LangGraph thread ID map (`chat_id -> thread_id`).
# Defaults to `"nexus_primary"` so mobile chats share continuity unless reset via `/new`.
_ACTIVE_THREADS: dict[int, str] = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# `update: Update` is the incoming Telegram webhook/polling payload; `-> bool` indicates whether the caller is whitelisted.
async def auth_middleware(update: Update) -> bool:
    """Verify the sender's Telegram user ID against `ALLOWED_USER_IDS` from `.env`."""
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized access attempt from user ID {user_id}")
        if update.message:
            await update.message.reply_text("⛔ Unauthorized access.")
        return False
    return True


# `text: str` is the full agent response; `max_len: int` is the per-message cap; `-> list[str]` returns ordered slices.
def _split_telegram_message(text: str, max_len: int = TELEGRAM_MAX_MSG_LEN) -> list[str]:
    """Split long agent responses on paragraph or line boundaries so Telegram never rejects >4096-char messages."""
    if not text:
        return ["No response generated."]
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        # Prefer splitting at the last double-newline (paragraph break) or single newline inside the safe window
        split_idx = remaining.rfind("\n\n", 0, max_len)
        if split_idx == -1:
            split_idx = remaining.rfind("\n", 0, max_len)
        if split_idx == -1:
            split_idx = remaining.rfind(" ", 0, max_len)
        if split_idx <= 0:
            split_idx = max_len

        chunks.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks or ["No response generated."]


# `update: Update` is the active Telegram message context; `text: str` is the full markdown string to send.
async def _send_chunked_reply(update: Update, text: str) -> None:
    """Send a potentially multi-part response, falling back from Markdown to plain text if entity parsing fails."""
    if not update.message:
        return
    for chunk in _split_telegram_message(text):
        try:
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        except BadRequest as e:
            # Telegram's legacy Markdown parser fails if unclosed `*`, `_`, or `` ` `` appear in raw note excerpts
            if "Can't parse entities" in str(e):
                logger.warning("Markdown parse failed on chunk, falling back to raw text.")
                await update.message.reply_text(chunk, disable_web_page_preview=True)
            else:
                raise


def format_telegram_response(final_state: dict) -> str:
    """Format the LangGraph final state into a Telegram-friendly Markdown string."""
    # We are omitting sources in Telegram for now because obsidian:// deep links 
    # do not always render properly in mobile Telegram clients.
    if "response" in final_state and final_state["response"]:
        return final_state["response"]
    
    # Fallback if it's the old state format
    if "messages" in final_state and len(final_state["messages"]) > 0:
        return final_state["messages"][-1].content
        
    return "No response generated."


# `chat_id: int` is the Telegram conversation ID; `-> str` returns the active LangGraph checkpointer thread ID.
def _get_thread_id(chat_id: int) -> str:
    """Return the active LangGraph `thread_id` for this Telegram chat (defaults to `'nexus_primary'`)."""
    return _ACTIVE_THREADS.get(chat_id, "nexus_primary")


# `chat` is the Telegram Chat object receiving the typing indicator; `stop_event: asyncio.Event` signals completion.
async def _keep_typing(chat, stop_event: asyncio.Event) -> None:
    """Periodically emit Telegram's 'typing...' action every 4s while `NexusAgent` or subagents are thinking."""
    while not stop_event.is_set():
        try:
            await chat.send_action(action="typing")
        except Exception:
            pass
        try:
            # asyncio.wait_for: sleeps up to 4.0s but wakes immediately as soon as `stop_event.set()` is called
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            continue


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_middleware(update):
        return
        
    query = update.message.text
    await process_query(update, query)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_middleware(update):
        return
        
    status_msg = await update.message.reply_text("⏳ Processing voice note...")
    
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            temp_path = f.name
            
        await voice_file.download_to_drive(temp_path)
        
        # Run CPU/IO-bound Whisper transcription in a worker thread so the async loop stays responsive
        query = await asyncio.to_thread(transcribe_audio, temp_path)
        os.remove(temp_path)
        
        if not query or query.strip() == "":
            await status_msg.edit_text("No speech detected.")
            return
            
        await status_msg.edit_text(f"🗣️ *You:* {query}", parse_mode=ParseMode.MARKDOWN)
        
        await process_query(update, query)
        
    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        await status_msg.edit_text("❌ Something went wrong processing the voice note.")


async def process_query(update: Update, query: str):
    chat_id = update.effective_chat.id
    thread_id = _get_thread_id(chat_id)

    # Launch background typing heartbeat so mobile Telegram shows continuous activity during deep agent runs
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update.message.chat, stop_typing))
    
    try:
        # asyncio.to_thread: Offloads synchronous LangGraph execution to a worker thread so polling never blocks
        final_state = await asyncio.to_thread(route_content, query, None, thread_id)
        response_text = format_telegram_response(final_state)

        # Check if any HITL transactions are currently pending so mobile users know they can `/pending` or `/approve`
        pending = get_pending_transactions()
        if pending:
            tx_ids = ", ".join(f"#{tx['id']} ({tx['target_file']})" for tx in pending[:3])
            more = f" +{len(pending) - 3} more" if len(pending) > 3 else ""
            response_text += (
                f"\n\n───\n📋 *Pending HITL Edits ({len(pending)}):* {tx_ids}{more}\n"
                f"Use `/pending`, `/approve <id|all>`, or `/reject <id>`."
            )

        await _send_chunked_reply(update, response_text)
    except Exception as e:
        logger.error(f"Agent query error: {e}", exc_info=True)
        await update.message.reply_text("❌ I couldn't complete that right now, or something went wrong.")
    finally:
        stop_typing.set()
        await typing_task


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_middleware(update):
        return
    chat_id = update.effective_chat.id
    thread_id = _get_thread_id(chat_id)
    await update.message.reply_text(
        f"🧠 *Nexus Agentic Engine is online.*\n"
        f"Active thread: `{thread_id}`\n\n"
        f"• Send any text or voice note to talk to `NexusAgent`.\n"
        f"• `/new` — Start a fresh conversation thread\n"
        f"• `/pending` — List staged Vault HITL edits\n"
        f"• `/approve <id|all>` — Commit staged edit(s) to disk\n"
        f"• `/reject <id>` — Discard a staged edit",
        parse_mode=ParseMode.MARKDOWN,
    )


async def new_thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset the active LangGraph conversation thread for this Telegram chat."""
    if not await auth_middleware(update):
        return
    chat_id = update.effective_chat.id
    # Optional custom thread name (`/new primary` restores `"nexus_primary"`), otherwise mint a timestamped UUID
    arg = " ".join(context.args).strip() if context.args else ""
    if arg.lower() in ("primary", "default", "nexus_primary"):
        new_id = "nexus_primary"
    else:
        new_id = f"tg_{int(time.time())}"
    _ACTIVE_THREADS[chat_id] = new_id
    await update.message.reply_text(
        f"✨ Switched to conversation thread `{new_id}`.\n"
        f"(Tip: `/new primary` switches back to the shared desktop thread.)",
        parse_mode=ParseMode.MARKDOWN,
    )


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all pending HITL file transactions waiting in `hitl.db`."""
    if not await auth_middleware(update):
        return
    pending = get_pending_transactions()
    if not pending:
        await update.message.reply_text("✅ No pending HITL transactions in the queue.")
        return

    lines = [f"📋 *Pending HITL Transactions ({len(pending)}):*\n"]
    for tx in pending:
        reasoning = (tx.get("reasoning") or "No reasoning provided").strip()
        if len(reasoning) > 160:
            reasoning = reasoning[:157] + "..."
        lines.append(
            f"• *#{tx['id']}* [`{tx['action_type']}`] `{tx['target_file']}`\n"
            f"  _{reasoning}_"
        )
    lines.append("\nReply `/approve <id>`, `/approve all`, or `/reject <id>`.")
    await _send_chunked_reply(update, "\n".join(lines))


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve and commit a single pending HITL transaction (`/approve 42`) or all pending (`/approve all`)."""
    if not await auth_middleware(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/approve <id>` or `/approve all`", parse_mode=ParseMode.MARKDOWN)
        return

    target = context.args[0].strip().lower()
    force = len(context.args) > 1 and context.args[1].strip().lower() == "force"

    if target == "all":
        pending = get_pending_transactions()
        if not pending:
            await update.message.reply_text("✅ No pending transactions to approve.")
            return
        results: list[str] = []
        for tx in pending:
            tx_id = int(tx["id"])
            try:
                res = commit_transaction(tx_id, PROJECT_ROOT, force=force)
                results.append(f"✅ Approved *#{tx_id}* (`{res['target_file']}`)")
            except Exception as e:
                results.append(f"❌ Failed *#{tx_id}*: {e}")
        await _send_chunked_reply(update, "\n".join(results))
        return

    if not target.lstrip("#").isdigit():
        await update.message.reply_text("Usage: `/approve <id>` or `/approve all`", parse_mode=ParseMode.MARKDOWN)
        return

    tx_id = int(target.lstrip("#"))
    try:
        res = commit_transaction(tx_id, PROJECT_ROOT, force=force)
        await update.message.reply_text(
            f"✅ Committed Transaction *#{tx_id}* to `{res['target_file']}` (rev #{res['revision_id']}).",
            parse_mode=ParseMode.MARKDOWN,
        )
    except StaleBaseError as e:
        await update.message.reply_text(
            f"⚠️ {e}\nUse `/approve {tx_id} force` to overwrite disk state.",
            parse_mode=ParseMode.MARKDOWN,
        )
    except (TransactionNotFoundError, HitlCommitError) as e:
        await update.message.reply_text(f"❌ {e}")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject a pending HITL transaction (`/reject 42`)."""
    if not await auth_middleware(update):
        return
    if not context.args or not context.args[0].strip().lstrip("#").isdigit():
        await update.message.reply_text("Usage: `/reject <id>`", parse_mode=ParseMode.MARKDOWN)
        return

    tx_id = int(context.args[0].strip().lstrip("#"))
    update_transaction_status(tx_id, "rejected")
    await update.message.reply_text(f"🗑️ Rejected Transaction *#{tx_id}*.", parse_mode=ParseMode.MARKDOWN)


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env file.")
        print("Please create a bot via BotFather, add the token to .env, and try again.")
        sys.exit(1)
        
    if not ALLOWED_USER_IDS:
        print("❌ ALLOWED_USER_IDS not found in .env file.")
        print("Please add your Telegram User ID to .env (e.g., ALLOWED_USER_IDS=123456789) and try again.")
        sys.exit(1)

    # Ensure the SQLite HITL tables exist before handling `/pending` or `/approve` commands
    init_db()

    print("🚀 Starting Nexus Telegram Bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_thread_command))
    app.add_handler(CommandHandler("pending", pending_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("reject", reject_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Bot is listening...")
    app.run_polling()

if __name__ == "__main__":
    main()
