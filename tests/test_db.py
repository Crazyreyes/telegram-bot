import sys
from datetime import timedelta
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

    def __init__(
        self,
        event_id=42,
        fail_outbox=False,
        fail_fetchval_times=0,
        execute_result="OK",
        fetch_rows=None,
    ):
        self.event_id = event_id
        self.fail_outbox = fail_outbox
        self.fail_fetchval_times = fail_fetchval_times
        self.execute_result = execute_result
        self.fetch_rows = fetch_rows if fetch_rows is not None else []
        self.fetchvals = []
        self.executes = []
        self.fetches = []
        self.transaction_ctx = FakeTransaction()

    def transaction(self):
        return self.transaction_ctx

    async def fetchval(self, sql, *args):
        self.fetchvals.append((sql, args))
        if self.fail_fetchval_times > 0:
            self.fail_fetchval_times -= 1
            raise TimeoutError("query timed out")
        return self.event_id

    async def fetch(self, sql, *args):
        self.fetches.append((sql, args))
        return self.fetch_rows

    async def execute(self, sql, *args):
        self.executes.append((sql, args))
        if self.fail_outbox and "INSERT INTO outbox" in sql:
            raise RuntimeError("outbox insert failed")
        return self.execute_result


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


@pytest.mark.asyncio
async def test_log_twitch_event_retries_after_timeout(monkeypatch):
    conn = FakeConnection(event_id=42, fail_fetchval_times=1)
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(db.asyncio, "sleep", fake_sleep)

    event_id = await db.log_twitch_event(
        twitch_username="teststreamer",
        event_type="LIVE",
        message="TestStreamer is now LIVE!",
    )

    assert event_id == 42

    # The first attempt timed out and rolled back; the second succeeded.
    assert len(conn.fetchvals) == 2
    assert pool.acquire_count == 2
    assert conn.transaction_ctx.committed is True

    assert sleep_calls == [1]


@pytest.mark.asyncio
async def test_log_twitch_event_gives_up_after_max_attempts(monkeypatch):
    conn = FakeConnection(event_id=42, fail_fetchval_times=10)
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(db.asyncio, "sleep", fake_sleep)

    with pytest.raises(TimeoutError, match="query timed out"):
        await db.log_twitch_event(
            twitch_username="teststreamer",
            event_type="LIVE",
            message="TestStreamer is now LIVE!",
        )

    # Three attempts, with a 1s then a 2s pause between them.
    assert len(conn.fetchvals) == 3
    assert pool.acquire_count == 3
    assert sleep_calls == [1, 2]


@pytest.mark.asyncio
async def test_claim_outbox_rows(monkeypatch):
    rows = [
        {
            "id": 7,
            "chat_id": "123456",
            "message_text": "TestStreamer is now LIVE!",
            "parse_mode": "HTML",
            "attempts": 0,
        }
    ]
    conn = FakeConnection(fetch_rows=rows)
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    claimed = await db.claim_outbox_rows(limit=5, lease_seconds=60)

    assert claimed == rows

    assert len(conn.fetches) == 1
    claim_sql, claim_args = conn.fetches[0]
    assert "UPDATE outbox" in claim_sql
    assert "status = 'pending'" in claim_sql
    assert "RETURNING id, chat_id, message_text, parse_mode, attempts" in claim_sql
    assert claim_args == (5, timedelta(seconds=60))


@pytest.mark.asyncio
async def test_mark_outbox_sent(monkeypatch):
    conn = FakeConnection()
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    await db.mark_outbox_sent(7)

    assert len(conn.executes) == 1
    sql, args = conn.executes[0]
    assert "UPDATE outbox SET status = 'sent'" in sql
    assert "sent_at = NOW()" in sql
    assert args == (7,)


@pytest.mark.asyncio
async def test_schedule_outbox_retry(monkeypatch):
    conn = FakeConnection()
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    await db.schedule_outbox_retry(
        7, attempts=2, error="Telegram down", backoff_seconds=120
    )

    assert len(conn.executes) == 1
    sql, args = conn.executes[0]
    assert "next_attempt_at = NOW() + $4" in sql
    assert "status = 'pending'" in sql
    assert args == (7, 2, "Telegram down", timedelta(seconds=120))


@pytest.mark.asyncio
async def test_mark_outbox_failed(monkeypatch):
    conn = FakeConnection()
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    await db.mark_outbox_failed(7, attempts=5, error="Telegram down")

    assert len(conn.executes) == 1
    sql, args = conn.executes[0]
    assert "status = 'failed'" in sql
    assert "next_attempt_at = NULL" in sql
    assert args == (7, 5, "Telegram down")


@pytest.mark.asyncio
async def test_delete_old_sent_outbox_rows(monkeypatch):
    conn = FakeConnection(execute_result="DELETE 7")
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    deleted = await db.delete_old_sent_outbox_rows(retain_days=30)

    assert deleted == 7

    assert len(conn.executes) == 1
    sql, args = conn.executes[0]
    assert "DELETE FROM outbox" in sql
    assert "status = 'sent'" in sql
    assert args == (timedelta(days=30),)


@pytest.mark.asyncio
async def test_delete_old_sent_outbox_rows_unparsable_status_returns_zero(
    monkeypatch,
):
    conn = FakeConnection(execute_result="OK")
    pool = FakePool(conn)
    monkeypatch.setattr(db, "_pool", pool)

    deleted = await db.delete_old_sent_outbox_rows(retain_days=30)

    assert deleted == 0
