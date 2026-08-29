from __future__ import annotations

import os
from typing import Any, Callable, Optional
from fastapi import HTTPException, Response
from backend.core.routers.frontend_router import get_active_frontend_sid


def register_system_http_routes(
    app,
    *,
    get_spotify_manager: Optional[Callable[[], Any]] = None,
    get_audio_loop: Optional[Callable[[], Any]] = None,
    get_minecraft_bot_manager: Optional[Callable[[], Any]] = None,
    get_kasa_agent: Optional[Callable[[], Any]] = None,
    get_settings: Optional[Callable[[], Any]] = None,
    emit_to_frontend: Optional[Callable[..., Any]] = None,
):
    @app.get("/healthz")
    @app.get("/api/v1/health")
    async def health_check():
        return {"status": "ok", "service": "monikai"}

    @app.get("/status")
    @app.get("/api/v1/status")
    async def system_status():
        active_sid = get_active_frontend_sid()
        audio_loop = get_audio_loop() if get_audio_loop else None
        audio_status = "stopped"
        if audio_loop:
            audio_status = "paused" if getattr(audio_loop, "is_paused", False) else "running"

        spotify_status = "unavailable"
        if get_spotify_manager:
            sm = get_spotify_manager()
            if sm:
                try:
                    st = sm.status()
                    spotify_status = "connected" if st.get("logged_in") else "disconnected"
                except Exception:
                    spotify_status = "error"

        kasa_devices_count = 0
        if get_kasa_agent:
            ka = get_kasa_agent()
            if ka:
                kasa_devices_count = len(ka.serialize_devices())

        minecraft_status = "disabled"
        if get_minecraft_bot_manager:
            mb = get_minecraft_bot_manager()
            if mb and getattr(mb, "is_running", lambda: False)():
                minecraft_status = "running"
            elif mb:
                minecraft_status = "stopped"

        auth_configured = bool(str(os.getenv("MONIKAI_SOCKET_TOKEN") or "").strip())

        return {
            "status": "ok",
            "service": "MonikAI Workspace Backend",
            "version": "2.0-workspace",
            "client": {
                "connected": bool(active_sid),
                "active_sid": active_sid,
                "auth_required": auth_configured,
            },
            "subsystems": {
                "audio_loop": audio_status,
                "spotify": spotify_status,
                "smart_home_kasa_devices": kasa_devices_count,
                "minecraft": minecraft_status,
            },
        }

    @app.get("/spotify/status")
    async def spotify_status_http():
        if not get_spotify_manager:
            return {"ok": False, "error": "spotify manager unavailable"}
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            return {"ok": False, "error": "spotify manager unavailable"}
        try:
            return {"ok": True, "status": spotify_manager.status()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/spotify/auth/start")
    async def spotify_auth_start_http():
        if not get_spotify_manager:
            raise HTTPException(status_code=503, detail="spotify manager unavailable")
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            raise HTTPException(status_code=503, detail="spotify manager unavailable")
        try:
            url = spotify_manager.build_auth_url()
            return {"ok": True, "url": url}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/spotify/callback")
    async def spotify_auth_callback_http(
        code: str = "",
        state: str = "",
        error: str = "",
        error_description: str = "",
    ):
        if not get_spotify_manager:
            raise HTTPException(status_code=503, detail="spotify manager unavailable")
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            raise HTTPException(status_code=503, detail="spotify manager unavailable")
        if error:
            detail = str(error_description or error).strip() or "spotify authorization failed"
            raise HTTPException(status_code=400, detail=detail)
        if not code:
            raise HTTPException(status_code=400, detail="missing code")
        try:
            status_obj = spotify_manager.exchange_code(code, state=state)
            if emit_to_frontend:
                try:
                    await emit_to_frontend("spotify_status", {"ok": True, "status": status_obj})
                except Exception:
                    pass
            return Response(
                content=(
                    "<html><body style='font-family: sans-serif; padding: 24px;'>"
                    "<h2>Spotify connected.</h2>"
                    "<p>You can close this tab and return to MonikAI.</p>"
                    "</body></html>"
                ),
                media_type="text/html",
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

