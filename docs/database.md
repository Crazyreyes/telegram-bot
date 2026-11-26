# 🗄️ PostgreSQL Database

Reez Bot uses PostgreSQL for persistent storage.

The database stores Twitch monitoring events and a notification outbox.

## Why PostgreSQL?

The bot's data has natural relationships:

```text
Twitch Events
 └── Historical Twitch changes
```

A relational database makes it easy to query these relationships, calculate averages and retrieve participant histories.

## Database Connection

The bot supports a PostgreSQL connection URL:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

It also supports separate PostgreSQL environment variables:

```env
PGHOST=...
PGPORT=...
PGDATABASE=...
PGUSER=...
PGPASSWORD=...
```

`DATABASE_URL` is preferred when the hosting provider supplies a connection string.

## Tables

### `twitch_events`

Stores the Twitch event history.

Event types include:

```text
STARTUP_LIVE
STARTUP_OFFLINE
LIVE
OFFLINE
STREAM_UPDATE
```

The table also stores previous title/game values when relevant and the raw Twitch API response.

### `outbox`

Stores queued stream notifications that the worker sends.

Each row holds everything the worker needs to send the message later: the
`twitch_events` row it belongs to (`twitch_event_id`), the target chat
(`chat_id`), the message text (`message_text`) and its parse mode
(`parse_mode`, e.g. `HTML`).

Status bookkeeping for the worker:

- `status` — `pending`, `sent` or `failed` (starts as `pending`).
- `attempts` — how many send attempts have been made.
- `last_error` — the error from the most recent failed attempt.
- `next_attempt_at` — when the row is next due to be retried.
- `created_at` / `sent_at` — when the row was queued and when it was sent.

The event row and its outbox row are written in a single database
transaction, so either both are saved or neither is. If that write hits a
transient database error (e.g. a command timeout), it is retried up to 3
times with a 1s then 2s pause before giving up.

### The outbox worker

`outbox_worker.py` runs as a background task alongside the monitor
(started in `main.py`). Every 10 seconds it claims due `pending` rows and
sends them with `send_message_with_retry()`.

Claiming is a single atomic `UPDATE ... RETURNING`: it picks the oldest due
rows and pushes their `next_attempt_at` into the future, which acts as a
lease. A second worker cannot claim the same rows, and if a worker crashes
mid-send the lease simply expires and the rows become claimable again. No
separate `sending` status is needed.

On a successful send the row is marked `sent` with a timestamp. On a
failure the worker records the error, bumps `attempts`, and schedules the
next try with exponential backoff (60s, 120s, 240s, 480s, capped at 1
hour). After 5 attempts the row is marked `failed` and kept for inspection
instead of being retried forever. A message Telegram rejects outright
(e.g. bad HTML) is marked `failed` at once instead of being retried.
Sent rows older than 30 days are deleted
by the worker (checked roughly once an hour).

The outbox is the only send path for stream notifications: the monitor
queues them and never sends directly. The monitor's startup summary and
shutdown notice are still sent directly, since they are not stream events
and have no outbox row.

## Environment Variables

Example:

```env
BOT_TOKEN=...
STREAM_LOG_CHAT_ID=...
DUMP_CHAT_ID=...

TWITCH_CLIENT_ID=...
TWITCH_CLIENT_SECRET=...

DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

Secrets should never be committed to Git.

Use `.env` for local development and set the environment variables directly on your host for deployment.