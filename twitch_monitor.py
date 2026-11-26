import asyncio
import logging

import aiohttp
from html import escape

from config import (
    STREAM_LOG_CHAT_ID,
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    TWITCH_STREAMERS,
)
from db import log_twitch_event
from telegram_utils import send_message_with_retry
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class TwitchTokenExpiredError(Exception):
    pass


access_token = None
startup_summary = []
stream_state = {}
session: aiohttp.ClientSession | None = None


async def get_access_token():

    global access_token, session

    if session is None:
        raise RuntimeError("Twitch session is not initialized.")

    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }

    async with session.post(url, params=params) as response:
        response.raise_for_status()
        data = await response.json()
        access_token = data["access_token"]

    logger.info("[TWITCH] Access token obtained.")


def get_stream_event(previous_state, stream):
    """
    Determine what changed between the previous Twitch state
    and the current Twitch stream state.

    Returns:
        "LIVE"            - streamer went from offline to live
        "OFFLINE"         - streamer went from live to offline
        "STREAM_UPDATE"  - title or game changed
        None              - nothing changed
    """

    # Streamer is currently offline
    if stream is None:
        if previous_state["live"]:
            return "OFFLINE"

        return None

    # Streamer is currently live but was previously offline
    if not previous_state["live"]:
        return "LIVE"

    # Streamer was already live
    if (
        stream["title"] != previous_state["title"]
        or stream["game_name"] != previous_state["game"]
    ):
        return "STREAM_UPDATE"

    # Nothing changed
    return None


async def get_stream_data(username):
    global session

    if session is None:
        raise RuntimeError("Twitch session is not initialized.")

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {access_token}",
    }

    async with session.get(
        f"https://api.twitch.tv/helix/streams?user_login={username}",
        headers=headers,
    ) as response:

        if response.status == 401:
            raise TwitchTokenExpiredError()

        response.raise_for_status()
        data = await response.json()

    return data


async def check_streamer(streamer, bot):

    username = streamer["username"]

    data = await get_stream_data(username)

    is_live = len(data["data"]) > 0

    # First startup
    if username not in stream_state:
        if is_live:
            stream = data["data"][0]

            await log_twitch_event(
                twitch_username=username,
                event_type="STARTUP_LIVE",
                twitch_display_name=stream["user_name"],
                stream_id=stream.get("id"),
                title=stream["title"],
                game_name=stream["game_name"],
                message="Detected live during monitor startup.",
                raw_payload=stream,
            )
            stream_state[username] = {
                "live": True,
                "title": stream["title"],
                "game": stream["game_name"],
            }
        else:

            await log_twitch_event(
                twitch_username=username,
                event_type="STARTUP_OFFLINE",
                message="Detected offline during monitor startup.",
                raw_payload=data,
            )

            stream_state[username] = {
                "live": False,
                "title": None,
                "game": None,
            }

        startup_summary.append(
            f"{'🔴' if is_live else '⚫'} {username} - {'LIVE' if is_live else 'OFFLINE'}"
        )
        return

    state = stream_state[username]

    # Get the current stream information
    stream = data["data"][0] if is_live else None

    # Determine what happened since the previous check
    event = get_stream_event(state, stream)

    # Went live
    if event == "LIVE":
        message = ""

        message += f"🔴 <b>{escape(stream['user_name'])}</b> is now <b>LIVE!</b>\n\n"
        message += f"🎮 {escape(stream['game_name'])}\n"
        message += f"📝 {escape(stream['title'])}\n\n"
        message += f"https://twitch.tv/{stream['user_login']}"

        await log_twitch_event(
            twitch_username=username,
            event_type="LIVE",
            twitch_display_name=stream["user_name"],
            stream_id=stream.get("id"),
            title=stream["title"],
            game_name=stream["game_name"],
            message=message,
            raw_payload=stream,
            notify_chat_id=STREAM_LOG_CHAT_ID,
            notify_message=message,
            notify_parse_mode=ParseMode.HTML.value,
        )

        state["live"] = True
        state["title"] = stream["title"]
        state["game"] = stream["game_name"]

        logger.info("[TWITCH] %s went LIVE.", username)

    # Went offline
    elif event == "OFFLINE":
        old_title = state["title"]
        old_game = state["game"]

        message = ""

        message += f"⚫ <b>{escape(username)}</b> is now OFFLINE!"

        await log_twitch_event(
            twitch_username=username,
            event_type="OFFLINE",
            old_title=old_title,
            old_game_name=old_game,
            message=message,
            raw_payload=data,
            notify_chat_id=STREAM_LOG_CHAT_ID,
            notify_message=message,
            notify_parse_mode=ParseMode.HTML.value,
        )

        state["live"] = False
        state["title"] = None
        state["game"] = None

        logger.info("[TWITCH] %s went OFFLINE.", username)

    # Stream title or game changed
    elif event == "STREAM_UPDATE":
        changes = []
        old_title = state["title"]
        old_game = state["game"]

        if stream["title"] != state["title"]:
            change = ""

            change += f"📝 <b>Title</b>\n"
            change += f"<b>Old:</b> {escape(state['title'])}\n"
            change += f"<b>New:</b> {escape(stream['title'])}"

            changes.append(change)

        if stream["game_name"] != state["game"]:
            change = ""

            change += f"📝 <b>Game</b>\n"
            change += f"<b>Old:</b> {escape(state['game'])}\n"
            change += f"<b>New:</b> {escape(stream['game_name'])}"

            changes.append(change)

        if changes:
            message = ""

            message += (
                f"🔄 <b>{escape(stream['user_name'])}</b> updated their stream!\n\n"
            )

            message += "\n\n".join(changes)

            await log_twitch_event(
                twitch_username=username,
                event_type="STREAM_UPDATE",
                twitch_display_name=stream["user_name"],
                stream_id=stream.get("id"),
                title=stream["title"],
                game_name=stream["game_name"],
                old_title=old_title,
                old_game_name=old_game,
                message=message,
                raw_payload=stream,
                notify_chat_id=STREAM_LOG_CHAT_ID,
                notify_message=message,
                notify_parse_mode=ParseMode.HTML.value,
            )

            if stream["title"] != state["title"]:
                state["title"] = stream["title"]

            if stream["game_name"] != state["game"]:
                state["game"] = stream["game_name"]

            logger.info("[TWITCH] %s updated their stream.", username)


async def check_all(bot):

    for streamer in TWITCH_STREAMERS:
        try:
            await check_streamer(streamer, bot)
        except TwitchTokenExpiredError:
            logger.warning("[TWITCH] Access token expired. Refreshing token...")
            try:
                await get_access_token()
                await check_streamer(streamer, bot)

            except Exception:
                logger.exception(
                    "[TWITCH] Failed to refresh token or retry %s", streamer["username"]
                )
        except Exception:
            logger.exception("[TWITCH] Error checking %s", streamer["username"])


async def start_twitch_monitor(bot):
    logger.info("[TWITCH] Starting Twitch monitor...")

    global session
    session = aiohttp.ClientSession()

    try:
        while True:
            try:
                # Get a Twitch access token if we don't have one
                if access_token is None:
                    await get_access_token()

                # Check all streamers
                await check_all(bot)

                # Send startup message only once
                if startup_summary:
                    message = ""
                    message += "🎮 <b>Twitch Monitor Started</b>\n\n"
                    message += "\n".join(startup_summary)

                    try:
                        await send_message_with_retry(
                            bot,
                            chat_id=STREAM_LOG_CHAT_ID,
                            text=message,
                            parse_mode=ParseMode.HTML,
                        )
                    except TelegramError:
                        # Sent once only; a rejected summary is dropped.
                        logger.exception("[TWITCH] Startup summary rejected.")

                    startup_summary.clear()

                # Normal monitoring interval
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "[TWITCH] Error in monitoring cycle. " "Retrying in 60 seconds..."
                )

                await asyncio.sleep(60)

    except asyncio.CancelledError:
        logger.info("[TWITCH] Monitor shutting down")

        try:
            await send_message_with_retry(
                bot,
                chat_id=STREAM_LOG_CHAT_ID,
                text="[TWITCH] Monitor shutting down",
            )
        except TelegramError:
            logger.exception("[TWITCH] Shutdown notice rejected.")
        raise

    finally:
        if session is not None:
            await session.close()

        session = None
