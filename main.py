import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from telegram.ext import Application
from telegram.error import NetworkError, TelegramError

from config import BOT_TOKEN, DUMP_CHAT_ID
from db import close_db, init_db
from outbox_worker import run_outbox_worker
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
            backupCount=10,
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


async def post_init(application):
    await init_db()

    me = await application.bot.get_me()
    application.bot_data["username"] = me.username
    logger.info("Reez Bot is up and ready to go!")
    try:
        await send_message_with_retry(
            application.bot,
            chat_id=DUMP_CHAT_ID,
            text="Reez Bot just started up!",
        )
    except TelegramError:
        # A rejected startup notice must not stop the bot starting.
        logger.exception("Startup notice rejected.")
    twitch_task = asyncio.create_task(start_twitch_monitor(application.bot))
    application.bot_data["twitch_task"] = twitch_task

    outbox_task = asyncio.create_task(run_outbox_worker(application.bot))
    application.bot_data["outbox_task"] = outbox_task


async def post_stop(application):
    for key, label in (
        ("twitch_task", "[TWITCH] Monitor stopped"),
        ("outbox_task", "[OUTBOX] Worker stopped"),
    ):
        task = application.bot_data.get(key)

        if task:
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                logger.info(label)

    await close_db()


# Register the handler
app.add_error_handler(error_handler)
app.post_init = post_init
app.post_stop = post_stop

if __name__ == "__main__":
    app.run_polling()
