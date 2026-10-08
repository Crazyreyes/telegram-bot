import os
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


BOT_TOKEN = _required("BOT_TOKEN")
DUMP_CHAT_ID = _required("DUMP_CHAT_ID")
STREAM_LOG_CHAT_ID = _required("STREAM_LOG_CHAT_ID")
# FRIEND_GROUP_CHAT_ID = _required("FRIEND_GROUP_CHAT_ID")

TWITCH_CLIENT_ID = _required("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = _required("TWITCH_CLIENT_SECRET")

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
