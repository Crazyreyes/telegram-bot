import asyncio
import logging

from telegram.constants import ParseMode
from telegram.error import TelegramError

import db
from telegram_utils import send_message_with_retry

logger = logging.getLogger(__name__)

# Worker tuning. Named constants so the values are easy to find and change.
POLL_INTERVAL_SECONDS = 10
MAX_ATTEMPTS = 5
LEASE_SECONDS = 300
BATCH_SIZE = 10
RETAIN_SENT_DAYS = 30
CLEANUP_INTERVAL_SECONDS = 3600
CLEANUP_EVERY_CYCLES = CLEANUP_INTERVAL_SECONDS // POLL_INTERVAL_SECONDS

# Backoff after each failed send (seconds), capped at one hour.
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 3600


def backoff_seconds(attempts: int) -> int:
    """Seconds to wait before the next try after `attempts` failed sends."""
    return min(BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), BACKOFF_MAX_SECONDS)


async def process_row(bot, row) -> None:
    """Send one claimed outbox row and record the outcome."""
    row_id = row["id"]
    parse_mode = ParseMode(row["parse_mode"]) if row["parse_mode"] else None

    try:
        result = await send_message_with_retry(
            bot,
            chat_id=row["chat_id"],
            text=row["message_text"],
            parse_mode=parse_mode,
        )
    except TelegramError as exc:
        # Telegram rejected the message itself; retrying will not help.
        await _record_failure(row, str(exc), permanent=True)
        return
    except Exception as exc:
        # One bad row must never take the worker down.
        logger.exception("[OUTBOX] Unexpected error sending row %s", row_id)
        await _record_failure(row, str(exc))
        return

    if result is not None:
        await db.mark_outbox_sent(row_id)
        logger.info("[OUTBOX] Sent queued notification (outbox_id=%s).", row_id)
        return

    await _record_failure(
        row,
        "send_message_with_retry returned None after all retries",
    )


async def _record_failure(row, error: str, permanent: bool = False) -> None:
    """Schedule a retry for a failed row, or give up after MAX_ATTEMPTS
    or on a permanent error."""
    attempts = row["attempts"] + 1

    if permanent or attempts >= MAX_ATTEMPTS:
        await db.mark_outbox_failed(row["id"], attempts=attempts, error=error)
        logger.warning(
            "[OUTBOX] Giving up on queued notification (outbox_id=%s) "
            "after %s attempts: %s",
            row["id"],
            attempts,
            error,
        )
        return

    delay = backoff_seconds(attempts)
    await db.schedule_outbox_retry(
        row["id"],
        attempts=attempts,
        error=error,
        backoff_seconds=delay,
    )
    logger.warning(
        "[OUTBOX] Failed to send queued notification (outbox_id=%s), "
        "retrying in %s seconds (attempt %s/%s).",
        row["id"],
        delay,
        attempts,
        MAX_ATTEMPTS,
    )


async def process_pending_rows(bot) -> int:
    """Claim due rows and send them. Returns how many rows were processed."""
    rows = await db.claim_outbox_rows(limit=BATCH_SIZE, lease_seconds=LEASE_SECONDS)

    for row in rows:
        try:
            await process_row(bot, row)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One bad row must not stop the rest of the batch.
            logger.exception("[OUTBOX] Error processing row %s", row["id"])

    return len(rows)


async def run_outbox_worker(bot) -> None:
    """Poll the outbox forever, sending queued notifications."""
    logger.info("[OUTBOX] Worker started")

    cycle = 0

    try:
        while True:
            try:
                await process_pending_rows(bot)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[OUTBOX] Error in worker cycle")

            if cycle % CLEANUP_EVERY_CYCLES == 0:
                try:
                    deleted = await db.delete_old_sent_outbox_rows(
                        retain_days=RETAIN_SENT_DAYS
                    )
                    if deleted:
                        logger.info(
                            "[OUTBOX] Cleaned up %s sent rows older than %s days.",
                            deleted,
                            RETAIN_SENT_DAYS,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("[OUTBOX] Error cleaning up sent rows")

            cycle += 1

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("[OUTBOX] Worker stopping")
        raise
