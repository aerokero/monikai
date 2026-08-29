"""HTTP API endpoints for Modular Voice & TTS Router."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, Response
from pydantic import BaseModel

from backend.audio.tts_router import get_tts_router


class SelectVoiceRequest(BaseModel):
    provider: str
    voice: Optional[str] = None


class SynthesizeVoiceRequest(BaseModel):
    text: str
    provider: Optional[str] = None
    voice: Optional[str] = None


def register_voice_http_routes(app):
    @app.get("/api/v1/voice/status")
    async def get_voice_status():
        router = get_tts_router()
        return {"status": "ok", "voice_settings": router.get_status()}

    @app.post("/api/v1/voice/select")
    async def select_voice_provider(req: SelectVoiceRequest):
        router = get_tts_router()
        ok = router.set_provider(req.provider)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Nieznany provider TTS: {req.provider}")
        if req.voice:
            router.set_voice(req.provider, req.voice)
        return {"ok": True, "voice_settings": router.get_status()}

    @app.post("/api/v1/voice/synthesize")
    async def synthesize_voice(req: SynthesizeVoiceRequest):
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Tekst nie może być pusty")

        router = get_tts_router()
        try:
            res = await router.synthesize(text=req.text, provider=req.provider, voice=req.voice)
            return {
                "ok": True,
                "mime_type": res.mime_type,
                "sample_rate": res.sample_rate,
                "audio_base64": base64.b64encode(res.audio).decode("ascii"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Błąd syntezy mowy: {e}")
