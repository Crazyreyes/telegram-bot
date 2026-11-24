import os
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _required_list(name: str) -> list[str]:
    value = _required(name)
    items = [item.strip() for item in value.split(",")]
    items = [item for item in items if item]
    if not items:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return items


BOT_TOKEN = _required("BOT_TOKEN")
STREAM_LOG_CHAT_ID = _required("STREAM_LOG_CHAT_ID")

# Chat for the bot's own messages (e.g. startup notices). Stream notifications
# go to STREAM_LOG_CHAT_ID instead.
DUMP_CHAT_ID = _required("DUMP_CHAT_ID")

TWITCH_CLIENT_ID = _required("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = _required("TWITCH_CLIENT_SECRET")

# Comma-separated Twitch usernames to monitor, e.g. "streamer_one,streamer_two".
# Kept in configuration (not in code) so the monitored channels stay private.
# Stored as {"username": ...} dicts to match the monitor's existing shape.
TWITCH_STREAMERS = [
    {"username": name} for name in _required_list("TWITCH_STREAMERS")
]

# Some hosts provide DATABASE_URL directly. The individual variables are
# also supported so the bot works with standard PostgreSQL hosting panels.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    pg_host = _required("PGHOST")
    pg_port = _required("PGPORT")
    pg_database = _required("PGDATABASE")
    pg_user = _required("PGUSER")
    pg_password = _required("PGPASSWORD")
    DATABASE_URL = (
        f"postgresql://{quote(pg_user, safe='')}:{quote(pg_password, safe='')}"
        f"@{pg_host}:{pg_port}/{quote(pg_database, safe='')}"
    )
