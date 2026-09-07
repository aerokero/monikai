import asyncio
from types import SimpleNamespace

from backend.core import model_config as model_config
from backend.core import monikai
from backend.core.monikai import (
    AudioLoop,
    _build_voice_realtime_input_config,
    _build_voice_renderer_thinking_config,
    _streaming_transcript_update,
)
from backend.conversation.speech import SynthesizedSpeech


def test_thinker_renderer_uses_manual_activity_boundaries():
    config = _build_voice_realtime_input_config(renderer_only=True)
    assert config.automatic_activity_detection.disabled is True

    ordinary = _build_voice_realtime_input_config(renderer_only=False)
    assert ordinary.automatic_activity_detection.disabled is False


def test_renderer_disables_native_thinking_on_gemini_25(monkeypatch):
    monkeypatch.setattr(model_config, "_is_31", False)
    config = _build_voice_renderer_thinking_config()
    assert config.thinking_budget == 0
    assert config.include_thoughts is False


def test_renderer_uses_minimal_floor_on_gemini_31(monkeypatch):
    monkeypatch.setattr(model_config, "_is_31", True)
    config = _build_voice_renderer_thinking_config()
    level = getattr(config.thinking_level, "value", config.thinking_level)
    assert str(level).lower() == "minimal"
    assert config.include_thoughts is False


def test_streaming_transcript_distinguishes_growth_revision_and_new_chunk():
    assert _streaming_transcript_update("Hej", "Hej, co słychać?") == (", co słychać?", False)

    repeated = "Rozumiem. Kontynuuj, słucham dokładnie."
    corrected = "Rozumiem. Kontynuuj — słucham dokładnie."
    assert _streaming_transcript_update(repeated, corrected) == (corrected, True)

    assert _streaming_transcript_update("Pierwsze zdanie.", "Drugie zdanie.") == (
        "Drugie zdanie.",
        False,
    )


async def test_manual_voice_turn_delivers_brief_before_activity_end():
    events = []

    class FakeThinker:
        async def prepare_spoken_reply(self, text):
            events.append(("prepare", text))
            return "Gotowe."

        def mark_voice_delivered(self):
            events.append(("marked", True))

    class FakeSession:
        async def send_realtime_input(self, **kwargs):
            events.append((next(iter(kwargs)), kwargs))

    loop = AudioLoop.__new__(AudioLoop)
    loop.chat_buffer = {"sender": "Ty", "text": "pełna wypowiedź użytkownika"}
    loop._last_input_transcription = ""
    loop.thinker = FakeThinker()
    loop.session = FakeSession()
    loop.out_queue = None
    loop._is_speaking = False
    loop._manual_voice_activity_open = True
    loop._voice_finalize_task = asyncio.current_task()
    loop._suppress_spoken_output = False
    loop._dedicated_speech_enabled = lambda: True

    async def deliver(reply, *, speak):
        events.append(("deliver", (reply, speak)))
        return True

    loop.deliver_authored_reply = deliver

    await loop._finalize_manual_voice_turn()

    assert [kind for kind, _ in events] == ["prepare", "activity_end", "deliver", "marked"]
    assert events[2][1] == ("Gotowe.", True)
    assert not any(kind == "text" for kind, _ in events)
    assert loop._suppress_spoken_output is True
    assert loop._manual_voice_activity_open is False


async def test_authored_reply_is_displayed_and_synthesized_without_rewrite(monkeypatch):
    authored = "Po prostu siadasz i robisz."
    transcripts = []
    requests = []

    class FakeSynthesizer:
        async def synthesize(self, request):
            requests.append(request)
            return SynthesizedSpeech(audio=b"\x00\x01" * 8)

    monkeypatch.setitem(
        monikai.APP_SETTINGS,
        "speech",
        {
            "delivery_mode": "dedicated_tts",
            "model": "test-tts",
            "voice": "Sulafat",
            "timeout_sec": 2.0,
        },
    )
    loop = AudioLoop.__new__(AudioLoop)
    loop.chat_buffer = {"sender": None, "text": ""}
    loop._ai_turn_open = False
    loop.mark_ai_activity = lambda text: None
    loop.on_transcription = transcripts.append
    loop.flush_chat = lambda: None
    loop._last_speech_trace = {}
    loop.enable_audio_io = True
    loop.audio_in_queue = asyncio.Queue()
    loop.on_audio_data = None
    loop.speech_synthesizer = FakeSynthesizer()

    assert await loop.deliver_authored_reply(authored, speak=True) is True

    assert transcripts[0]["text"] == authored
    assert transcripts[0]["authored"] is True
    assert requests[0].text == authored
    assert requests[0].model == "test-tts"
    assert await loop.audio_in_queue.get() == b"\x00\x01" * 8
    assert loop._last_speech_trace["status"] == "audio_delivered"


async def test_canonical_authored_reply_uses_renderer_settings_not_legacy_speech(monkeypatch):
    calls = []

    class FakeRenderer:
        def get_status(self):
            return {"provider": "gemini", "available": True}

        async def synthesize(self, text, **kwargs):
            calls.append((text, kwargs))
            return SynthesizedSpeech(audio=b"\x00\x01" * 8)

    monkeypatch.setitem(
        monikai.APP_SETTINGS,
        "speech",
        {
            "delivery_mode": "dedicated_tts",
            "provider": "elevenlabs",
            "model": "legacy-model-that-must-not-win",
            "voice": "legacy-voice-that-must-not-win",
            "timeout_sec": 2.0,
        },
    )
    loop = AudioLoop.__new__(AudioLoop)
    loop.conversation_gateway = object()
    loop.voice_output_service = FakeRenderer()
    loop.chat_buffer = {"sender": None, "text": ""}
    loop._ai_turn_open = False
    loop.mark_ai_activity = lambda text: None
    loop.on_transcription = lambda payload: None
    loop.flush_chat = lambda: None
    loop._last_speech_trace = {}
    loop.enable_audio_io = True
    loop.audio_in_queue = asyncio.Queue()
    loop.on_audio_data = None

    assert await loop.deliver_authored_reply("Odpowiedź Odysseusa.", speak=True) is True
    assert calls == [("Odpowiedź Odysseusa.", {})]
    assert await loop.audio_in_queue.get() == b"\x00\x01" * 8


def test_canonical_live_transcript_is_not_persisted_in_legacy_history():
    logged = []
    loop = AudioLoop.__new__(AudioLoop)
    loop.conversation_gateway = object()
    loop.chat_buffer = {"sender": "Ty", "text": "transportowy transkrypt"}
    loop.session_manager = SimpleNamespace(log_chat=lambda *args: logged.append(args))
    loop._last_input_transcription = "transportowy transkrypt"
    loop._last_output_transcription = ""
    loop._last_spoken_transcription = ""
    loop._emitted_thoughts_count = 0
    loop._is_new_turn = False

    loop.flush_chat()

    assert logged == []
    assert loop.chat_buffer == {"sender": None, "text": ""}


async def test_canonical_manual_voice_turn_calls_odysseus_once_before_delivery():
    events = []

    class FakeGateway:
        async def generate(self, text, **kwargs):
            events.append(("generate", text, kwargs))
            return "Odpowiedź z Odysseusa."

    class FakeSession:
        async def send_realtime_input(self, **kwargs):
            events.append(("live", kwargs))

    loop = AudioLoop.__new__(AudioLoop)
    loop.conversation_gateway = FakeGateway()
    loop.conversation_model = "gemini-2.5-flash"
    loop.conversation_endpoint_id = "gemini-text"
    loop.conversation_preset_id = "monika"
    loop.conversation_session_id = "live-test"
    loop.chat_buffer = {"sender": "Ty", "text": "pytanie głosowe"}
    loop._last_input_transcription = ""
    loop.session = FakeSession()
    loop.out_queue = None
    loop._is_speaking = False
    loop._manual_voice_activity_open = True
    loop._voice_finalize_task = asyncio.current_task()
    loop._suppress_spoken_output = True

    async def deliver(reply, *, speak):
        events.append(("deliver", reply, speak))

    loop.deliver_authored_reply = deliver

    await loop._finalize_manual_voice_turn()

    assert [event[0] for event in events] == ["generate", "live", "deliver"]
    assert events[0][1] == "pytanie głosowe"
    assert events[2] == ("deliver", "Odpowiedź z Odysseusa.", True)


async def test_lore_learning_runs_after_matching_authored_turn(monkeypatch):
    captured = []
    finished = asyncio.Event()

    class FakeLearningEngine:
        async def propose_from_turn(self, **kwargs):
            captured.append(kwargs)
            finished.set()
            return []

    monkeypatch.setitem(
        monikai.APP_SETTINGS,
        "lore_learning",
        {"enabled": True, "timeout_sec": 1.0},
    )
    loop = AudioLoop.__new__(AudioLoop)
    loop.lore_learning_engine = FakeLearningEngine()
    loop.thinker = SimpleNamespace(
        last_trace={
            "status": "prepared",
            "source": "Pracuję w Warszawie.",
            "reply_core": "Rozumiem.",
        }
    )
    loop.session_manager = SimpleNamespace(
        get_current_session_id=lambda: "session-1"
    )

    loop._schedule_lore_learning("Rozumiem.")
    await asyncio.wait_for(finished.wait(), timeout=1.0)

    assert captured == [
        {
            "conversation_id": "session-1",
            "user_text": "Pracuję w Warszawie.",
            "assistant_reply": "Rozumiem.",
        }
    ]
