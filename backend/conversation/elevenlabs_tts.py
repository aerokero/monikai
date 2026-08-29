"""ElevenLabs Streaming TTS Provider for MonikAI Workspace."""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from .speech import SpeechSynthesisRequest, SpeechSynthesizer, SynthesizedSpeech

logger = logging.getLogger(__name__)

DEFAULT_ELEVENLABS_VOICE = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" default voice ID
DEFAULT_ELEVENLABS_MODEL = "eleven_multilingual_v2"


class ElevenLabsSpeechSynthesizer:
    """ElevenLabs TTS adapter supporting high quality streaming and multilingual speech."""

    def __init__(self, api_key: Optional[str] = None, voice_id: Optional[str] = None, model_id: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE)
        self.model_id = model_id or os.environ.get("ELEVENLABS_MODEL_ID", DEFAULT_ELEVENLABS_MODEL)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedSpeech:
        """Synthesize text into MP3 audio via ElevenLabs API."""
        api_key = self.api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured")

        voice = request.voice if request.voice and len(request.voice) > 10 else self.voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"

        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": request.text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                error_msg = f"ElevenLabs API error {resp.status_code}: {resp.text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            audio_bytes = resp.content
            return SynthesizedSpeech(audio=audio_bytes, mime_type="audio/mpeg", sample_rate=44100)

    async def stream_audio_chunks(self, text: str, voice: Optional[str] = None) -> AsyncIterator[bytes]:
        """Stream raw MP3 audio chunks from ElevenLabs."""
        api_key = self.api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured")

        voice_id = voice or self.voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as stream_resp:
                if stream_resp.status_code != 200:
                    raw_err = await stream_resp.aread()
                    raise RuntimeError(f"ElevenLabs stream error {stream_resp.status_code}: {raw_err.decode()}")
                async for chunk in stream_resp.aiter_bytes():
                    if chunk:
                        yield chunk
