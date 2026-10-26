import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import twitch_monitor
from twitch_monitor import get_stream_event

def test_offline_to_offline():
    previous_state = {
        "live": False,
        "title": None,
        "game": None,
    }

    assert get_stream_event(previous_state, None) is None


def test_offline_to_live():
    previous_state = {
        "live": False,
        "title": None,
        "game": None,
    }

    current_stream = {
        "title": "Playing Minecraft",
        "game_name": "Minecraft",
    }

    assert get_stream_event(previous_state, current_stream) == "LIVE"


def test_live_to_offline():
    previous_state = {
        "live": True,
        "title": "Playing Minecraft",
        "game": "Minecraft",
    }

    assert get_stream_event(previous_state, None) == "OFFLINE"


def test_live_with_no_changes():
    previous_state = {
        "live": True,
        "title": "Playing Minecraft",
        "game": "Minecraft",
    }

    current_stream = {
        "title": "Playing Minecraft",
        "game_name": "Minecraft",
    }

    assert get_stream_event(previous_state, current_stream) is None


def test_live_with_title_change():
    previous_state = {
        "live": True,
        "title": "Playing Minecraft",
        "game": "Minecraft",
    }

    current_stream = {
        "title": "Playing Minecraft with friends!",
        "game_name": "Minecraft",
    }

    assert get_stream_event(previous_state, current_stream) == "STREAM_UPDATE"


def test_live_with_game_change():
    previous_state = {
        "live": True,
        "title": "Playing Minecraft",
        "game": "Minecraft",
    }

    current_stream = {
        "title": "Playing Minecraft",
        "game_name": "Fortnite",
    }

    assert get_stream_event(previous_state, current_stream) == "STREAM_UPDATE"


def test_live_with_title_and_game_change():
    previous_state = {
        "live": True,
        "title": "Playing Minecraft",
        "game": "Minecraft",
    }

    current_stream = {
        "title": "Playing Fortnite!",
        "game_name": "Fortnite",
    }

    assert get_stream_event(previous_state, current_stream) == "STREAM_UPDATE"


@pytest.mark.asyncio
async def test_check_streamer_live(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    async def fake_get_stream_data(username):
        return {
            "data": [
                {
                    "id": "123456",
                    "user_id": "999",
                    "user_login": username,
                    "user_name": "TestStreamer",
                    "title": "Testing my stream",
                    "game_name": "Just Chatting",
                }
            ]
        }

    logged_events = []
    sent_messages = []

    async def fake_log_twitch_event(**kwargs):
        logged_events.append(kwargs)

    async def fake_send_message(*args, **kwargs):
        sent_messages.append((args, kwargs))

    monkeypatch.setattr(
        twitch_monitor,
        "get_stream_data",
        fake_get_stream_data,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "log_twitch_event",
        fake_log_twitch_event,
    )

    class FakeBot:
        send_message = fake_send_message

    bot = FakeBot()

    await twitch_monitor.check_streamer(
        {"username": "teststreamer"},
        bot,
    )

    assert twitch_monitor.stream_state["teststreamer"]["live"] is True

    assert twitch_monitor.stream_state["teststreamer"]["title"] == ("Testing my stream")

    assert twitch_monitor.stream_state["teststreamer"]["game"] == ("Just Chatting")

    assert logged_events[0]["event_type"] == "STARTUP_LIVE"

    assert sent_messages == []


@pytest.mark.asyncio
async def test_check_streamer_goes_live(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    twitch_monitor.stream_state["teststreamer"] = {
        "live": False,
        "title": None,
        "game": None,
    }

    async def fake_get_stream_data(username):
        return {
            "data": [
                {
                    "id": "123456",
                    "user_id": "999",
                    "user_login": username,
                    "user_name": "TestStreamer",
                    "title": "Testing my stream",
                    "game_name": "Just Chatting",
                }
            ]
        }

    logged_events = []
    sent_messages = []

    async def fake_log_twitch_event(**kwargs):
        logged_events.append(kwargs)

    async def fake_send_message(*args, **kwargs):
        sent_messages.append((args, kwargs))

    monkeypatch.setattr(
        twitch_monitor,
        "get_stream_data",
        fake_get_stream_data,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "log_twitch_event",
        fake_log_twitch_event,
    )

    class FakeBot:
        async def send_message(self, *args, **kwargs):
            sent_messages.append((args, kwargs))

    bot = FakeBot()

    await twitch_monitor.check_streamer(
        {"username": "teststreamer"},
        bot,
    )

    assert twitch_monitor.stream_state["teststreamer"]["live"] is True

    assert twitch_monitor.stream_state["teststreamer"]["title"] == ("Testing my stream")

    assert twitch_monitor.stream_state["teststreamer"]["game"] == ("Just Chatting")

    assert logged_events[0]["event_type"] == "LIVE"

    assert sent_messages[0][1]["chat_id"] == twitch_monitor.STREAM_LOG_CHAT_ID

    assert "TestStreamer" in sent_messages[0][1]["text"]
    assert "LIVE" in sent_messages[0][1]["text"]


@pytest.mark.asyncio
async def test_check_streamer_goes_offline(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    twitch_monitor.stream_state["teststreamer"] = {
        "live": True,
        "title": "Testing my stream",
        "game": "Just Chatting",
    }

    async def fake_get_stream_data(username):
        return {"data": []}

    logged_events = []
    sent_messages = []

    async def fake_log_twitch_event(**kwargs):
        logged_events.append(kwargs)

    class FakeBot:

        async def send_message(self, *args, **kwargs):
            sent_messages.append((args, kwargs))

    monkeypatch.setattr(
        twitch_monitor,
        "get_stream_data",
        fake_get_stream_data,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "log_twitch_event",
        fake_log_twitch_event,
    )

    bot = FakeBot()

    await twitch_monitor.check_streamer(
        {"username": "teststreamer"},
        bot,
    )

    assert twitch_monitor.stream_state["teststreamer"]["live"] is False

    assert twitch_monitor.stream_state["teststreamer"]["title"] is None

    assert twitch_monitor.stream_state["teststreamer"]["game"] is None

    assert logged_events[0]["event_type"] == "OFFLINE"

    assert logged_events[0]["old_title"] == "Testing my stream"

    assert logged_events[0]["old_game_name"] == "Just Chatting"

    assert sent_messages[0][1]["chat_id"] == twitch_monitor.STREAM_LOG_CHAT_ID

    assert "TestStreamer" not in sent_messages[0][1]["text"]

    assert "OFFLINE" in sent_messages[0][1]["text"]


@pytest.mark.asyncio
async def test_check_streamer_title_update(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    twitch_monitor.stream_state["teststreamer"] = {
        "live": True,
        "title": "Old stream title",
        "game": "Just Chatting",
    }

    async def fake_get_stream_data(username):
        return {
            "data": [
                {
                    "id": "123456",
                    "user_id": "999",
                    "user_login": username,
                    "user_name": "TestStreamer",
                    "title": "New stream title",
                    "game_name": "Just Chatting",
                }
            ]
        }

    logged_events = []
    sent_messages = []

    async def fake_log_twitch_event(**kwargs):
        logged_events.append(kwargs)

    class FakeBot:

        async def send_message(self, *args, **kwargs):
            sent_messages.append((args, kwargs))

    monkeypatch.setattr(
        twitch_monitor,
        "get_stream_data",
        fake_get_stream_data,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "log_twitch_event",
        fake_log_twitch_event,
    )

    bot = FakeBot()

    await twitch_monitor.check_streamer(
        {"username": "teststreamer"},
        bot,
    )

    assert twitch_monitor.stream_state["teststreamer"]["live"] is True

    assert twitch_monitor.stream_state["teststreamer"]["title"] == ("New stream title")

    assert twitch_monitor.stream_state["teststreamer"]["game"] == ("Just Chatting")

    assert logged_events[0]["event_type"] == "STREAM_UPDATE"

    assert logged_events[0]["old_title"] == "Old stream title"

    assert logged_events[0]["old_game_name"] == "Just Chatting"

    assert sent_messages[0][1]["chat_id"] == twitch_monitor.STREAM_LOG_CHAT_ID

    assert "New stream title" in sent_messages[0][1]["text"]

    assert "Old stream title" in sent_messages[0][1]["text"]


@pytest.mark.asyncio
async def test_check_streamer_game_update(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    twitch_monitor.stream_state["teststreamer"] = {
        "live": True,
        "title": "Playing something",
        "game": "Minecraft",
    }

    async def fake_get_stream_data(username):
        return {
            "data": [
                {
                    "id": "123456",
                    "user_id": "999",
                    "user_login": username,
                    "user_name": "TestStreamer",
                    "title": "Playing something",
                    "game_name": "Fortnite",
                }
            ]
        }

    logged_events = []
    sent_messages = []

    async def fake_log_twitch_event(**kwargs):
        logged_events.append(kwargs)

    class FakeBot:

        async def send_message(self, *args, **kwargs):
            sent_messages.append((args, kwargs))

    monkeypatch.setattr(
        twitch_monitor,
        "get_stream_data",
        fake_get_stream_data,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "log_twitch_event",
        fake_log_twitch_event,
    )

    bot = FakeBot()

    await twitch_monitor.check_streamer(
        {"username": "teststreamer"},
        bot,
    )

    assert twitch_monitor.stream_state["teststreamer"]["live"] is True

    assert twitch_monitor.stream_state["teststreamer"]["title"] == ("Playing something")

    assert twitch_monitor.stream_state["teststreamer"]["game"] == ("Fortnite")

    assert logged_events[0]["event_type"] == "STREAM_UPDATE"

    assert logged_events[0]["old_title"] == "Playing something"

    assert logged_events[0]["old_game_name"] == "Minecraft"

    assert sent_messages[0][1]["chat_id"] == twitch_monitor.STREAM_LOG_CHAT_ID

    assert "Minecraft" in sent_messages[0][1]["text"]

    assert "Fortnite" in sent_messages[0][1]["text"]


@pytest.mark.asyncio
async def test_check_streamer_title_and_game_update(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    twitch_monitor.stream_state["teststreamer"] = {
        "live": True,
        "title": "Old title",
        "game": "Minecraft",
    }

    async def fake_get_stream_data(username):
        return {
            "data": [
                {
                    "id": "123456",
                    "user_id": "999",
                    "user_login": username,
                    "user_name": "TestStreamer",
                    "title": "New title",
                    "game_name": "Fortnite",
                }
            ]
        }

    logged_events = []
    sent_messages = []

    async def fake_log_twitch_event(**kwargs):
        logged_events.append(kwargs)

    class FakeBot:

        async def send_message(self, *args, **kwargs):
            sent_messages.append((args, kwargs))

    monkeypatch.setattr(
        twitch_monitor,
        "get_stream_data",
        fake_get_stream_data,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "log_twitch_event",
        fake_log_twitch_event,
    )

    bot = FakeBot()

    await twitch_monitor.check_streamer(
        {"username": "teststreamer"},
        bot,
    )

    assert twitch_monitor.stream_state["teststreamer"]["live"] is True

    assert twitch_monitor.stream_state["teststreamer"]["title"] == ("New title")

    assert twitch_monitor.stream_state["teststreamer"]["game"] == ("Fortnite")

    assert logged_events[0]["event_type"] == "STREAM_UPDATE"

    assert logged_events[0]["old_title"] == "Old title"

    assert logged_events[0]["old_game_name"] == "Minecraft"

    assert logged_events[0]["title"] == "New title"

    assert logged_events[0]["game_name"] == "Fortnite"

    assert sent_messages[0][1]["chat_id"] == twitch_monitor.STREAM_LOG_CHAT_ID

    message = sent_messages[0][1]["text"]

    assert "Old title" in message
    assert "New title" in message
    assert "Minecraft" in message
    assert "Fortnite" in message


@pytest.mark.asyncio
async def test_check_all_refreshes_expired_token(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    calls = []
    token_refreshes = []

    async def fake_check_streamer(streamer, bot):

        calls.append(streamer["username"])

        if len(calls) == 1:
            raise twitch_monitor.TwitchTokenExpiredError()

        twitch_monitor.stream_state[streamer["username"]] = {
            "live": False,
            "title": None,
            "game": None,
        }

    async def fake_get_access_token():
        token_refreshes.append(True)

    monkeypatch.setattr(
        twitch_monitor,
        "check_streamer",
        fake_check_streamer,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "get_access_token",
        fake_get_access_token,
    )

    original_streamers = twitch_monitor.TWITCH_STREAMERS

    twitch_monitor.TWITCH_STREAMERS = [{"username": "teststreamer"}]

    try:
        await twitch_monitor.check_all(None)
    finally:
        twitch_monitor.TWITCH_STREAMERS = original_streamers

    assert calls == [
        "teststreamer",
        "teststreamer",
    ]

    assert token_refreshes == [True]


@pytest.mark.asyncio
async def test_check_all_handles_token_refresh_failure(monkeypatch):

    twitch_monitor.stream_state.clear()
    twitch_monitor.startup_summary.clear()

    calls = []
    refresh_attempts = []

    async def fake_check_streamer(streamer, bot):

        calls.append(streamer["username"])

        raise twitch_monitor.TwitchTokenExpiredError()

    async def fake_get_access_token():

        refresh_attempts.append(True)

        raise RuntimeError("Unable to refresh Twitch token")

    monkeypatch.setattr(
        twitch_monitor,
        "check_streamer",
        fake_check_streamer,
    )

    monkeypatch.setattr(
        twitch_monitor,
        "get_access_token",
        fake_get_access_token,
    )

    original_streamers = twitch_monitor.TWITCH_STREAMERS

    twitch_monitor.TWITCH_STREAMERS = [
        {"username": "teststreamer1"},
        {"username": "teststreamer2"},
    ]

    try:
        await twitch_monitor.check_all(None)
    finally:
        twitch_monitor.TWITCH_STREAMERS = original_streamers

    assert calls == [
        "teststreamer1",
        "teststreamer2",
    ]

    assert refresh_attempts == [
        True,
        True,
    ]


@pytest.mark.asyncio
async def test_get_stream_data_success():

    class FakeResponse:

        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {
                "data": [
                    {
                        "id": "123456",
                        "user_name": "TestStreamer",
                        "title": "Testing my stream",
                        "game_name": "Just Chatting",
                    }
                ]
            }

    class FakeSession:

        def get(self, url, headers):
            assert url == "https://api.twitch.tv/helix/streams?user_login=teststreamer"

            assert headers["Client-ID"] == twitch_monitor.TWITCH_CLIENT_ID

            assert headers["Authorization"] == (f"Bearer {twitch_monitor.access_token}")

            return FakeResponse()

    twitch_monitor.access_token = "test-access-token"
    twitch_monitor.session = FakeSession()

    try:
        result = await twitch_monitor.get_stream_data("teststreamer")

        assert result["data"][0]["id"] == "123456"

        assert result["data"][0]["user_name"] == "TestStreamer"

        assert result["data"][0]["title"] == "Testing my stream"

        assert result["data"][0]["game_name"] == "Just Chatting"

    finally:
        twitch_monitor.session = None


@pytest.mark.asyncio
async def test_get_stream_data_token_expired():

    class FakeResponse:

        status = 401

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {}

    class FakeSession:

        def get(self, url, headers):
            return FakeResponse()

    twitch_monitor.session = FakeSession()

    try:
        with pytest.raises(twitch_monitor.TwitchTokenExpiredError):
            await twitch_monitor.get_stream_data("teststreamer")

    finally:
        twitch_monitor.session = None


@pytest.mark.asyncio
async def test_get_stream_data_offline():

    class FakeResponse:

        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"data": []}

    class FakeSession:

        def get(self, url, headers):
            return FakeResponse()

    twitch_monitor.session = FakeSession()

    try:
        result = await twitch_monitor.get_stream_data("teststreamer")

        assert result == {"data": []}

    finally:
        twitch_monitor.session = None


@pytest.mark.asyncio
async def test_get_stream_data_without_session():

    twitch_monitor.session = None

    with pytest.raises(RuntimeError, match="Twitch session is not initialized"):
        await twitch_monitor.get_stream_data("teststreamer")


@pytest.mark.asyncio
async def test_get_access_token_success():

    class FakeResponse:

        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"access_token": "new-test-token"}

    class FakeSession:

        def post(self, url, params):

            assert url == "https://id.twitch.tv/oauth2/token"

            assert params["client_id"] == twitch_monitor.TWITCH_CLIENT_ID

            assert params["client_secret"] == (twitch_monitor.TWITCH_CLIENT_SECRET)

            assert params["grant_type"] == "client_credentials"

            return FakeResponse()

    twitch_monitor.session = FakeSession()
    twitch_monitor.access_token = None

    try:
        await twitch_monitor.get_access_token()

        assert twitch_monitor.access_token == "new-test-token"

    finally:
        twitch_monitor.session = None
