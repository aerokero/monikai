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
