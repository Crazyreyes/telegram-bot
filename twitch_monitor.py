import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
STREAM_LOG_CHAT_ID = os.getenv("STREAM_LOG_CHAT_ID")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

TWITCH_STREAMERS = [
    {
        "username": "streamer_one",
    },
    {
        "username": "streamer_two",
    }
]

access_token = None
startup_summary = []
stream_state = {}

session = None

async def get_access_token():
    global access_token

    url = "https://id.twitch.tv/oauth2/token"

    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }

    async with session.post(url, params=params) as response:

        data = await response.json()

        access_token = data["access_token"]

    print("[TWITCH] Access token obtained.")

async def check_streamer(streamer, bot):

    username = streamer["username"]

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {access_token}"
    }

    async with session.get(
        f"https://api.twitch.tv/helix/streams?user_login={username}",
        headers=headers
    ) as response:

        if response.status == 401:
            raise Exception("TOKEN_EXPIRED")

        data = await response.json()

    is_live = len(data["data"]) > 0

    # First startup
    if username not in stream_state:

        if is_live:

            stream = data["data"][0]

            stream_state[username] = {
                "live": True,
                "title": stream["title"],
                "game": stream["game_name"]
            }

        else:

            stream_state[username] = {
                "live": False,
                "title": None,
                "game": None
            }

        startup_summary.append(
            f"{'🔴' if is_live else '⚫'} {username} - {'LIVE' if is_live else 'OFFLINE'}"
        )

        return

    state = stream_state[username]


    # Went live
    if is_live and not state["live"]:

        stream = data["data"][0]

        state["live"] = True
        state["title"] = stream["title"]
        state["game"] = stream["game_name"]
        
        message = ""

        message += f"🔴 <b>{stream['user_name']}</b> is now <b>LIVE!</b>\n\n"
        message += f"🎮 {stream['game_name']}\n"
        message += f"📝 {stream['title']}\n\n"
        message += f"https://twitch.tv/{stream['user_login']}"
        await bot.send_message(STREAM_LOG_CHAT_ID, message, parse_mode="HTML")

        print(f"[TWITCH] {username} went LIVE.")

    # Went offline
    elif not is_live and state["live"]:

        state["live"] = False
        state["title"] = None
        state["game"] = None

        message = ""

        message += f"⚫ <b>{username}</b> is now OFFLINE!"

        await bot.send_message(STREAM_LOG_CHAT_ID, message, parse_mode="HTML")

        print(f"[TWITCH] {username} went OFFLINE.")

    elif is_live and state["live"]:

        stream = data["data"][0]

        changes = []

        if stream["title"] != state["title"]:
            change = ""

            change += f"📝 <b>Title</b>\n"
            change += f"<b>Old:</b> {state['title']}\n"
            change += f"<b>New:</b> {stream['title']}"

            changes.append(change)

            state["title"] = stream["title"]

        if stream["game_name"] != state["game"]:

            change = ""
            
            change += f"📝 <b>Game</b>\n"
            change += f"<b>Old:</b> {state['game']}\n"
            change += f"<b>New:</b> {stream['game_name']}"

            changes.append(change)

            state["game"] = stream["game_name"]

        if changes:
            message = ""
            message += f"🔄 <b>{stream['user_name']}</b> updated their stream!\n\n"
            message += "\n\n".join(changes)

            await bot.send_message(STREAM_LOG_CHAT_ID, message, parse_mode="HTML")


async def check_all(bot):

    for streamer in TWITCH_STREAMERS:

        try:

            await check_streamer(streamer, bot)

        except Exception as e:

            if str(e) == "TOKEN_EXPIRED":

                await get_access_token()

                await check_streamer(streamer, bot)

            else:

                print(e)


async def start_twitch_monitor(bot):

    print("[TWITCH] Starting Twitch monitor...");

    global session

    session = aiohttp.ClientSession()

    await get_access_token()

    await check_all(bot)
    
    message = ""
    message += "🎮 <b>Twitch Monitor Started</b>\n\n"
    message += "\n".join(startup_summary)

    await bot.send_message(STREAM_LOG_CHAT_ID, message, parse_mode="HTML")

    startup_summary.clear()

    while True:

        await asyncio.sleep(60)

        await check_all(bot)