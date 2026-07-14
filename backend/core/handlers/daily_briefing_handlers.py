def register_daily_briefing_handlers(
    sio,
    *,
    runtime,
    save_settings,
    emit_to_frontend,
    settings,
):
    @sio.event
    async def get_daily_briefing(sid, data=None):
        req = data or {}
        language = req.get("language", "pl")
        force = bool(req.get("force", False))
        payload = await runtime.build_payload(language=language, force=force)
        await sio.emit("daily_briefing_data", payload, room=sid)

    @sio.event
    async def set_daily_briefing_profile(sid, data=None):
        data = data or {}
        runtime.set_profile(data.get("profile") or {})
        save_settings()

        runtime.invalidate_cache()

        language = data.get("language", "pl")
        payload = await runtime.build_payload(language=language, force=True)
        await sio.emit("daily_briefing_data", payload, room=sid)
        await emit_to_frontend("settings", settings)

