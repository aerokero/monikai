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

# Gemini's speech model can infer a language from text, but short Polish
# phrases without diacritics are ambiguous.  Supplying a BCP-47 code makes the
# pronunciation contract explicit and prevents the voice from drifting into
# an English reading of an otherwise Polish reply.
_TTS_LANGUAGE_CODES = {
    "pl": "pl-PL",
    "pl-pl": "pl-PL",
    "en": "en-US",
    "en-us": "en-US",
    "en-gb": "en-GB",
    "de": "de-DE",
    "es": "es-ES",
    "fr": "fr-FR",
    "it": "it-IT",
    "pt": "pt-BR",
    "pt-br": "pt-BR",
    "ja": "ja-JP",
    "zh": "cmn-CN",
    "hi": "hi-IN",
    "ru": "ru-RU",
    "uk": "uk-UA",
}


def normalize_speech_language(value: str | None) -> str:
    """Return a normalized language selector used by all speech providers."""
    return str(value or "auto").strip().lower().replace("_", "-") or "auto"


def speech_language_code(value: str | None) -> str | None:
    """Map an app language selector to a provider-neutral BCP-47 code."""
    normalized = normalize_speech_language(value)
    if normalized == "auto":
        return None
    if normalized in _TTS_LANGUAGE_CODES:
        return _TTS_LANGUAGE_CODES[normalized]
    if re.fullmatch(r"[a-z]{2}-[a-z]{2}", normalized):
        language, region = normalized.split("-", 1)
        return f"{language}-{region.upper()}"
    if re.fullmatch(r"[a-z]{2}", normalized):
        return normalized
    return None


def _detected_speech_language(text: str) -> str | None:
    """Detect only strong Polish hints for an otherwise automatic request."""
    value = str(text or "")
    if re.search(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", value):
        return "pl-PL"
    words = set(re.findall(r"[a-ząćęłńóśźż]+", value.casefold()))
    if len(
        words
        & {
            "ale",
            "czy",
            "dla",
            "jest",
            "mam",
            "masz",
            "nie",
            "oraz",
            "to",
            "tobie",
            "twoj",
            "wiem",
            "zeby",
        }
    ) >= 2:
        return "pl-PL"
    return None


@dataclass(frozen=True)
class SpeechSynthesisRequest:
    text: str
    voice: str
    model: str = DEFAULT_SPEECH_MODEL
    language: str = "auto"

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

        # Keep the authored transcript as the model input.  The old adapter
        # prefixed it with an English instruction, which made a Polish TTS
        # request less deterministic and violated the speech-only boundary.
        # ``language_code`` below carries the rendering instruction without
        # changing the words Monika authored or the text used in provider
        # tests/caches.
        speech_config_kwargs = {
            "voice_config": types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=request.voice
                )
            )
        }
        language_code = speech_language_code(request.language) or _detected_speech_language(
            request.text
        )
        if language_code:
            speech_config_kwargs["language_code"] = language_code

        try:
            speech_config = types.SpeechConfig(**speech_config_kwargs)
        except (TypeError, ValueError):
            # Older google-genai releases did not expose language_code on the
            # Python type even though the API accepted the rest of the TTS
            # request. Keep those installations functional and let Gemini's
            # text-language detection handle the request.
            speech_config_kwargs.pop("language_code", None)
            speech_config = types.SpeechConfig(**speech_config_kwargs)

        response = await self._get_client().aio.models.generate_content(
            model=request.model,
            contents=request.text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=speech_config,
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
