import asyncio
import logging

from telegram.error import NetworkError, BadRequest, RetryAfter, TelegramError

logger = logging.getLogger(__name__)


async def send_message_with_retry(
    bot,
    chat_id: int | str,
    text: str,
    max_attempts: int = 4,
    parse_mode: str | None = None,
    **send_kwargs,
):
    """
    Send a Telegram message with timeouts and automatic retries.

    - Timeout/network error: retry with exponential backoff.
    - Telegram rate limit: wait for Telegram's specified delay.
    - Other Telegram errors: raised to the caller (permanent).

    Returns the sent message, or None if transient retries run out.
    """

    timeout_kwargs = {
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
        "pool_timeout": 5,
    }

    # Only specify a parse mode when one is provided
    if parse_mode is not None:
        send_kwargs["parse_mode"] = parse_mode

    # Allow callers to override the default timeouts.
    timeout_kwargs.update(send_kwargs)

    for attempt in range(1, max_attempts + 1):
        try:
            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                **timeout_kwargs,
            )

            logger.info(
                "Telegram message sent successfully " "(chat_id=%s, attempt=%s/%s)",
                chat_id,
                attempt,
                max_attempts,
            )

            return message

        except RetryAfter as exc:
            if attempt == max_attempts:
                logger.error(
                    "Telegram rate limit prevented delivery after "
                    "%s attempts (chat_id=%s).",
                    max_attempts,
                    chat_id,
                )
                return None

            delay = exc.retry_after + 1

            logger.warning(
                "Telegram rate limit hit. Retrying in %s seconds " "(attempt=%s/%s).",
                delay,
                attempt,
                max_attempts,
            )

            await asyncio.sleep(delay)

        except BadRequest as exc:
            logger.error(
                "Telegram rejected the message (chat_id=%s): %s",
                chat_id,
                exc,
            )
            raise

        except NetworkError as exc:
            if attempt == max_attempts:
                logger.error(
                    "Telegram message failed after %s attempts " "(chat_id=%s): %s",
                    max_attempts,
                    chat_id,
                    exc,
                )
                return None

            # Retry after 1, 2, then 4 seconds.
            delay = min(2 ** (attempt - 1), 30)

            logger.warning(
                "Telegram network error: %s. Retrying in %s seconds "
                "(attempt=%s/%s).",
                exc,
                delay,
                attempt,
                max_attempts,
            )

            await asyncio.sleep(delay)

        except TelegramError:
            # Errors such as an invalid chat ID generally won't
            # be fixed by immediately sending the same request again.
            logger.exception(
                "Telegram rejected the message (chat_id=%s).",
                chat_id,
            )
            raise

    return None
