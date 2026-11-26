import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import db


class FakeTransaction:
    """Stands in for asyncpg's transaction context manager."""

    def __init__(self):
        self.entered = False
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True
        return False


class FakeConnection:
    """Records every query and can fail the outbox insert on demand."""

    def __init__(self, event_id=42, fail_outbox=False):
        self.event_id = event_id
        self.fail_outbox = fail_outbox
        self.fetchvals = []
        self.executes = []
        self.transaction_ctx = FakeTransaction()

    def transaction(self):
        return self.transaction_ctx

    async def fetchval(self, sql, *args):
        self.fetchvals.append((sql, args))
        return self.event_id

    async def execute(self, sql, *args):
        self.executes.append((sql, args))
        if self.fail_outbox and "INSERT INTO outbox" in sql:
            raise RuntimeError("outbox insert failed")
        return "OK"


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn
        self.acquire_count = 0

    def acquire(self):
        self.acquire_count += 1
        return FakeAcquire(self.conn)


@pytest.mark.asyncio
async def test_log_twitch_event_inserts_event_only(monkeypatch):
    conn = FakeConnection(event_id=42)
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    event_id = await db.log_twitch_event(
        twitch_username="teststreamer",
        event_type="STARTUP_OFFLINE",
        message="Detected offline during monitor startup.",
    )

    assert event_id == 42

    assert len(conn.fetchvals) == 1
    assert "INSERT INTO twitch_events" in conn.fetchvals[0][0]
    assert "RETURNING id" in conn.fetchvals[0][0]

    # No notification given, so no outbox row is written.
    assert conn.executes == []

    assert conn.transaction_ctx.entered is True
    assert conn.transaction_ctx.committed is True
    assert pool.acquire_count == 1


@pytest.mark.asyncio
async def test_log_twitch_event_with_notification_inserts_both_in_one_transaction(
    monkeypatch,
):
    conn = FakeConnection(event_id=42)
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    event_id = await db.log_twitch_event(
        twitch_username="teststreamer",
        event_type="LIVE",
        message="TestStreamer is now LIVE!",
        notify_chat_id="123456",
        notify_message="TestStreamer is now LIVE!",
        notify_parse_mode="HTML",
    )

    assert event_id == 42

    # Both writes happen inside a single transaction, on one connection.
    assert conn.transaction_ctx.entered is True
    assert conn.transaction_ctx.committed is True
    assert conn.transaction_ctx.rolled_back is False
    assert pool.acquire_count == 1

    # Event insert first, outbox insert second.
    assert len(conn.fetchvals) == 1
    assert "INSERT INTO twitch_events" in conn.fetchvals[0][0]

    assert len(conn.executes) == 1
    outbox_sql, outbox_args = conn.executes[0]
    assert "INSERT INTO outbox" in outbox_sql
    assert outbox_args == (42, "123456", "TestStreamer is now LIVE!", "HTML")


@pytest.mark.asyncio
async def test_log_twitch_event_notification_needs_chat_and_message(monkeypatch):
    monkeypatch.setattr(db, "_pool", None)

    with pytest.raises(ValueError, match="must be given together"):
        await db.log_twitch_event(
            twitch_username="teststreamer",
            event_type="LIVE",
            notify_chat_id="123456",
        )

    with pytest.raises(ValueError, match="must be given together"):
        await db.log_twitch_event(
            twitch_username="teststreamer",
            event_type="LIVE",
            notify_message="TestStreamer is now LIVE!",
        )


@pytest.mark.asyncio
async def test_log_twitch_event_rolls_back_when_outbox_insert_fails(monkeypatch):
    conn = FakeConnection(event_id=42, fail_outbox=True)
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    with pytest.raises(RuntimeError, match="outbox insert failed"):
        await db.log_twitch_event(
            twitch_username="teststreamer",
            event_type="LIVE",
            message="TestStreamer is now LIVE!",
            notify_chat_id="123456",
            notify_message="TestStreamer is now LIVE!",
            notify_parse_mode="HTML",
        )

    # The event insert ran, but the transaction rolled back instead of
    # committing, so the event row is not saved either.
    assert len(conn.fetchvals) == 1
    assert conn.transaction_ctx.committed is False
    assert conn.transaction_ctx.rolled_back is True


@pytest.mark.asyncio
async def test_log_twitch_event_without_pool_raises(monkeypatch):
    monkeypatch.setattr(db, "_pool", None)

    with pytest.raises(RuntimeError, match="Database has not been initialized"):
        await db.log_twitch_event(
            twitch_username="teststreamer",
            event_type="LIVE",
        )


def test_schema_creates_outbox_table():
    for fragment in [
        "CREATE TABLE IF NOT EXISTS outbox",
        "twitch_event_id BIGINT REFERENCES twitch_events (id)",
        "chat_id TEXT NOT NULL",
        "message_text TEXT NOT NULL",
        "parse_mode TEXT",
        "status TEXT NOT NULL DEFAULT 'pending'",
        "attempts INT NOT NULL DEFAULT 0",
        "last_error TEXT",
        "next_attempt_at TIMESTAMPTZ",
        "sent_at TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS idx_outbox_pending",
    ]:
        assert fragment in db.SCHEMA_SQL


@pytest.mark.asyncio
async def test_init_db_runs_schema(monkeypatch):
    conn = FakeConnection()
    pool = FakePool(conn)

    async def fake_create_pool(**kwargs):
        return pool

    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db.asyncpg, "create_pool", fake_create_pool)

    await db.init_db()

    assert db._pool is pool
    assert len(conn.executes) == 1
    assert conn.executes[0][0] == db.SCHEMA_SQL
