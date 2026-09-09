"""Unified TTS Router supporting Gemini Live/TTS, ElevenLabs, and fallback chains."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from backend.conversation.elevenlabs_tts import ElevenLabsSpeechSynthesizer
from backend.conversation.speech import (
    GeminiSpeechSynthesizer,
    SpeechSynthesisRequest,
    SpeechSynthesizer,
    SynthesizedSpeech,
)

logger = logging.getLogger(__name__)


class TTSRouter:
    """Manages speech synthesis provider selection, fallbacks, and voice catalogs."""

    def __init__(self, default_provider: str = "gemini"):
        self.default_provider = default_provider
        self.providers: Dict[str, Any] = {
            "gemini": GeminiSpeechSynthesizer(),
            "elevenlabs": ElevenLabsSpeechSynthesizer(),
        }
        self._builtin_provider_names = {"gemini", "elevenlabs"}
        self.selected_voices: Dict[str, str] = {
            "gemini": "Leda",
            "elevenlabs": "21m00Tcm4TlvDq8ikWAM",  # Rachel
        }
        self.selected_models: Dict[str, str] = {
            "gemini": "gemini-2.5-flash-preview-tts",
            "elevenlabs": "eleven_multilingual_v2",
        }

    def register_provider(self, name: str, synthesizer: Any) -> None:
        self.providers[name] = synthesizer

    def set_provider(self, name: str) -> bool:
        if name in self.providers:
            self.default_provider = name
            return True
        return False

    def set_voice(self, provider: str, voice: str) -> None:
        self.selected_voices[provider] = voice

    def set_model(self, provider: str, model: str) -> None:
        if model:
            self.selected_models[provider] = model

    def get_status(self) -> Dict[str, Any]:
        return {
            "current_provider": self.default_provider,
            "selected_voices": self.selected_voices,
            "selected_models": self.selected_models,
            "available_providers": list(self.providers.keys()),
            "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
            "elevenlabs_configured": bool(os.environ.get("ELEVENLABS_API_KEY")),
        }

    async def synthesize(
        self,
        text: str,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
    ) -> SynthesizedSpeech:
        """Synthesize text using chosen or default provider with graceful fallback."""
        target_provider = provider or self.default_provider
        target_voice = voice or self.selected_voices.get(target_provider, "Leda")
        target_model = model or self.selected_models.get(target_provider)

        synth = self.providers.get(target_provider)
        if not synth:
            synth = self.providers.get("gemini")
            target_provider = "gemini"
            target_voice = self.selected_voices.get("gemini", "Leda")
            target_model = self.selected_models.get("gemini")

        try:
            req = SpeechSynthesisRequest(
                text=text,
                voice=target_voice,
                language=language or "auto",
                **({"model": target_model} if target_model else {}),
            )
            return await synth.synthesize(req)
        except Exception as e:
            logger.warning(f"TTS synthesis failed on provider '{target_provider}': {e}. Falling back to secondary...")
            # Fallback chain
            # Prefer explicitly registered providers before the optional
            # network providers.  This keeps local/custom renderers useful as
            # deterministic fallbacks and avoids a configured Gemini key
            # unexpectedly winning over an operator's registered provider.
            fallback_names = [
                name for name in self.providers if name not in self._builtin_provider_names
            ] + [name for name in self.providers if name in self._builtin_provider_names]
            for fallback_name in fallback_names:
                fallback_synth = self.providers[fallback_name]
                if fallback_name != target_provider:
                    try:
                        fallback_voice = self.selected_voices.get(fallback_name, "Leda")
                        fallback_model = self.selected_models.get(fallback_name)
                        req = SpeechSynthesisRequest(
                            text=text,
                            voice=fallback_voice,
                            language=language or "auto",
                            **({"model": fallback_model} if fallback_model else {}),
                        )
                        return await fallback_synth.synthesize(req)
                    except Exception as fb_err:
                        logger.error(f"Fallback TTS '{fallback_name}' also failed: {fb_err}")

            raise RuntimeError(f"All TTS synthesis providers failed for: '{text[:40]}...'")


# Global singleton instance
_GLOBAL_TTS_ROUTER: Optional[TTSRouter] = None


def get_tts_router() -> TTSRouter:
    global _GLOBAL_TTS_ROUTER
    if _GLOBAL_TTS_ROUTER is None:
        _GLOBAL_TTS_ROUTER = TTSRouter()
    return _GLOBAL_TTS_ROUTER
