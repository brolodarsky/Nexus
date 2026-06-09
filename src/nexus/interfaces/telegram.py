"""
telegram.py — Telegram bot interface for the Nexus Engine.
Provides remote access to the Vault Reader agent via text and voice messages.
"""
import os
import sys
import logging
import urllib.parse
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
from nexus.agents.router.api import route_content
from nexus.core.audio import transcribe_audio

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS_STR = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [int(x.strip()) for x in ALLOWED_USER_IDS_STR.split(",") if x.strip()]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def auth_middleware(update: Update) -> bool:
    """Check if the user is authorized."""
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        logger.warning(f"Unauthorized access attempt from user ID {user_id}")
        if update.message:
            await update.message.reply_text("⛔ Unauthorized access.")
        return False
    return True

def format_telegram_response(final_state: dict) -> str:
    """Format the LangGraph final state into a Telegram-friendly Markdown string."""
    # We are omitting sources in Telegram for now because obsidian:// deep links 
    # do not always render properly in mobile Telegram clients.
    if "response" in final_state:
        # It's from the router
        return final_state["response"]
    
    # Fallback if it's the old state format
    if "messages" in final_state and len(final_state["messages"]) > 0:
        return final_state["messages"][-1].content
        
    return "No response generated."

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
        
        query = transcribe_audio(temp_path)
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
    # Send typing action
    await update.message.chat.send_action(action="typing")
    
    try:
        # We run the synchronous RAG pipeline in the same thread for simplicity here.
        # This will block the event loop for the duration of the query,
        # but since it's a personal bot for one user, this is acceptable.
        # We don't currently pass thread_id to router, but we could in the future.
        final_state = route_content(query)
        response_text = format_telegram_response(final_state)
        
        # Try sending with Markdown parsing first
        try:
            await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                logger.warning("Markdown parse failed, falling back to raw text.")
                await update.message.reply_text(response_text, disable_web_page_preview=True)
            else:
                raise e
    except Exception as e:
        logger.error(f"RAG query error: {e}", exc_info=True)
        await update.message.reply_text("❌ I couldn't find that right now, or something went wrong.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_middleware(update):
        return
    await update.message.reply_text("🧠 Nexus Agentic Engine is online. Send me a text or voice message to query your vault.")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env file.")
        print("Please create a bot via BotFather, add the token to .env, and try again.")
        sys.exit(1)
        
    if not ALLOWED_USER_IDS:
        print("❌ ALLOWED_USER_IDS not found in .env file.")
        print("Please add your Telegram User ID to .env (e.g., ALLOWED_USER_IDS=123456789) and try again.")
        sys.exit(1)

    print("🚀 Starting Brain Telegram Bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Bot is listening...")
    app.run_polling()

if __name__ == "__main__":
    main()
