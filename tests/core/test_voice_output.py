from __future__ import annotations

import io
import wave

import pytest

from backend.conversation.speech import SynthesizedSpeech
from backend.conversation.voice_output import VoiceOutputService, speech_to_live_pcm


def test_speech_to_live_pcm_unwraps_wav():
    raw = b"\x01\x02" * 4
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24_000)
        output.writeframes(raw)

    rendered = SynthesizedSpeech(
        audio=buffer.getvalue(),
        mime_type="audio/wav",
        sample_rate=24_000,
    )
    assert speech_to_live_pcm(rendered) == raw


def test_speech_to_live_pcm_rejects_compressed_audio():
    rendered = SynthesizedSpeech(audio=b"ID3fake", mime_type="audio/mpeg", sample_rate=44_100)
    with pytest.raises(RuntimeError, match="cannot consume"):
        speech_to_live_pcm(rendered)


@pytest.mark.asyncio
async def test_voice_output_uses_canonical_settings_without_authoring_text(monkeypatch):
    calls = []

    class FakeRouter:
        async def synthesize(self, **kwargs):
            calls.append(kwargs)
            return SynthesizedSpeech(audio=b"\x00\x01" * 4)

    service = VoiceOutputService(router=FakeRouter())
    monkeypatch.setattr(
        service,
        "_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "gemini",
            "tts_model": "gemini-2.5-flash-preview-tts",
            "tts_voice": "Leda",
            "tts_speed": "1",
            "tts_auto_read": True,
        },
    )

    result = await service.synthesize("To jest już gotowa odpowiedź.")

    assert result.audio == b"\x00\x01" * 4
    assert calls == [
        {
            "text": "To jest już gotowa odpowiedź.",
            "provider": "gemini",
            "voice": "Leda",
            "model": "gemini-2.5-flash-preview-tts",
        }
    ]


@pytest.mark.asyncio
async def test_voice_output_never_sends_thinking_blocks_to_provider(monkeypatch):
    calls = []

    class FakeRouter:
        async def synthesize(self, **kwargs):
            calls.append(kwargs)
            return SynthesizedSpeech(audio=b"\x00\x01" * 4)

    service = VoiceOutputService(router=FakeRouter())
    monkeypatch.setattr(
        service,
        "_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "gemini",
            "tts_model": "gemini-2.5-flash-preview-tts",
            "tts_voice": "Leda",
            "tts_speed": "1",
            "tts_auto_read": True,
        },
    )

    await service.synthesize(
        '<think time="1.2">Nie wolno tego czytać. <think>Także tego.</think> '
        'To też jest ukryte.</think>\n'
        "To jest jedyna treść do przeczytania."
    )

    assert calls[0]["text"] == "To jest jedyna treść do przeczytania."


@pytest.mark.asyncio
async def test_voice_output_drops_unclosed_thinking_block(monkeypatch):
    calls = []

    class FakeRouter:
        async def synthesize(self, **kwargs):
            calls.append(kwargs)
            return SynthesizedSpeech(audio=b"\x00\x01" * 4)

    service = VoiceOutputService(router=FakeRouter())
    monkeypatch.setattr(
        service,
        "_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "gemini",
            "tts_model": "gemini-2.5-flash-preview-tts",
            "tts_voice": "Leda",
            "tts_speed": "1",
            "tts_auto_read": True,
        },
    )

    with pytest.raises(ValueError, match="no speakable content"):
        await service.synthesize("<think>To jest nadal proces myślenia...")

    assert calls == []
