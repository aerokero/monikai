from __future__ import annotations

import asyncio
from dataclasses import asdict

from backend.core.routers.frontend_router import is_active_frontend_sid


def register_system_frontend_handlers(
    sio,
    *,
    get_audio_loop,
    get_personality_system,
    get_spotify_manager,
    get_settings,
    save_settings,
    shutdown_and_exit,
    mark_user_activity,
):
    @sio.event
    async def get_personality_status(sid):
        try:
            from backend.core.runtimes import v2_runtime
            runtime = v2_runtime.get()
            if runtime is not None:
                await sio.emit("personality_status", await runtime.get_status_payload(), room=sid)
                return
        except Exception:
            pass

        if get_personality_system():
            data = asdict(get_personality_system().state)
            aff = max(0.0, min(100.0, float(data.get("affection", 0))))
            score = aff / 10.0
            full = int(score)
            hearts = "❤️" * full + "🤍" * (10 - full)
            data["affection_hearts"] = f"{hearts} ({score:.1f}/10)"
            await sio.emit("personality_status", data, room=sid)

    @sio.event
    async def video_frame(sid, data):
        if not is_active_frontend_sid(sid):
            return
        image_data = data.get("image")
        audio_loop = get_audio_loop()
        if image_data and audio_loop:
            asyncio.create_task(audio_loop.send_frame(image_data))

    @sio.on("screen_frame")
    async def screen_frame(sid, data):
        if not is_active_frontend_sid(sid):
            return
        audio_loop = get_audio_loop()
        if audio_loop and isinstance(data, dict):
            asyncio.create_task(audio_loop.send_screen_frame(data.get("image")))

    @sio.on("client_audio_chunk")
    async def client_audio_chunk(sid, data):
        if not is_active_frontend_sid(sid):
            return
        audio_loop = get_audio_loop()
        if audio_loop and isinstance(data, dict):
            await audio_loop.send_client_audio(
                data.get("data"),
                data.get("sample_rate", 16000),
            )

    @sio.event
    async def user_activity(sid, data):
        try:
            text = (data or {}).get("text") or ""
            mark_user_activity(get_audio_loop(), text)
        except Exception:
            pass

    @sio.event
    async def spotify_get_status(sid, data=None):
        _ = data
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            await sio.emit("spotify_status", {"ok": False, "error": "spotify manager unavailable"}, room=sid)
            return
        try:
            await sio.emit("spotify_status", {"ok": True, "status": spotify_manager.status()}, room=sid)
        except Exception as e:
            await sio.emit("spotify_status", {"ok": False, "error": str(e)}, room=sid)

    @sio.event
    async def spotify_get_auth_url(sid, data=None):
        _ = data
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            await sio.emit("spotify_auth_url", {"ok": False, "error": "spotify manager unavailable"}, room=sid)
            return
        try:
            url = spotify_manager.build_auth_url()
            await sio.emit("spotify_auth_url", {"ok": True, "url": url}, room=sid)
        except Exception as e:
            await sio.emit("spotify_auth_url", {"ok": False, "error": str(e)}, room=sid)

    @sio.event
    async def spotify_refresh_token(sid, data=None):
        _ = data
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            await sio.emit("spotify_status", {"ok": False, "error": "spotify manager unavailable"}, room=sid)
            return
        try:
            st = spotify_manager.refresh_access_token()
            await sio.emit("spotify_status", {"ok": True, "status": st}, room=sid)
        except Exception as e:
            await sio.emit("spotify_status", {"ok": False, "error": str(e)}, room=sid)

    @sio.event
    async def kill_server(sid, data=None):
        _ = data
        print("[SERVER] Kill server requested from frontend")
        asyncio.create_task(shutdown_and_exit("[SERVER] Kill server requested from frontend."))
        await asyncio.sleep(0.1)
