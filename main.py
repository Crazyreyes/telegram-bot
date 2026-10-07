from telegram.ext import (
    Application,
    MessageHandler,
    filters,
)
import asyncio
import os
from dotenv import load_dotenv
from twitch_monitor import start_twitch_monitor

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
STREAM_LOG_CHAT_ID = os.getenv("STREAM_LOG_CHAT_ID")

app = Application.builder().token(BOT_TOKEN).build()


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
    print("Reez Bot is up and ready to go!")
    await application.bot.send_message(
        STREAM_LOG_CHAT_ID,
        "Reez Bot just restarted",
        parse_mode="HTML"
    )
    asyncio.create_task(start_twitch_monitor(application.bot))


app.post_init = post_init

# Register the handler
app.add_handler(MessageHandler(filters.ALL, log_messages))

app.run_polling()