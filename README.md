# Reez Bot

A Telegram bot that monitors Twitch channels and posts stream updates to a
Telegram chat. Every detected event is also stored in PostgreSQL.

## Features

### 🎮 Twitch Monitor

Monitors configured Twitch channels and sends a Telegram notification when a
streamer goes live, goes offline, or changes their title or game/category.

[Read the Twitch Monitor documentation](docs/twitch-monitor.md)

### 🗄️ PostgreSQL

Stores every detected Twitch event, so stream history is kept even after a
stream ends.

[Read the Database documentation](docs/database.md)

### 🧪 Testing

Automated tests are written using pytest. They use mocked Twitch API
responses and need no real credentials.

[Read the Testing documentation](docs/test.md)

## Setup

Requires Python 3.10 or later.

```powershell
git clone https://github.com/Crazyreyes/telegram-bot.git
cd telegram-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env` (see below), then start the bot:

```powershell
python main.py
```

## Environment variables

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `STREAM_LOG_CHAT_ID` | Telegram chat ID that receives the stream notifications |
| `DUMP_CHAT_ID` | Telegram chat ID for the bot's own messages (e.g. startup notices) |
| `TWITCH_CLIENT_ID` | Twitch API client ID from the [Twitch developer console](https://dev.twitch.tv/console) |
| `TWITCH_CLIENT_SECRET` | Twitch API client secret |
| `TWITCH_STREAMERS` | Comma-separated Twitch usernames to monitor, e.g. `streamer_one,streamer_two` |
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql://USER:PASSWORD@HOST:PORT/DATABASE` |
| `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` | Used instead of `DATABASE_URL` when the host does not provide one |

Never commit `.env` — secrets stay out of git. `.env` is already in
`.gitignore`.

## Running tests

```powershell
pytest
```

No real credentials are needed: `tests/conftest.py` sets dummy values for
every required variable before the tests run.

## Deployment

The bot runs on any host with Python 3.10+ and PostgreSQL. Deploy it by pushing
the code to the server and setting the same environment variables there — in the
host's panel, or in a `.env` file on the server. Start it with:

```powershell
python main.py
```

## License

MIT — see [LICENSE](LICENSE).
