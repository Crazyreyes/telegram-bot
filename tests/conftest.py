import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Dummy credentials so `pytest` runs with no real secrets configured.
# config.py requires every variable at import time, so the tests set
# placeholders here before any project module is imported.
# Real values in the environment win over these defaults.
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("STREAM_LOG_CHAT_ID", "123456")
os.environ.setdefault("DUMP_CHAT_ID", "123456")
os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("TWITCH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("TWITCH_STREAMERS", "streamer_one,streamer_two")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://user:password@localhost:5432/testdb"
)
