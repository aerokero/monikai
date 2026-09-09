from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.audio.server_voice_session import ServerVoiceSessionStore
from backend.audio.server_voice_session import ServerVoiceChatSession
from backend.core.conversation_store import get_conversation, list_conversations
from backend.core.odysseus_voice_gateway import OdysseusVoiceGateway


@pytest.mark.asyncio
async def test_server_voice_store_creates_normal_browsable_conversation(tmp_path):
    events = []

    async def emit(event, payload):
        events.append((event, payload))

    store = ServerVoiceSessionStore(tmp_path, emit_event=emit)
    session_id = await store.begin()
    await store.record_turn("Dodaj mleko do listy", "Dodałam mleko.")
    await store.end()

    item = get_conversation(tmp_path / "sessions", session_id)
    assert item is not None
    assert item["kind"] == "conversation"
    assert item["channel"] == "server_voice"
    assert [(turn["sender"], turn["text"]) for turn in item["turns"]] == [
        ("User", "Dodaj mleko do listy"),
        ("AI", "Dodałam mleko."),
    ]
    meta = json.loads(
        (store.manager.get_session_path(session_id) / "meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert meta["source"] == "server_microphone"
    assert meta["finalized"] is True
    assert meta["ended_at"]
    assert [name for name, _ in events] == [
        "server_voice_session_started",
        "server_voice_turn",
        "server_voice_session_finished",
    ]


@pytest.mark.asyncio
async def test_each_wake_activation_gets_a_new_conversation(tmp_path):
    store = ServerVoiceSessionStore(tmp_path)

    first = await store.record_turn("Pierwsza", "Odpowiedź")
    await store.end()
    second = await store.record_turn("Druga", "Odpowiedź")

    assert first != second
    items = list_conversations(tmp_path / "sessions")
    assert {item["id"] for item in items} == {first, second}
    assert all(item["channel"] == "server_voice" for item in items)


def test_server_voice_route_tracks_current_conversation_settings(tmp_path):
    settings = {
        "text_model": "openrouter/free",
        "text_endpoint_id": "openrouter",
        "text_persona_id": "monika",
    }
    chat = ServerVoiceChatSession(
        session_store=ServerVoiceSessionStore(tmp_path),
        settings_getter=lambda: settings,
    )

    assert chat._conversation_route() == (
        "openrouter/free",
        "openrouter",
        "monika",
    )

    settings.update({"text_model": "gemini-2.5-flash", "text_endpoint_id": "gemini-text"})
    assert chat._conversation_route() == (
        "gemini-2.5-flash",
        "gemini-text",
        "monika",
    )


@pytest.mark.asyncio
async def test_native_voice_gateway_does_not_start_gemini_live(tmp_path):
    settings = {
        "text_model": "openrouter/free",
        "text_endpoint_id": "openrouter",
        "text_persona_id": "monika",
    }
    gateway = AsyncMock()
    gateway.generate.return_value = "Jasne, już sprawdzam."
    store = ServerVoiceSessionStore(tmp_path)
    chat = ServerVoiceChatSession(
        session_store=store,
        settings_getter=lambda: settings,
        conversation_gateway=gateway,
    )

    reply = await chat.ask("Co jest na liście zakupów?")

    assert reply == "Jasne, już sprawdzam."
    assert chat.audio_loop is None
    gateway.generate.assert_awaited_once()
    call = gateway.generate.await_args
    assert call.args == ("Co jest na liście zakupów?",)
    assert call.kwargs["model"] == "openrouter/free"
    assert call.kwargs["endpoint_id"] == "openrouter"
    assert call.kwargs["persona_id"] == "monika"
    assert call.kwargs["session_id"].startswith("voice_")


def test_native_voice_gateway_extracts_agent_answer_after_tool_call():
    response = httpx.Response(
        200,
        content=(
            'data: {"type":"tool_start","tool":"home_assistant_control"}\n\n'
            'data: {"type":"tool_output","tool":"home_assistant_control","output":"ok"}\n\n'
            'data: {"delta":"Włączyłam tryb relaksu."}\n\n'
            "data: [DONE]\n\n"
        ),
        request=httpx.Request("POST", "http://odysseus.internal/api/chat_stream"),
    )

    assert OdysseusVoiceGateway._stream_result(response) == "Włączyłam tryb relaksu."


def test_native_voice_gateway_does_not_speak_thinking_deltas():
    response = httpx.Response(
        200,
        content=(
            'data: {"delta":"internal reasoning", "thinking":true}\n\n'
            'data: {"delta":"Gotowe."}\n\n'
            "data: [DONE]\n\n"
        ),
        request=httpx.Request("POST", "http://odysseus.internal/api/chat_stream"),
    )

    assert OdysseusVoiceGateway._stream_result(response) == "Gotowe."
