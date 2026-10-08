# 🧪 Testing

Reez Bot uses **pytest** for automated testing.

Automated tests are stored in:

```text
tests/
└── test_twitch_monitor.py
```

## Running Tests

Activate the project's virtual environment and run:

```powershell
pytest
```

A successful test run should look similar to:

```text
============================= test session starts =============================
collected 20 items

tests\test_twitch_monitor.py ....................                            [100%]

============================== 20 passed ======================================
```

## Twitch Monitor Tests

The automated test suite currently covers the core Twitch monitoring logic.

### Stream State Detection

Tests verify:

* offline → offline
* offline → live
* live → offline
* live with no changes
* live with a title change
* live with a game/category change
* live with both title and game/category changes

### Stream Monitoring

Tests verify:

* initial live detection
* initial offline detection
* streamer going live
* streamer going offline
* title updates
* game/category updates
* simultaneous title and game/category updates

### Twitch API Handling

Tests verify:

* successful Twitch API requests
* offline Twitch API responses
* expired access tokens
* access token refresh
* failure while refreshing an expired token
* handling requests before the Twitch session is initialized

## Automated Tests vs Live Testing

The automated tests use mocked Twitch API responses and do not require the real Twitch API.

This allows the core monitoring logic to be tested reliably without waiting for a streamer to change state.

Live testing is also performed separately when possible.

A live test can verify the complete system:

```text
Twitch API
     ↓
Twitch Monitor
     ↓
PostgreSQL
     ↓
Telegram Notification
```

The current automated test suite does **not** replace live testing.

## Current Test Status

The Twitch monitoring test suite currently contains:

```text
20 tests
20 passed
0 failed
```

Tests should be run after significant changes to the Twitch monitoring code.

The expected command is:

```powershell
pytest
```

A change should not be considered complete if the existing automated tests fail.
