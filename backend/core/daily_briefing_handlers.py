def register_daily_briefing_handlers(
    sio,
    *,
    runtime,
    save_settings,
    emit_to_frontend,
    settings,
    default_sections,
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

    @sio.event
    async def accept_daily_briefing_proposal(sid, data=None):
        req = data or {}
        proposal = req.get("proposal") or {}
        from_section = str(proposal.get("from_section") or "").strip().lower()
        to_section = str(proposal.get("to_section") or "").strip().lower()

        if not from_section or not to_section or to_section not in default_sections:
            await sio.emit("error", {"msg": "Invalid daily briefing proposal."}, room=sid)
            return

        profile = runtime.get_profile()
        pinned = [s for s in profile.get("pinned_sections", []) if s in default_sections]
        preferred = [s for s in profile.get("preferred_sections", []) if s in default_sections]

        if from_section in pinned:
            pinned = [s for s in pinned if s != from_section]
        if to_section not in pinned:
            pinned.append(to_section)
        if to_section not in preferred:
            preferred.append(to_section)

        profile["pinned_sections"] = pinned[:3]
        profile["preferred_sections"] = preferred[:4]
        runtime.set_profile(profile)
        save_settings()

        runtime.invalidate_cache()
        payload = await runtime.build_payload(language=req.get("language", "pl"), force=True)
        await sio.emit("daily_briefing_data", payload, room=sid)
        await emit_to_frontend("settings", settings)

    @sio.event
    async def reject_daily_briefing_proposal(sid, data=None):
        req = data or {}
        proposal = req.get("proposal") or {}
        from_section = str(proposal.get("from_section") or "").strip().lower()
        to_section = str(proposal.get("to_section") or "").strip().lower()

        profile = runtime.get_profile()
        cooldown_hours = int((profile.get("proposal_policy") or {}).get("cooldown_hours", 12))
        runtime.reject_proposal(from_section, to_section, cooldown_hours)

        runtime.invalidate_cache()
        payload = await runtime.build_payload(language=req.get("language", "pl"), force=True)
        await sio.emit("daily_briefing_data", payload, room=sid)
