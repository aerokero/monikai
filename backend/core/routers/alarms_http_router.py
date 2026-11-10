"""HTTP adapter for the alarm clock panel; same AlarmManager as voice/Telegram."""

from __future__ import annotations

import asyncio
import io
import re
import uuid
import wave
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from backend.services import alarm_manager as am

_SOUND_EXTS = {".wav", ".mp3", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac", ".webm"}
MAX_SOUND_BYTES = 20 * 1024 * 1024


def _safe_sound_name(filename: str) -> str:
    """Uploaded name -> plain file name inside SOUNDS_DIR (no paths, known audio ext)."""
    raw = Path(filename or "")
    ext = raw.suffix.lower()
    if ext not in _SOUND_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type; use one of {', '.join(sorted(_SOUND_EXTS))}")
    stem = re.sub(r"[^\w.\- ]+", "_", raw.stem).strip(" ._")[:60] or "sound"
    return stem + ext


def _tone_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(am.SAMPLE_RATE)
        w.writeframes(am.tone_pcm())
    return buf.getvalue()


def _manager():
    from src.voice_runtime import get_alarm_manager

    mgr = get_alarm_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="Alarm manager is not running")
    return mgr


def _state(mgr) -> Dict[str, Any]:
    now = datetime.now(am.TZ)
    alarms = []
    for a in mgr.list():
        nxt = am.next_time(a, now)
        alarms.append({**asdict(a), "next": nxt.isoformat() if nxt else None})
    try:
        sounds = sorted(p.name for p in am.SOUNDS_DIR.iterdir() if p.suffix.lower() in _SOUND_EXTS)
    except OSError:
        sounds = []
    return {
        "status": "ok",
        "alarms": alarms,
        "ringing": mgr.ringing.id if mgr.ringing else None,
        "sounds": sounds,
        "snooze_minutes": am.SNOOZE_MINUTES,
    }


def register_alarms_http_routes(app):
    @app.get("/api/alarms")
    async def list_alarms():
        return _state(_manager())

    @app.post("/api/alarms")
    async def save_alarm(payload: Dict[str, Any] = Body(...)):
        mgr = _manager()
        alarm_id = str(payload.get("id") or "")
        if alarm_id and alarm_id not in mgr.alarms:
            raise HTTPException(status_code=404, detail="Alarm not found")
        try:
            mgr.set(
                time=str(payload.get("time") or ""),
                days=payload.get("days") or [],
                date_str=str(payload.get("date") or ""),
                label=str(payload.get("label") or ""),
                sound=str(payload.get("sound") or ""),
                greeting=bool(payload.get("greeting", True)),
                alarm_id=alarm_id,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return _state(mgr)

    @app.delete("/api/alarms/{alarm_id}")
    async def delete_alarm(alarm_id: str):
        mgr = _manager()
        if not mgr.delete(alarm_id):
            raise HTTPException(status_code=404, detail="Alarm not found")
        return _state(mgr)

    @app.post("/api/alarms/{alarm_id}/enabled")
    async def set_alarm_enabled(alarm_id: str, payload: Dict[str, Any] = Body(...)):
        mgr = _manager()
        if not mgr.set_enabled(alarm_id, bool(payload.get("enabled"))):
            raise HTTPException(status_code=404, detail="Alarm not found")
        return _state(mgr)

    @app.get("/api/alarms/sounds/preview")
    async def preview_sound(name: str = ""):
        if not name:
            return Response(_tone_wav(), media_type="audio/wav")
        path = am.SOUNDS_DIR / Path(name).name
        if path.suffix.lower() not in _SOUND_EXTS or not path.is_file():
            raise HTTPException(status_code=404, detail="Sound not found")
        return FileResponse(path)

    @app.post("/api/alarms/sounds")
    async def upload_sound(file: UploadFile = File(...)):
        mgr = _manager()
        name = _safe_sound_name(file.filename)
        data = await file.read(MAX_SOUND_BYTES + 1)
        if len(data) > MAX_SOUND_BYTES:
            raise HTTPException(status_code=413, detail="Sound file is larger than 20 MB")
        am.SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = am.SOUNDS_DIR / f".upload-{uuid.uuid4().hex}{Path(name).suffix}"
        tmp.write_bytes(data)
        try:
            # The alarm decodes with ffmpeg at ring time; reject what it cannot read now.
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-v", "error", "-i", str(tmp), "-t", "2", "-f", "null", "-",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, err = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                raise HTTPException(status_code=400, detail=f"Not a playable audio file: {err.decode(errors='replace').strip()[:200]}")
            tmp.replace(am.SOUNDS_DIR / name)
        finally:
            tmp.unlink(missing_ok=True)
        mgr.forget_sound(name)  # an overwritten file must be re-decoded
        return {**_state(mgr), "uploaded": name}

    @app.post("/api/alarms/ringing/stop")
    async def stop_ringing():
        mgr = _manager()
        mgr.stop()
        return _state(mgr)

    @app.post("/api/alarms/ringing/snooze")
    async def snooze_ringing(payload: Dict[str, Any] = Body(default={})):
        mgr = _manager()
        minutes = payload.get("minutes")
        mgr.snooze(int(minutes) if minutes else None)
        return _state(mgr)
