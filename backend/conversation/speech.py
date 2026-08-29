"""Speech-only delivery for already-authored conversation text.

The synthesizer receives immutable display text and may only turn it into
audio. It is deliberately separate from the response-author provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


DEFAULT_SPEECH_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_SAMPLE_RATE = 24_000


@dataclass(frozen=True)
class SpeechSynthesisRequest:
    text: str
    voice: str
    model: str = DEFAULT_SPEECH_MODEL

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("speech text cannot be empty")
        if not self.voice.strip():
            raise ValueError("speech voice cannot be empty")


@dataclass(frozen=True)
class SynthesizedSpeech:
    audio: bytes
    mime_type: str = "audio/pcm;rate=24000"
    sample_rate: int = DEFAULT_SAMPLE_RATE

    def __post_init__(self) -> None:
        if not self.audio:
            raise ValueError("synthesized audio cannot be empty")


class SpeechSynthesizer(Protocol):
    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedSpeech:
        """Render ``request.text`` as audio without authoring new text."""


def _sample_rate_from_mime(mime_type: str) -> int:
    match = re.search(r"(?:rate|sample_rate)=(\d+)", mime_type or "", re.I)
    return int(match.group(1)) if match else DEFAULT_SAMPLE_RATE


class GeminiSpeechSynthesizer:
    """Dedicated Gemini TTS adapter; this does not use a Live dialogue session."""

    def __init__(self, *, api_key: str | None = None, client=None):
        self._api_key = api_key
        self._client = client

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedSpeech:
        from google.genai import types

        prompt_content = (
            f"Read the following text out loud:\n{request.text}"
            if "tts" in str(request.model).lower()
            else request.text
        )
        response = await self._get_client().aio.models.generate_content(
            model=request.model,
            contents=prompt_content,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=request.voice
                        )
                    )
                ),
            ),
        )
        parts = list(getattr(response, "parts", None) or [])
        if not parts:
            candidates = list(getattr(response, "candidates", None) or [])
            if candidates:
                content = getattr(candidates[0], "content", None)
                parts = list(getattr(content, "parts", None) or [])
        for part in parts:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                mime_type = (
                    str(getattr(inline, "mime_type", "") or "")
                    or "audio/pcm;rate=24000"
                )
                return SynthesizedSpeech(
                    audio=bytes(data),
                    mime_type=mime_type,
                    sample_rate=_sample_rate_from_mime(mime_type),
                )
        raise RuntimeError("TTS provider returned no audio")

