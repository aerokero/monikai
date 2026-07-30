from types import SimpleNamespace

import pytest

from backend.conversation.speech import (
    GeminiSpeechSynthesizer,
    SpeechSynthesisRequest,
)


class _FakeModels:
    def __init__(self):
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        inline = SimpleNamespace(data=b"\x01\x02\x03\x04", mime_type="audio/pcm;rate=24000")
        return SimpleNamespace(parts=[SimpleNamespace(inline_data=inline)])


@pytest.mark.asyncio
async def test_tts_provider_receives_exact_authored_text():
    models = _FakeModels()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    provider = GeminiSpeechSynthesizer(client=client)
    authored = "Nie potrzebujesz specjalnego rozruchu — po prostu zaczynasz."

    result = await provider.synthesize(
        SpeechSynthesisRequest(
            text=authored,
            voice="Sulafat",
            model="gemini-3.1-flash-tts-preview",
        )
    )

    assert models.calls[0]["contents"] == authored
    assert models.calls[0]["model"] == "gemini-3.1-flash-tts-preview"
    assert result.audio == b"\x01\x02\x03\x04"
    assert result.sample_rate == 24000


def test_tts_request_rejects_empty_display_text():
    with pytest.raises(ValueError):
        SpeechSynthesisRequest(text="  ", voice="Sulafat")

