"""HTTP API endpoints for Modular Voice & TTS Router."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, Response
from pydantic import BaseModel

from backend.audio.tts_router import get_tts_router
from backend.conversation.voice_output import get_voice_output_service, pcm_to_wav


class SelectVoiceRequest(BaseModel):
    provider: str
    voice: Optional[str] = None
    model: Optional[str] = None
    volume: Optional[float] = None


class VoiceVolumeRequest(BaseModel):
    volume: float


class SynthesizeVoiceRequest(BaseModel):
    text: str
    provider: Optional[str] = None
    voice: Optional[str] = None


class TTSRequest(BaseModel):
    text: str
    format: str = "audio"


def register_voice_http_routes(app):
    def _persist_canonical_voice_settings(
        provider: Optional[str],
        voice: Optional[str] = None,
        model: Optional[str] = None,
        volume: Optional[float] = None,
    ) -> None:
        """Persist the voice choice in Odysseus' settings store when present.

        The desktop client historically used ``TTSRouter``'s process-local
        selection while the web client used Odysseus settings.  Keeping the
        compatibility endpoint, but writing the canonical settings as well,
        makes both clients select the same renderer after a reload.
        """
        try:
            from src.settings import load_settings, save_settings
        except Exception:
            return
        settings = dict(load_settings() or {})
        if provider is not None:
            settings["tts_provider"] = str(provider or "disabled").strip().lower()
        if voice:
            settings["tts_voice"] = str(voice).strip()
        if model:
            settings["tts_model"] = str(model).strip()
        if volume is not None:
            try:
                normalized = float(volume)
            except (TypeError, ValueError):
                normalized = 1.0
            if normalized > 1.0:
                normalized /= 100.0
            settings["tts_volume"] = max(0.0, min(1.0, normalized))
        save_settings(settings)

    @app.get("/api/v1/voice/status")
    async def get_voice_status():
        router = get_tts_router()
        canonical = get_voice_output_service().get_status()
        legacy = router.get_status()
        return {
            "status": "ok",
            "voice_settings": {
                **legacy,
                "current_provider": canonical["provider"],
                "selected_models": {
                    **legacy.get("selected_models", {}),
                    canonical["provider"]: canonical["model"],
                },
                "selected_voices": {
                    **legacy.get("selected_voices", {}),
                    canonical["provider"]: canonical["voice"],
                },
                "canonical": canonical,
            },
        }

    @app.post("/api/v1/voice/select")
    async def select_voice_provider(req: SelectVoiceRequest):
        router = get_tts_router()
        provider = str(req.provider or "disabled").strip().lower()
        if provider != "disabled":
            ok = router.set_provider(provider)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Nieznany provider TTS: {req.provider}")
            if req.voice:
                router.set_voice(provider, req.voice)
            if req.model:
                router.set_model(provider, req.model)
        _persist_canonical_voice_settings(provider, req.voice, req.model, req.volume)
        canonical = get_voice_output_service().get_status()
        return {
            "ok": True,
            "voice_settings": {
                **router.get_status(),
                "current_provider": canonical["provider"],
                "canonical": canonical,
            },
        }

    @app.post("/api/v1/voice/volume")
    async def set_voice_volume(req: VoiceVolumeRequest):
        _persist_canonical_voice_settings(provider=None, volume=req.volume)
        return {"ok": True, "volume": get_voice_output_service().get_status()["volume"]}

    @app.post("/api/v1/voice/synthesize")
    async def synthesize_voice(req: SynthesizeVoiceRequest):
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Tekst nie może być pusty")

        try:
            service = get_voice_output_service()
            res = await service.synthesize(text=req.text, provider=req.provider, voice=req.voice)
            return {
                "ok": True,
                "mime_type": res.mime_type,
                "sample_rate": res.sample_rate,
                "audio_base64": base64.b64encode(res.audio).decode("ascii"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Błąd syntezy mowy: {e}")

    # Browser read-aloud API.  This is deliberately backed by the same
    # VoiceOutputService as Live's dedicated renderer, while keeping the old
    # /api/v1/voice contract for the desktop client.
    @app.get("/api/tts/stats")
    async def get_tts_stats():
        return get_voice_output_service().get_status()

    @app.post("/api/tts/synthesize")
    async def synthesize_tts(req: TTSRequest):
        if not req.text.strip():
            raise HTTPException(status_code=400, detail={"message": "Tekst nie może być pusty"})
        try:
            rendered = await get_voice_output_service().synthesize(req.text)
            audio = rendered.audio
            mime = rendered.mime_type.split(";", 1)[0]
            if mime == "audio/pcm":
                audio = pcm_to_wav(audio, rendered.sample_rate)
                mime = "audio/wav"
            return Response(content=audio, media_type=mime)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail={"message": str(exc)})
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"message": f"Synthesis failed: {exc}"})

    @app.post("/api/tts/clear-cache")
    async def clear_tts_cache():
        get_voice_output_service().clear_cache()
        return {"success": True}
