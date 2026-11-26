import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

import telegram_utils
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut, Forbidden


@pytest.mark.asyncio
async def test_network_error_retries_and_then_succeeds(monkeypatch):
    """Retry network errors with exponential backoff, then succeed."""

    sent_message = object()

    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                NetworkError("Connection lost"),
                NetworkError("Connection lost"),
                sent_message,
            ]
        )
    )

    sleep_mock = AsyncMock()
    monkeypatch.setattr(telegram_utils.asyncio, "sleep", sleep_mock)

    result = await telegram_utils.send_message_with_retry(
        bot,
        chat_id=12345,
        text="Test notification",
    )

    assert result is sent_message
    assert bot.send_message.await_count == 3

    assert sleep_mock.await_args_list == [
        call(1),
        call(2),
    ]


@pytest.mark.asyncio
async def test_rate_limit_waits_before_retrying(monkeypatch):
    """Respect Telegram's RetryAfter delay."""

    sent_message = object()

    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                RetryAfter(2),
                sent_message,
            ]
        )
    )

    sleep_mock = AsyncMock()
    monkeypatch.setattr(telegram_utils.asyncio, "sleep", sleep_mock)

    result = await telegram_utils.send_message_with_retry(
        bot,
        chat_id=12345,
        text="Test notification",
    )

    assert result is sent_message
    assert bot.send_message.await_count == 2

    # The helper adds one second to Telegram's requested delay.
    sleep_mock.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_html_parse_mode_is_passed_correctly():
    """Send HTML-formatted messages using ParseMode.HTML."""

    sent_message = object()

    bot = SimpleNamespace(send_message=AsyncMock(return_value=sent_message))

    result = await telegram_utils.send_message_with_retry(
        bot,
        chat_id=12345,
        text="<b>Test notification</b>",
        parse_mode=ParseMode.HTML,
    )

    assert result is sent_message

    bot.send_message.assert_awaited_once_with(
        chat_id=12345,
        text="<b>Test notification</b>",
        parse_mode=ParseMode.HTML,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
        pool_timeout=5,
    )


@pytest.mark.asyncio
async def test_bad_request_raises_without_retrying(monkeypatch):
    """Raise invalid messages instead of returning None for them."""

    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=BadRequest("Can't parse entities"))
    )

    sleep_mock = AsyncMock()
    monkeypatch.setattr(telegram_utils.asyncio, "sleep", sleep_mock)

    with pytest.raises(BadRequest):
        await telegram_utils.send_message_with_retry(
            bot,
            chat_id=12345,
            text="<b>Invalid HTML",
            parse_mode=ParseMode.HTML,
        )

    bot.send_message.assert_awaited_once()
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_telegram_error_raises_without_retrying(monkeypatch):
    """Raise other permanent Telegram errors (e.g. Forbidden)."""

    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=Forbidden("Bot was blocked"))
    )

    sleep_mock = AsyncMock()
    monkeypatch.setattr(telegram_utils.asyncio, "sleep", sleep_mock)

    with pytest.raises(Forbidden):
        await telegram_utils.send_message_with_retry(
            bot,
            chat_id=12345,
            text="Test notification",
        )

    bot.send_message.assert_awaited_once()
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_exhaustion_returns_none(monkeypatch):
    """Return None after all network retry attempts fail."""

    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=NetworkError("Telegram unavailable"))
    )

    sleep_mock = AsyncMock()
    monkeypatch.setattr(telegram_utils.asyncio, "sleep", sleep_mock)

    result = await telegram_utils.send_message_with_retry(
        bot,
        chat_id=12345,
        text="Test notification",
        max_attempts=4,
    )

    assert result is None
    assert bot.send_message.await_count == 4

    assert sleep_mock.await_args_list == [
        call(1),
        call(2),
        call(4),
    ]


@pytest.mark.asyncio
async def test_timeout_is_retried_and_timeout_values_are_passed(
    monkeypatch,
):
    """Retry timeouts and pass the configured timeout values."""

    sent_message = object()

    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                TimedOut("Telegram request timed out"),
                sent_message,
            ]
        )
    )

    sleep_mock = AsyncMock()
    monkeypatch.setattr(telegram_utils.asyncio, "sleep", sleep_mock)

    result = await telegram_utils.send_message_with_retry(
        bot,
        chat_id=12345,
        text="Test notification",
    )

    assert result is sent_message
    assert bot.send_message.await_count == 2

    sleep_mock.assert_awaited_once_with(1)

    for sent_call in bot.send_message.await_args_list:
        assert sent_call.kwargs["connect_timeout"] == 5
        assert sent_call.kwargs["read_timeout"] == 10
        assert sent_call.kwargs["write_timeout"] == 10
        assert sent_call.kwargs["pool_timeout"] == 5
