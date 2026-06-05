from __future__ import annotations

from fastapi import HTTPException, Response


def register_system_http_routes(app, *, get_spotify_manager, emit_to_frontend):
    @app.get("/status")
    async def status():
        return {"status": "running", "service": "MonikAI Backend"}

    @app.get("/spotify/status")
    async def spotify_status_http():
        spotify_manager = get_spotify_manager()
        if not spotify_manager:
            return {"ok": False, "error": "spotify manager unavailable"}
        try:
            return {"ok": True, "status": spotify_manager.status()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/spotify/auth/start")
    async def spotify_auth_start_http():
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
