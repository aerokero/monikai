from __future__ import annotations

from typing import Any
import pytest

from backend.core import monikai
from backend.vn.discord_adapter import DiscordChannelAdapter, DiscordChatSession


class StubAudioLoop:

    def __init__(self, *args, **kwargs):
        self.started = False
        self.stopped = False
        self.last_text = None
        self.permissions = {}
        # dummy memory engine to satisfy session summaries
        self.memory_engine = StubMemoryEngine()

    def update_permissions(self, perms):
        self.permissions = perms

    async def wait_until_ready(self, timeout):
        pass

    async def run(self, start_message):
        self.started = True

    def stop(self):
        self.stopped = True

    async def submit_text_turn(self, text, timeout_sec):
        self.last_text = text
        if text.strip() == "test_fail":
            raise RuntimeError("Simulated failure")
        return f"Response to: {text}"


class StubMemoryEngine:

    def __init__(self):
        self.entries = [
            {"id": "mem_1", "type": "semantic", "content": "Test fact 1"},
            {"id": "mem_2", "type": "episodic", "content": "Test episodic 2"},
        ]

    def list_recent(self, limit=5):
        return self.entries[:limit]

    def update_entry(self, entry_id, update_dict):
        for entry in self.entries:
            if entry["id"] == entry_id:
                entry.update(update_dict)
                return "ok"
        return "not_found"

    def get_page(self, resolved):
        if resolved == "notes.md":
            return "Global notes content"
        return f"Page content of {resolved}"

    def append_page(self, resolved, payload):
        pass


class StubUser:

    def __init__(self, id: int, name: str, is_bot: bool = False):
        self.id = id
        self.name = name
        self.is_bot = is_bot


class DMChannel:

    def __init__(self, channel_id: int):
        self.id = channel_id
        self.sent_messages = []
        self.typing_entered = False

    async def send(self, content):
        self.sent_messages.append(content)
        return content

    def typing(self):

        class TypingCtx:

            def __init__(self, parent):
                self.parent = parent

            async def __aenter__(self):
                self.parent.typing_entered = True

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return TypingCtx(self)


class StubChannel:

    def __init__(self, channel_id: int, name: str = "general"):
        self.id = channel_id
        self.name = name
        self.sent_messages = []
        self.typing_entered = False

    async def send(self, content):
        self.sent_messages.append(content)
        return content

    def typing(self):

        class TypingCtx:

            def __init__(self, parent):
                self.parent = parent

            async def __aenter__(self):
                self.parent.typing_entered = True

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return TypingCtx(self)


class StubMessage:

    def __init__(self, content: str, author: StubUser, channel: Any):
        self.content = content
        self.author = author
        self.channel = channel


@pytest.fixture(autouse=True)
def mock_audio_loop(monkeypatch):
    monkeypatch.setattr(monikai, "AudioLoop", StubAudioLoop)
    monkeypatch.setattr(DiscordChatSession, "_list_note_pages", lambda self, limit=24: ["notes.md"])


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr(
        DiscordChannelAdapter,
        "user",
        property(lambda self: StubUser(id=999, name="MonikaBot", is_bot=True)),
    )
    bot = DiscordChannelAdapter(
        token="dummy_token",
        settings_getter=lambda: {},
        allowed_channel_ids=[123],
    )
    return bot


async def test_on_message_ignores_self(adapter):
    channel = StubChannel(123)
    msg = StubMessage(content="Hello", author=adapter.user, channel=channel)

    await adapter.on_message(msg)
    assert not channel.sent_messages


async def test_on_message_ignores_unauthorized_channels(adapter):
    channel = StubChannel(456)  # Not in allowed_channel_ids [123]
    user = StubUser(1, "Alice")
    msg = StubMessage(content="Hello", author=user, channel=channel)

    await adapter.on_message(msg)
    assert not channel.sent_messages


async def test_on_message_accepts_authorized_channels(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    # Must mention bot to initiate session
    msg = StubMessage(content="<@999> Hello Monika", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "Response to: Hello Monika" in channel.sent_messages[0]


async def test_on_message_accepts_dms_regardless_of_allowed_list(adapter):
    channel = DMChannel(789)
    user = StubUser(1, "Alice")
    msg = StubMessage(content="Hello Monika in DM", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "Response to: Hello Monika in DM" in channel.sent_messages[0]


async def test_on_message_handles_mentions(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    # Bot mention is <@999>
    msg = StubMessage(content="<@999> how are you?", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "Response to: how are you?" in channel.sent_messages[0]


async def test_command_help(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    msg = StubMessage(content="!help", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "Dostępne komendy" in channel.sent_messages[0]


async def test_command_status_when_inactive(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    msg = StubMessage(content="!status", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "nieaktywna" in channel.sent_messages[0]


async def test_command_status_when_active(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")

    # Send a regular message to start the session (with mention)
    await adapter.on_message(StubMessage(content="<@999> Hello", author=user, channel=channel))

    # Send status
    await adapter.on_message(StubMessage(content="!status", author=user, channel=channel))
    assert len(channel.sent_messages) == 2
    assert "aktywna" in channel.sent_messages[1]


async def test_command_reset(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")

    # Start session (with mention)
    await adapter.on_message(StubMessage(content="<@999> Hello", author=user, channel=channel))
    assert channel.id in adapter._sessions

    # Reset
    await adapter.on_message(StubMessage(content="!reset", author=user, channel=channel))
    assert channel.id not in adapter._sessions
    assert "Zresetowałam" in channel.sent_messages[-1]


async def test_command_mood(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    msg = StubMessage(content="!mood", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    # Our stub personality is None, so it should report no active mood
    assert "Nie mam teraz" in channel.sent_messages[0]


async def test_command_memory(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    msg = StubMessage(content="!memory", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "Ostatnie wpisy" in channel.sent_messages[0]


async def test_command_forget(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    msg = StubMessage(content="!forget", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "Usunęłam ostatni wpis" in channel.sent_messages[0]


async def test_command_notes(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")

    # notes list catalog
    await adapter.on_message(StubMessage(content="!notes", author=user, channel=channel))
    assert "Dostępne notatki" in channel.sent_messages[-1]

    # read specific page
    await adapter.on_message(StubMessage(content="!notes notes.md", author=user, channel=channel))
    assert "Global notes content" in channel.sent_messages[-1]


async def test_adapter_failure_response(adapter):
    channel = StubChannel(123)
    user = StubUser(1, "Alice")
    msg = StubMessage(content="<@999> test_fail", author=user, channel=channel)

    await adapter.on_message(msg)
    assert channel.sent_messages
    assert "Napotkałam problem" in channel.sent_messages[0]
