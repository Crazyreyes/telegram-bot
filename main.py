import asyncio
import os
import logging
from logging.handlers import RotatingFileHandler

from telegram.ext import Application, MessageHandler, filters
from telegram.error import NetworkError

from config import BOT_TOKEN, STREAM_LOG_CHAT_ID
from db import close_db, init_db
from telegram_utils import send_message_with_retry
from twitch_monitor import start_twitch_monitor

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            "logs/bot.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=100,
            encoding="utf-8",
        ),
    ],
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = Application.builder().token(BOT_TOKEN).build()


async def error_handler(update, context):
    error = context.error

    if error is None:
        logger.warning("[TELEGRAM] Error handler called without an exception.")
        return

    if isinstance(error, NetworkError):
        logger.warning(
            "[TELEGRAM] Network error during polling: %s",
            error,
        )
        return

    logger.error(
        "[TELEGRAM] Unhandled exception",
        exc_info=error,
    )


# Logs every message the bot receives
async def log_messages(update, context):
    chat = update.effective_chat
    print("=" * 40)
    print(f"Chat ID: {chat.id}")
    print(f"Chat Type: {chat.type}")
    print(f"Chat Title: {chat.title}")
    print(f"Username: {chat.username}")
    if update.message:
        print(f"Message: {update.message.text}")


async def post_init(application):
    await init_db()

    me = await application.bot.get_me()
    application.bot_data["username"] = me.username
    logger.info("Reez Bot is up and ready to go!")
    await send_message_with_retry(
        application.bot,
        chat_id=STREAM_LOG_CHAT_ID,
        text="Reez Bot just started up!",
    )
    twitch_task = asyncio.create_task(start_twitch_monitor(application.bot))
    application.bot_data["twitch_task"] = twitch_task


async def post_stop(application):
    twitch_task = application.bot_data.get("twitch_task")

    if twitch_task:
        twitch_task.cancel()

        try:
            await twitch_task
        except asyncio.CancelledError:
            logger.info("[TWITCH] Monitor stopped")

    await close_db()


# Register the handler
app.add_handler(MessageHandler(filters.ALL, log_messages))
app.add_error_handler(error_handler)
app.post_init = post_init
app.post_stop = post_stop

app.run_polling()
