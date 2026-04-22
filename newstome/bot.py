import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import load_config, secrets
from .pipeline import build_digest
from .telegram import format_digest, send_message


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I send you a morning news digest.\n"
        "Commands:\n"
        "  /digest - fetch and send the latest digest now\n"
        "  /status - show your chat ID"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Your chat_id: {chat_id}")


async def digest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text("Fetching the latest news. This takes 1-2 minutes...")
    cfg = load_config()
    summaries, _ = await asyncio.to_thread(build_digest, False)
    if not summaries:
        await update.message.reply_text("No new stories since your last digest.")
        return
    text = format_digest(summaries, cfg.telegram.digest_title)
    await asyncio.to_thread(send_message, text, chat_id)


def build_app() -> Application:
    app = Application.builder().token(secrets.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("digest", digest_cmd))
    return app
