# 🗄️ PostgreSQL Database

Reez Bot uses PostgreSQL for persistent storage.

The database stores Twitch monitoring events.

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