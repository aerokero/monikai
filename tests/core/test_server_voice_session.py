from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

_ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(_ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(_ODY_ROOT))

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


def test_native_voice_gateway_drops_voice_silence_marker():
    response = httpx.Response(
        200,
        content=(
            'data: {"delta":"[VOICE_SILENCE]"}\n\n'
            "data: [DONE]\n\n"
        ),
        request=httpx.Request("POST", "http://odysseus.internal/api/chat_stream"),
    )

    assert OdysseusVoiceGateway._stream_result(response) == ""


def test_tool_toggle_enabled_handles_false_values_defensively():
    from src.tool_policy import tool_toggle_enabled
    assert not tool_toggle_enabled(False)
    assert not tool_toggle_enabled("false")
    assert not tool_toggle_enabled("False")
    assert not tool_toggle_enabled(None)
    assert not tool_toggle_enabled("")
    assert tool_toggle_enabled(True)
    assert tool_toggle_enabled("true")
    assert tool_toggle_enabled("True")


def test_casual_low_signal_recognizes_polish_greetings():
    from routes.chat_helpers import _is_casual_low_signal
    assert _is_casual_low_signal("Hej Monika")
    assert _is_casual_low_signal("Cześć Monika")
    assert _is_casual_low_signal("Dzień dobry")
    assert _is_casual_low_signal("Siemanko")
    assert _is_casual_low_signal("Dobranoc, śpij dobrze")
    # Non-casual commands should NOT be low signal
    assert not _is_casual_low_signal("Włącz proszę światło wszędzie.")
    assert not _is_casual_low_signal("Wyłącz światło w salonie")


def test_chat_processor_preface_suppresses_web_search_in_agent_mode_or_falsy_use_web():
    from src.chat_processor import ChatProcessor
    processor = ChatProcessor(memory_manager=None, personal_docs_manager=None)

    # With use_web="false" or in agent_mode, web_sources must stay empty
    preface, rag, web_sources = processor.build_context_preface(
        message="Włącz proszę światło wszędzie.",
        session=None,
        use_web="false",
        use_memory=False,
        use_rag=False,
        agent_mode=False,
    )
    assert web_sources == []

    # Even with use_web=True, agent mode must never run pre-search
    preface, rag, web_sources = processor.build_context_preface(
        message="Włącz proszę światło wszędzie.",
        session=None,
        use_web=True,
        use_memory=False,
        use_rag=False,
        agent_mode=True,
    )
    assert web_sources == []


def test_needs_auto_name_identifies_live_voice_placeholders():
    from routes.chat_helpers import needs_auto_name

    # Placeholders that need auto naming
    assert needs_auto_name("")
    assert needs_auto_name("Chat")
    assert needs_auto_name("Chat: Włącz światło w pokoju")
    assert needs_auto_name("Live Voice")
    assert needs_auto_name("Live Voice: Czy mogłabyś wyłączyć")
    assert needs_auto_name("Voice: Wyłącz światło")
    assert needs_auto_name("New Chat")
    assert needs_auto_name("New Chat 123")
    assert needs_auto_name("gemini-2.5-flash 10:40:20 PM")

    # Real, established titles must NOT be overwritten
    assert not needs_auto_name("Wyłączenie wszystkich świateł")
    assert not needs_auto_name("Przypomnienie o nagrodzie Opera GX")
    assert not needs_auto_name("Rozmowa o planach na jutro")


def test_chat_handler_updates_live_voice_placeholder_name():
    from src.chat_handler import ChatHandler
    from unittest.mock import MagicMock

    handler = ChatHandler(
        session_manager=MagicMock(),
        memory_manager=MagicMock(),
        chat_processor=MagicMock(),
        research_handler=MagicMock(),
        preset_manager=MagicMock(),
        upload_handler=MagicMock(),
    )

    class FakeSession:
        def __init__(self, name=""):
            self.id = "voice_test_123"
            self.name = name

    sess = FakeSession(name="Live Voice")
    handler.update_session_name_if_needed(sess, "Czy mogłabyś wyłączyć wszystkie światła?")
    assert sess.name == "Live Voice: Czy mogłabyś wyłączyć wszystkie światła?"
    handler.session_manager.update_session_name.assert_called_with("voice_test_123", sess.name)

    # An established title must not be changed
    established_sess = FakeSession(name="Wyłączenie wszystkich świateł")
    handler.update_session_name_if_needed(established_sess, "I jeszcze lampkę nocną")
    assert established_sess.name == "Wyłączenie wszystkich świateł"


@pytest.mark.asyncio
async def test_auto_name_session_renames_voice_session(monkeypatch):
    from routes.chat_helpers import auto_name_session
    from unittest.mock import AsyncMock, MagicMock

    fake_llm_call = AsyncMock(return_value="Tytuł: Wyłączenie wszystkich świateł")
    monkeypatch.setattr("src.llm_core.llm_call_async", fake_llm_call)
    monkeypatch.setattr(
        "src.task_endpoint.resolve_task_endpoint",
        lambda url, model, headers, owner=None: ("http://internal/chat", "test-model", {"Authorization": "Bearer test"}),
    )

    class FakeMsg:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    class FakeSession:
        def __init__(self):
            self.id = "voice_20260923_120000_123"
            self.name = "Live Voice: Czy mogłabyś wyłączyć"
            self.endpoint_url = "http://internal/chat"
            self.model = "test-model"
            self.headers = {}
            self.owner = "bartosz"
            self.history = [
                FakeMsg("user", "Czy mogłabyś wyłączyć wszystkie światła w mieszkaniu?"),
                FakeMsg("assistant", "Wszystkie światła zostały wyłączone."),
            ]

    session_manager = MagicMock()
    sess = FakeSession()

    await auto_name_session(session_manager, sess)

    session_manager.update_session_name.assert_called_once_with(
        "voice_20260923_120000_123", "Wyłączenie wszystkich świateł"
    )


def test_native_voice_gateway_speaks_asked_question_when_answer_has_preface():
    response = httpx.Response(
        200,
        content=(
            'data: {"delta":"Szukam pogody dla Krakowa na jutro."}\n\n'
            'data: {"type":"ask_user","data":{"voice_prompt":"Use web fetch. Say yes or tak to approve."}}\n\n'
            "data: [DONE]\n\n"
        ),
        request=httpx.Request("POST", "http://odysseus.internal/api/chat_stream"),
    )

    answer = OdysseusVoiceGateway._stream_result(response)
    assert "Szukam pogody dla Krakowa na jutro." in answer
    assert "Use web fetch. Say yes or tak to approve." in answer


@pytest.mark.asyncio
async def test_server_voice_store_preserves_session_while_approval_pending(tmp_path):
    from src.tool_approvals import tool_approval_store
    from src.tool_capabilities import capabilities_for_tool

    store = ServerVoiceSessionStore(tmp_path)
    session_id = await store.begin()

    approval = tool_approval_store.create(
        owner="bartosz",
        session_id=session_id,
        origin_run_id="run_1",
        tool_name="home_assistant_control",
        content='{"action": "turn_off"}',
        workspace="",
        external_untrusted_context_seen=True,
        capabilities=capabilities_for_tool("home_assistant_control"),
    )

    try:
        await store.end()
        assert store.manager.get_current_session_id() == session_id

        next_session_id = await store.begin()
        assert next_session_id == session_id
    finally:
        tool_approval_store.consume(
            approval.approval_id,
            decision="approve_task",
            owner="bartosz",
            session_id=session_id,
        )



