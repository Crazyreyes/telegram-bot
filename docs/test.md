# 🧪 Testing

Reez Bot uses **pytest** for automated testing.

Automated tests are stored in:

```text
tests/
├── conftest.py
├── test_telegram_utils.py
└── test_twitch_monitor.py
```

`conftest.py` sets dummy values for every required environment variable, so
the tests run with no real credentials configured.

## Running Tests

Activate the project's virtual environment and run:

```powershell
pytest
```

A successful test run should look similar to:

```text
============================= test session starts =============================
collected 26 items

tests\test_telegram_utils.py ......                                      [ 23%]
tests\test_twitch_monitor.py ....................                        [100%]

============================== 26 passed ======================================
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

## Telegram Utilities Tests

The message-sending helper in `telegram_utils.py` has its own test suite,
covering:

* retrying after a network error, then succeeding
* waiting out a Telegram rate limit before retrying
* passing the HTML parse mode through correctly
* not retrying a rejected (`BadRequest`) message
* giving up and returning `None` once retries are exhausted
* retrying timeouts with the configured timeout values

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

The automated test suite currently contains:

```text
26 tests
26 passed
0 failed
```

20 tests cover the Twitch monitor and 6 cover the Telegram utilities.

Tests should be run after significant changes to the Twitch monitoring code.

The expected command is:

```powershell
pytest
```

A change should not be considered complete if the existing automated tests fail.
