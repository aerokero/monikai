"""Canonical speech-output facade.

The conversation/model layer owns the words.  This module only chooses a
configured renderer and turns already-authored text into audio.  Browser TTS
is represented as a client-side provider; it never causes a second server
generation request.
"""

from __future__ import annotations

import asyncio
import os
import re
import wave
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from backend.audio.tts_router import TTSRouter, get_tts_router
from backend.conversation.speech import SynthesizedSpeech


DEFAULT_GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_ELEVENLABS_VOICE = "21m00Tcm4TlvDq8ikWAM"
_GEMINI_VOICES = {"leda", "aoede", "kore", "sulafat", "puck", "charon", "fenrir"}
_THINKING_TAG_RE = re.compile(r"</?(?:think(?:ing)?|thought)\b[^<>]*>", re.IGNORECASE)


def _strip_thinking_for_tts(text: str) -> str:
    """Return only user-facing text, never the model's ``<think>`` blocks.

    The browser filters before sending text to the API, but keeping the same
    boundary here protects every caller (including the desktop/Live path) and
    prevents reasoning text from entering provider caches.
    """
    value = str(text or "")
    if not value:
        return ""

    # Remove tagged blocks with a depth counter. A response can contain
    # multiple or nested tags, and a dangling opener must hide the remainder
    # of the stream rather than allowing partial reasoning into a queue.
    output = []
    cursor = 0
    depth = 0
    for match in _THINKING_TAG_RE.finditer(value):
        if depth == 0:
            output.append(value[cursor : match.start()])
        if match.group(0).startswith("</"):
            depth = max(0, depth - 1)
        else:
            depth += 1
        cursor = match.end()
    if depth == 0:
        output.append(value[cursor:])
    tagged_text = "".join(output)

    # Also handle the other internal reasoning-channel wrappers used by some
    # model gateways when the shared Odysseus package is available.
    try:
        from src.text_helpers import strip_think

        return strip_think(tagged_text, prose=False, prompt_echo=False).strip()
    except Exception:
        return tagged_text.strip()


def _safe_volume(value: Any, default: float = 1.0) -> float:
    """Normalize a stored voice level to the browser/WebAudio 0..1 range."""
    try:
        volume = float(value)
    except (TypeError, ValueError):
        volume = default
    # Accept percent values as a compatibility convenience for older clients.
    if volume > 1.0:
        volume /= 100.0
    return max(0.0, min(1.0, volume))


def _load_settings() -> Dict[str, Any]:
    try:
        from src.settings import load_settings

        return dict(load_settings() or {})
    except Exception:
        # Keep the API usable in isolated unit tests before the Odysseus
        # bridge has inserted its package root into sys.path.
        candidates = (
            Path(__file__).resolve().parents[2] / "data" / "odysseus" / "settings.json",
            Path(__file__).resolve().parents[2] / "data" / "settings.json",
        )
        for path in candidates:
            try:
                import json

                with path.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                if isinstance(raw, dict):
                    return raw
            except Exception:
                continue
        return {}


def _audio_mime(audio: bytes, fallback: str = "audio/wav") -> str:
    if audio[:4] == b"RIFF":
        return "audio/wav"
    if audio[:3] == b"ID3" or (
        len(audio) >= 2 and audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0
    ):
        return "audio/mpeg"
    return fallback


def pcm_to_wav(audio: bytes, sample_rate: int = 24_000) -> bytes:
    """Wrap mono 16-bit PCM so normal browser ``Audio`` can play it."""
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(int(sample_rate or 24_000))
        output.writeframes(audio)
    return buffer.getvalue()


def speech_to_live_pcm(speech: SynthesizedSpeech) -> bytes:
    """Return audio in the format used by the desktop Live playback queue.

    Gemini TTS already returns raw mono PCM.  Local Kokoro commonly returns a
    WAV container, so unwrap that container before it reaches the queue.  MP3
    is intentionally rejected here: the desktop client consumes PCM directly
    and must not interpret compressed bytes as samples.  MP3 remains valid for
    the browser read-aloud endpoint, which can hand it to ``<audio>``.
    """
    mime = str(speech.mime_type or "").split(";", 1)[0].lower()
    if mime == "audio/pcm":
        if int(speech.sample_rate or 24_000) != 24_000:
            raise RuntimeError(
                f"Live playback requires 24 kHz PCM, got {speech.sample_rate} Hz"
            )
        return speech.audio
    if mime in {"audio/wav", "audio/x-wav", "audio/wave"} or speech.audio[:4] == b"RIFF":
        try:
            with wave.open(BytesIO(speech.audio), "rb") as source:
                if source.getnchannels() != 1 or source.getsampwidth() != 2:
                    raise RuntimeError("Live playback requires mono 16-bit PCM")
                if source.getframerate() != 24_000:
                    raise RuntimeError(
                        f"Live playback requires 24 kHz PCM, got {source.getframerate()} Hz"
                    )
                return source.readframes(source.getnframes())
        except (wave.Error, EOFError) as exc:
            raise RuntimeError("Live playback received an invalid WAV stream") from exc
    raise RuntimeError(
        f"Live playback cannot consume {speech.mime_type or 'unknown audio'}; "
        "choose Gemini TTS or a local 24 kHz PCM renderer"
    )


class VoiceOutputService:
    """One provider boundary for read-aloud and dedicated Live rendering."""

    def __init__(self, router: Optional[TTSRouter] = None):
        self.router = router or get_tts_router()

    def _settings(self) -> Dict[str, Any]:
        settings = _load_settings()
        provider = str(settings.get("tts_provider", "disabled") or "disabled").strip().lower()
        model = str(settings.get("tts_model", "tts-1") or "tts-1").strip()
        voice = str(settings.get("tts_voice", "alloy") or "alloy").strip()
        language = str(settings.get("tts_language", "auto") or "auto").strip().lower()
        # Upgrade the old local Kokoro Polish profile in memory. Without this
        # compatibility bridge, an ASCII-only sentence could still be routed
        # through af_heart's English phonemizer after the Piper upgrade.
        if provider == "local" and language == "auto" and voice.lower() in {
            "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
            "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        }:
            model = "Piper"
            voice = "pl_PL-gosia-medium"
            language = "pl"
        return {
            "tts_enabled": settings.get("tts_enabled", True),
            "tts_provider": provider,
            "tts_model": model,
            "tts_voice": voice,
            "tts_speed": settings.get("tts_speed", "1"),
            "tts_language": language,
            "tts_volume": _safe_volume(settings.get("tts_volume", 1.0)),
            "tts_auto_read": bool(settings.get("tts_auto_read", False)),
        }

    def get_status(self) -> Dict[str, Any]:
        settings = self._settings()
        provider = settings["tts_provider"]
        enabled = settings["tts_enabled"] is not False

        if provider == "browser":
            available = enabled
        elif provider == "gemini":
            available = enabled and bool(os.environ.get("GEMINI_API_KEY"))
        elif provider == "elevenlabs":
            available = enabled and bool(os.environ.get("ELEVENLABS_API_KEY"))
        elif provider in {"local"} or provider.startswith("endpoint:"):
            try:
                from backend.odysseus.services.tts.tts_service import get_tts_service

                available = enabled and bool(get_tts_service().available)
            except Exception:
                available = False
        else:
            available = False

        return {
            "available": available,
            "ready": available,
            "provider": provider,
            "model": settings["tts_model"],
            "voice": settings["tts_voice"],
            "language": settings.get("tts_language", "auto"),
            "speed": settings["tts_speed"],
            "volume": settings["tts_volume"],
            "auto_read": settings["tts_auto_read"],
            "available_providers": ["disabled", "browser", "gemini", "elevenlabs", "local"],
            "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
            "elevenlabs_configured": bool(os.environ.get("ELEVENLABS_API_KEY")),
        }

    async def synthesize(
        self,
        text: str,
        *,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
    ) -> SynthesizedSpeech:
        if not str(text or "").strip():
            raise ValueError("speech text cannot be empty")

        speech_text = _strip_thinking_for_tts(text)
        if not speech_text:
            raise ValueError("speech text contains no speakable content")

        settings = self._settings()
        explicit_provider = provider is not None
        target = str(provider or settings["tts_provider"] or "disabled").strip().lower()
        if settings["tts_enabled"] is False and not explicit_provider:
            raise RuntimeError("TTS is disabled in settings")
        if target in {"disabled", "browser"}:
            raise RuntimeError(f"Provider '{target}' is client-side or disabled")

        selected_voice = str(voice or settings["tts_voice"] or "Leda").strip()
        selected_model = str(model or settings["tts_model"] or "").strip()

        if target in {"gemini", "elevenlabs"}:
            selected_language = language if language is not None else settings.get("tts_language", "auto")
            if target == "gemini" and selected_model in {"", "tts-1", "tts-1-hd", "gpt-4o-mini-tts"}:
                selected_model = DEFAULT_GEMINI_TTS_MODEL
            if target == "elevenlabs" and (
                not selected_model
                or selected_model in {"tts-1", "tts-1-hd", "gpt-4o-mini-tts", DEFAULT_GEMINI_TTS_MODEL}
                or selected_model.startswith("gemini-")
            ):
                selected_model = "eleven_multilingual_v2"
            if target == "elevenlabs" and (
                not selected_voice or selected_voice.lower() in _GEMINI_VOICES or selected_voice == "alloy"
            ):
                selected_voice = DEFAULT_ELEVENLABS_VOICE
            if target == "gemini" and (
                not selected_voice or selected_voice == DEFAULT_ELEVENLABS_VOICE
            ):
                selected_voice = "Leda"
            router_kwargs = {
                "text": speech_text,
                "provider": target,
                "voice": selected_voice,
                "model": selected_model or None,
            }
            # Preserve the compatibility contract for callers that leave the
            # selector at ``auto``; an explicit language is the useful part.
            if str(selected_language or "auto").strip().lower() != "auto":
                router_kwargs["language"] = selected_language
            return await self.router.synthesize(**router_kwargs)

        if target == "local" or target.startswith("endpoint:"):
            from backend.odysseus.services.tts.tts_service import get_tts_service

            selected_language = language if language is not None else settings.get("tts_language", "auto")
            audio = await asyncio.to_thread(
                get_tts_service().synthesize,
                speech_text,
                language=selected_language,
                provider=target,
            )
            if not audio:
                raise RuntimeError(f"Provider '{target}' returned no audio")
            return SynthesizedSpeech(
                audio=audio,
                mime_type=_audio_mime(audio),
                sample_rate=24_000,
            )

        raise ValueError(f"Unknown TTS provider: {target}")

    def clear_cache(self) -> None:
        try:
            from backend.odysseus.services.tts.tts_service import get_tts_service

            get_tts_service().clear_cache()
        except Exception:
            pass


_GLOBAL_VOICE_OUTPUT: Optional[VoiceOutputService] = None


def get_voice_output_service() -> VoiceOutputService:
    global _GLOBAL_VOICE_OUTPUT
    if _GLOBAL_VOICE_OUTPUT is None:
        _GLOBAL_VOICE_OUTPUT = VoiceOutputService()
    return _GLOBAL_VOICE_OUTPUT
