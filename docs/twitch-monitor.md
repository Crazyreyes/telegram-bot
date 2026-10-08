# 🎮 Twitch Monitor

Reez Bot continuously monitors configured Twitch channels and sends relevant stream updates to the configured Telegram group.

## How It Works

The bot uses the Twitch API to periodically check whether each configured streamer is live.

The current monitor checks:

```text
streamer_one
streamer_two
```

The monitor checks the channels every **60 seconds**.

When a change is detected, the bot records the event in PostgreSQL and sends a notification to Telegram when appropriate.

The Twitch monitor runs as a background task alongside the Telegram bot.

## Startup Detection

When Reez Bot starts, it first checks the current status of every configured streamer.

Each streamer is classified as:

* 🔴 `LIVE`
* ⚫ `OFFLINE`

The bot stores a startup event in PostgreSQL:

```text
STARTUP_LIVE
STARTUP_OFFLINE
```

The group then receives a startup summary showing the current state of the monitored streamers.

Example:

```text
🎮 Twitch Monitor Started

🔴 streamer_one - LIVE
⚫ streamer_two - OFFLINE
```

Startup status is also stored in PostgreSQL so that the bot's monitoring history includes what was detected when the monitor started.

## Going Live

When a streamer changes from offline to live, the bot sends a Telegram notification.

Example:

```text
🔴 <streamer> is now LIVE!

🎮 <game>
📝 <stream title>

https://twitch.tv/<username>
```

The event is stored as:

```text
LIVE
```

The database record includes the stream ID, display name, title, game/category, notification message, and raw Twitch response.

## Going Offline

When a streamer changes from live to offline, the bot sends:

```text
⚫ <streamer> is now OFFLINE!
```

The event is stored as:

```text
OFFLINE
```

The previous stream title and game/category are also stored where available.

## Stream Updates

While a streamer is live, the bot checks for changes to:

* stream title
* game/category

When either changes, the bot sends an update.

Example:

```text
🔄 <streamer> updated their stream!

📝 Title
Old: Previous title
New: New title

📝 Game
Old: Previous game
New: New game
```

The event is stored as:

```text
STREAM_UPDATE
```

The database keeps both the previous and new values.

## Error Handling

The Twitch monitor is designed to continue running if a temporary Twitch API or network error occurs.

If an error occurs during a monitoring cycle, the error is logged and the monitor retries after 60 seconds.

If the Twitch access token expires, the bot automatically requests a new token and retries the affected check.

This prevents a temporary API or network problem from permanently stopping the Twitch monitor.

## Shutdown

When the Telegram bot shuts down, the Twitch monitoring task is cancelled gracefully.

The Twitch HTTP session is closed and the database connection pool is closed by the main application.

## PostgreSQL History

Every detected Twitch event is stored in the:

```text
twitch_events
```

table.

Each event can contain:

| Field                 | Description                             |
| --------------------- | --------------------------------------- |
| `detected_at`         | Time the bot detected the event         |
| `twitch_username`     | Twitch login name                       |
| `event_type`          | Type of detected event                  |
| `twitch_display_name` | Display name of the streamer            |
| `stream_id`           | Twitch stream ID when available         |
| `title`               | Current stream title                    |
| `game_name`           | Current game/category                   |
| `old_title`           | Previous title where applicable         |
| `old_game_name`       | Previous game/category where applicable |
| `message`             | Telegram notification text              |
| `raw_payload`         | Raw Twitch API response                 |

This means Twitch history is retained even after the stream ends.

## Authentication

The Twitch monitor requires:

```env
TWITCH_CLIENT_ID=...
TWITCH_CLIENT_SECRET=...
```

The bot obtains an application access token and uses it to query the Twitch API.

If the Twitch token expires, the monitor automatically requests a new token and retries the check.

## Adding Streamers

The currently monitored streamers are configured in:

```text
twitch_monitor.py
```

The streamer list is defined by the `TWITCH_STREAMERS` variable.

To monitor another Twitch account, add its Twitch username to the list.

Example:

```python
TWITCH_STREAMERS = [
    {"username": "streamer_one"},
    {"username": "streamer_two"},
    {"username": "another_streamer"},
]
```

## Testing

The Twitch monitoring logic has an automated test suite using pytest.

Tests are located in:

```text
tests/test_twitch_monitor.py
```

Run the tests with:

```powershell
pytest
```

The test suite covers stream state changes, Twitch API responses, token expiration, token refresh, error handling, and stream updates.

See the [Testing documentation](testing.md) for more information.
