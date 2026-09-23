import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.conversation.speech import SpeechSynthesisRequest, SynthesizedSpeech
from backend.audio.tts_router import TTSRouter, get_tts_router
from backend.core.routers.voice_http_router import register_voice_http_routes


class MockSynthesizer:
    def __init__(self, name="mock"):
        self.name = name

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedSpeech:
        return SynthesizedSpeech(
            audio=b"RIFF_MOCK_AUDIO_DATA",
            mime_type="audio/pcm;rate=24000",
            sample_rate=24000,
        )


@pytest.mark.asyncio
async def test_tts_router_selection_and_fallback():
    router = TTSRouter(default_provider="mock_primary")
    mock_primary = MockSynthesizer("mock_primary")
    mock_secondary = MockSynthesizer("mock_secondary")

    router.register_provider("mock_primary", mock_primary)
    router.register_provider("mock_secondary", mock_secondary)

    # 1. Successful primary synthesis
    res = await router.synthesize("Witaj w MonikAI Workspace!")
    assert res.audio == b"RIFF_MOCK_AUDIO_DATA"
    assert res.sample_rate == 24000

    # 2. Test fallback when primary throws error
    failing_primary = MockSynthesizer("failing")
    failing_primary.synthesize = AsyncMock(side_effect=RuntimeError("Quota exceeded"))
    router.register_provider("failing", failing_primary)
    router.set_provider("failing")

    # Should gracefully fall back to mock_secondary
    fallback_res = await router.synthesize("Test awaryjnego providera")
    assert fallback_res.audio == b"RIFF_MOCK_AUDIO_DATA"


def test_voice_http_endpoints():
    app = FastAPI()
    register_voice_http_routes(app)
    client = TestClient(app)

    # 1. Get status
    status_res = client.get("/api/v1/voice/status")
    assert status_res.status_code == 200
    assert "voice_settings" in status_res.json()

    # 2. Select provider
    select_res = client.post("/api/v1/voice/select", json={"provider": "gemini", "voice": "Leda"})
    assert select_res.status_code == 200
    assert select_res.json()["ok"] is True

    # 3. Select xtts provider with leda
    select_xtts = client.post("/api/v1/voice/select", json={"provider": "xtts", "voice": "leda", "model": "XTTS-v2"})
    assert select_xtts.status_code == 200
    assert select_xtts.json()["ok"] is True


@pytest.mark.asyncio
async def test_voice_output_service_xtts(monkeypatch):
    from backend.conversation.voice_output import VoiceOutputService

    service = VoiceOutputService()
    monkeypatch.setattr(
        service,
        "_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "xtts",
            "tts_model": "XTTS-v2",
            "tts_voice": "leda",
            "tts_speed": "1",
            "tts_language": "pl",
            "tts_volume": 1.0,
            "tts_auto_read": False,
        },
    )

    fake_wav = b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 48000
    captured_kwargs = {}

    def fake_synthesize(self, text, voice=None, language=None, provider=None, **kwargs):
        captured_kwargs["voice"] = voice
        captured_kwargs["provider"] = provider
        return fake_wav

    mock_tts = type("MockTTSService", (), {
        "available": True,
        "synthesize": fake_synthesize,
    })()

    monkeypatch.setattr("backend.odysseus.services.tts.tts_service.get_tts_service", lambda: mock_tts)

    status = service.get_status()
    assert status["provider"] == "xtts"
    assert status["voice"] == "leda"
    assert "xtts" in status["available_providers"]
    assert status["available"] is True

    rendered = await service.synthesize("Cześć, tu Monika!", voice="leda")
    assert rendered.audio == fake_wav
    assert rendered.sample_rate == 24000
    assert captured_kwargs["voice"] == "leda"
    assert captured_kwargs["provider"] == "xtts"

