import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

from config import DATABASE_URL

_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS twitch_events (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL,
    twitch_username TEXT NOT NULL,
    event_type TEXT NOT NULL,
    twitch_display_name TEXT,
    stream_id TEXT,
    title TEXT,
    game_name TEXT,
    old_title TEXT,
    old_game_name TEXT,
    message TEXT,
    raw_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_twitch_events_username_detected ON twitch_events (twitch_username, detected_at DESC);
"""


async def init_db() -> None:
    global _pool
    if _pool is not None:
        return

    _pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _require_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database has not been initialized.")
    return _pool


async def log_twitch_event(
    *,
    twitch_username: str,
    event_type: str,
    twitch_display_name: str | None = None,
    stream_id: str | None = None,
    title: str | None = None,
    game_name: str | None = None,
    old_title: str | None = None,
    old_game_name: str | None = None,
    message: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO twitch_events
                (detected_at, twitch_username, event_type, twitch_display_name,
                 stream_id, title, game_name, old_title, old_game_name, message, raw_payload)
            VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
            """,
            twitch_username,
            event_type,
            twitch_display_name,
            stream_id,
            title,
            game_name,
            old_title,
            old_game_name,
            message,
            json.dumps(raw_payload) if raw_payload is not None else None,
        )
