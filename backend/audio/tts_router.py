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
        self.selected_voices: Dict[str, str] = {
            "gemini": "Leda",
            "elevenlabs": "21m00Tcm4TlvDq8ikWAM",  # Rachel
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

    def get_status(self) -> Dict[str, Any]:
        return {
            "current_provider": self.default_provider,
            "selected_voices": self.selected_voices,
            "available_providers": list(self.providers.keys()),
            "elevenlabs_configured": bool(os.environ.get("ELEVENLABS_API_KEY")),
        }

    async def synthesize(
        self,
        text: str,
        provider: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> SynthesizedSpeech:
        """Synthesize text using chosen or default provider with graceful fallback."""
        target_provider = provider or self.default_provider
        target_voice = voice or self.selected_voices.get(target_provider, "Leda")

        synth = self.providers.get(target_provider)
        if not synth:
            synth = self.providers.get("gemini")
            target_provider = "gemini"
            target_voice = self.selected_voices.get("gemini", "Leda")

        try:
            req = SpeechSynthesisRequest(text=text, voice=target_voice)
            return await synth.synthesize(req)
        except Exception as e:
            logger.warning(f"TTS synthesis failed on provider '{target_provider}': {e}. Falling back to secondary...")
            # Fallback chain
            for fallback_name, fallback_synth in self.providers.items():
                if fallback_name != target_provider:
                    try:
                        fallback_voice = self.selected_voices.get(fallback_name, "Leda")
                        req = SpeechSynthesisRequest(text=text, voice=fallback_voice)
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
