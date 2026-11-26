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

Stores queued stream notifications that the worker will send.

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
transaction, so either both are saved or neither is. The outbox only queues
for now: the bot still sends stream notifications directly, and the worker
that reads `pending` rows is a later step.

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