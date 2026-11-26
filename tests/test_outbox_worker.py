import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from telegram.constants import ParseMode
from telegram.error import BadRequest

import db
import outbox_worker


def make_row(**overrides):
    row = {
        "id": 7,
        "chat_id": "123456",
        "message_text": "TestStreamer is now LIVE!",
        "parse_mode": "HTML",
        "attempts": 0,
    }
    row.update(overrides)
    return row


def test_backoff_seconds():
    assert outbox_worker.backoff_seconds(0) == 60
    assert outbox_worker.backoff_seconds(1) == 60
    assert outbox_worker.backoff_seconds(2) == 120
    assert outbox_worker.backoff_seconds(3) == 240
    assert outbox_worker.backoff_seconds(4) == 480
    assert outbox_worker.backoff_seconds(5) == 960

    # Capped at one hour.
    assert outbox_worker.backoff_seconds(10) == 3600


@pytest.mark.asyncio
async def test_process_row_sends_and_marks_sent(monkeypatch):
    row = make_row()
    sent_calls = []
    marked_sent = []

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        sent_calls.append(
            {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        )
        return object()

    async def fake_mark_sent(row_id):
        marked_sent.append(row_id)

    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "mark_outbox_sent", fake_mark_sent)

    await outbox_worker.process_row(object(), row)

    assert sent_calls == [
        {
            "chat_id": "123456",
            "text": "TestStreamer is now LIVE!",
            "parse_mode": ParseMode.HTML,
        }
    ]
    assert marked_sent == [7]


@pytest.mark.asyncio
async def test_process_row_without_parse_mode(monkeypatch):
    row = make_row(parse_mode=None)
    sent_calls = []
    marked_sent = []

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        sent_calls.append(parse_mode)
        return object()

    async def fake_mark_sent(row_id):
        marked_sent.append(row_id)

    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "mark_outbox_sent", fake_mark_sent)

    await outbox_worker.process_row(object(), row)

    assert sent_calls == [None]
    assert marked_sent == [7]


@pytest.mark.asyncio
async def test_process_row_permanent_error_marks_failed_at_once(monkeypatch):
    row = make_row()
    send_calls = []
    retried = []
    marked_failed = []

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        send_calls.append(text)
        raise BadRequest("Can't parse entities")

    async def fake_schedule(row_id, *, attempts, error, backoff_seconds):
        retried.append(row_id)

    async def fake_mark_failed(row_id, *, attempts, error):
        marked_failed.append(
            {"row_id": row_id, "attempts": attempts, "error": error}
        )

    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "schedule_outbox_retry", fake_schedule)
    monkeypatch.setattr(db, "mark_outbox_failed", fake_mark_failed)

    await outbox_worker.process_row(object(), row)

    # Sent once, then given up on: no retry scheduled.
    assert len(send_calls) == 1
    assert retried == []
    assert len(marked_failed) == 1
    assert marked_failed[0]["row_id"] == 7
    assert marked_failed[0]["attempts"] == 1
    assert "Can't parse entities" in marked_failed[0]["error"]


@pytest.mark.asyncio
async def test_process_row_failure_schedules_retry(monkeypatch):
    row = make_row()
    retried = []
    marked_failed = []
    marked_sent = []

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        return None

    async def fake_schedule(row_id, *, attempts, error, backoff_seconds):
        retried.append(
            {
                "row_id": row_id,
                "attempts": attempts,
                "error": error,
                "backoff_seconds": backoff_seconds,
            }
        )

    async def fake_mark_failed(row_id, *, attempts, error):
        marked_failed.append(row_id)

    async def fake_mark_sent(row_id):
        marked_sent.append(row_id)

    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "schedule_outbox_retry", fake_schedule)
    monkeypatch.setattr(db, "mark_outbox_failed", fake_mark_failed)
    monkeypatch.setattr(db, "mark_outbox_sent", fake_mark_sent)

    await outbox_worker.process_row(object(), row)

    assert len(retried) == 1
    assert retried[0]["row_id"] == 7
    assert retried[0]["attempts"] == 1
    assert retried[0]["backoff_seconds"] == 60
    assert "returned None" in retried[0]["error"]
    assert marked_failed == []
    assert marked_sent == []


@pytest.mark.asyncio
async def test_process_row_failure_at_max_attempts_marks_failed(monkeypatch):
    row = make_row(attempts=4)
    retried = []
    marked_failed = []

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        return None

    async def fake_schedule(row_id, *, attempts, error, backoff_seconds):
        retried.append(row_id)

    async def fake_mark_failed(row_id, *, attempts, error):
        marked_failed.append(
            {"row_id": row_id, "attempts": attempts, "error": error}
        )

    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "schedule_outbox_retry", fake_schedule)
    monkeypatch.setattr(db, "mark_outbox_failed", fake_mark_failed)

    await outbox_worker.process_row(object(), row)

    assert retried == []
    assert len(marked_failed) == 1
    assert marked_failed[0]["row_id"] == 7
    assert marked_failed[0]["attempts"] == 5


@pytest.mark.asyncio
async def test_process_row_send_exception_schedules_retry(monkeypatch):
    row = make_row()
    retried = []

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        raise RuntimeError("Telegram down")

    async def fake_schedule(row_id, *, attempts, error, backoff_seconds):
        retried.append(
            {"row_id": row_id, "attempts": attempts, "error": error}
        )

    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "schedule_outbox_retry", fake_schedule)

    await outbox_worker.process_row(object(), row)

    assert len(retried) == 1
    assert retried[0]["row_id"] == 7
    assert retried[0]["attempts"] == 1
    assert retried[0]["error"] == "Telegram down"


@pytest.mark.asyncio
async def test_process_pending_rows_claims_and_processes(monkeypatch):
    rows = [make_row(id=7), make_row(id=8, message_text="Another update")]
    claims = []
    sent = []
    marked_sent = []

    async def fake_claim(*, limit, lease_seconds):
        claims.append({"limit": limit, "lease_seconds": lease_seconds})
        return rows

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        sent.append(text)
        return object()

    async def fake_mark_sent(row_id):
        marked_sent.append(row_id)

    monkeypatch.setattr(db, "claim_outbox_rows", fake_claim)
    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "mark_outbox_sent", fake_mark_sent)

    processed = await outbox_worker.process_pending_rows(object())

    assert processed == 2
    assert claims == [
        {
            "limit": outbox_worker.BATCH_SIZE,
            "lease_seconds": outbox_worker.LEASE_SECONDS,
        }
    ]
    assert sent == ["TestStreamer is now LIVE!", "Another update"]
    assert marked_sent == [7, 8]


@pytest.mark.asyncio
async def test_process_pending_rows_continues_after_row_error(monkeypatch):
    rows = [make_row(id=7), make_row(id=8)]
    marked_sent = []

    async def fake_claim(*, limit, lease_seconds):
        return rows

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        return object()

    async def fake_mark_sent(row_id):
        if row_id == 7:
            raise RuntimeError("status update failed")
        marked_sent.append(row_id)

    monkeypatch.setattr(db, "claim_outbox_rows", fake_claim)
    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)
    monkeypatch.setattr(db, "mark_outbox_sent", fake_mark_sent)

    processed = await outbox_worker.process_pending_rows(object())

    # The first row failed, but the second was still sent and marked.
    assert processed == 2
    assert marked_sent == [8]


@pytest.mark.asyncio
async def test_process_pending_rows_empty(monkeypatch):
    sent = []

    async def fake_claim(*, limit, lease_seconds):
        return []

    async def fake_send(bot, chat_id, text, parse_mode=None, **kwargs):
        sent.append(text)
        return object()

    monkeypatch.setattr(db, "claim_outbox_rows", fake_claim)
    monkeypatch.setattr(outbox_worker, "send_message_with_retry", fake_send)

    processed = await outbox_worker.process_pending_rows(object())

    assert processed == 0
    assert sent == []


@pytest.mark.asyncio
async def test_run_worker_polls_until_sleep_error(monkeypatch):
    cycles = []
    cleanups = []
    sleep_calls = []

    async def fake_process(bot):
        cycles.append(bot)
        return 0

    async def fake_cleanup(*, retain_days):
        cleanups.append(retain_days)
        return 0

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) == 2:
            raise RuntimeError("stop the loop")

    monkeypatch.setattr(outbox_worker, "process_pending_rows", fake_process)
    monkeypatch.setattr(db, "delete_old_sent_outbox_rows", fake_cleanup)
    monkeypatch.setattr(outbox_worker.asyncio, "sleep", fake_sleep)

    bot = object()

    with pytest.raises(RuntimeError, match="stop the loop"):
        await outbox_worker.run_outbox_worker(bot)

    assert cycles == [bot, bot]
    assert sleep_calls == [
        outbox_worker.POLL_INTERVAL_SECONDS,
        outbox_worker.POLL_INTERVAL_SECONDS,
    ]

    # Cleanup runs on cycle 0.
    assert cleanups == [outbox_worker.RETAIN_SENT_DAYS]


@pytest.mark.asyncio
async def test_run_worker_cleans_up_every_n_cycles(monkeypatch):
    monkeypatch.setattr(outbox_worker, "CLEANUP_EVERY_CYCLES", 2)

    cycles = []
    cleanups = []
    sleep_calls = []

    async def fake_process(bot):
        cycles.append(bot)
        return 0

    async def fake_cleanup(*, retain_days):
        cleanups.append(retain_days)
        return 0

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) == 4:
            raise RuntimeError("stop the loop")

    monkeypatch.setattr(outbox_worker, "process_pending_rows", fake_process)
    monkeypatch.setattr(db, "delete_old_sent_outbox_rows", fake_cleanup)
    monkeypatch.setattr(outbox_worker.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="stop the loop"):
        await outbox_worker.run_outbox_worker(object())

    # Four cycles ran; cleanup ran on cycles 0 and 2.
    assert len(cycles) == 4
    assert len(cleanups) == 2
