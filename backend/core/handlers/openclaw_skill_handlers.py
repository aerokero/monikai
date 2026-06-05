import base64


def register_openclaw_skill_handlers(sio, *, get_audio_loop):
    def _skills_manager():
        audio_loop = get_audio_loop()
        if not audio_loop:
            return None
        return getattr(audio_loop, "skills_manager", None) or getattr(audio_loop, "openclaw_skills", None)

    async def _emit_skills_payload(sid, payload):
        await sio.emit("skills", payload, room=sid)
        await sio.emit("openclaw_skills", payload, room=sid)

    async def _emit_skill_install_result(sid, payload):
        await sio.emit("skill_install_result", payload, room=sid)
        await sio.emit("openclaw_skill_install_result", payload, room=sid)

    async def _emit_skill_uninstall_result(sid, payload):
        await sio.emit("skill_uninstall_result", payload, room=sid)
        await sio.emit("openclaw_skill_uninstall_result", payload, room=sid)

    @sio.event
    async def prompt_web_agent(sid, data):
        prompt = data.get("prompt")
        print(f"Received web agent prompt: '{prompt}'")

        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "web_agent", None):
                await sio.emit("error", {"msg": "Monika OpenClaw fork is not available"}, room=sid)
                return

            await sio.emit("status", {"msg": "Monika OpenClaw fork running..."}, room=sid)

            await audio_loop.handle_openclaw_agent_request(prompt)

            await sio.emit("status", {"msg": "Monika OpenClaw fork finished"}, room=sid)

        except Exception as e:
            print(f"Error running Monika OpenClaw fork: {e}")
            await sio.emit("error", {"msg": f"Monika OpenClaw fork error: {str(e)}"}, room=sid)

    @sio.event
    async def control_agent_job(sid, data):
        action = str((data or {}).get("action") or "").strip().lower()
        job_id = (data or {}).get("job_id")
        audio_loop = get_audio_loop()
        if not audio_loop:
            await sio.emit("error", {"msg": "Agent loop not active"}, room=sid)
            return

        try:
            if action == "start":
                prompt = str((data or {}).get("prompt") or "").strip()
                if not prompt:
                    await sio.emit("agent_job_status", {"ok": False, "error": "prompt required for action=start"}, room=sid)
                    return
                provider = str((data or {}).get("provider") or "openclaw").strip().lower() or "openclaw"
                agent = (data or {}).get("agent")
                thinking = (data or {}).get("thinking")
                timeout_sec = (data or {}).get("timeout_sec")
                new_job_id = audio_loop.start_agent_job(
                    prompt=prompt,
                    provider=provider,
                    agent=agent,
                    thinking=thinking,
                    timeout_sec=timeout_sec,
                )
                await sio.emit("agent_job_status", {"ok": True, "job_id": new_job_id, "status": "queued"}, room=sid)
            elif action == "status":
                status_obj = audio_loop.get_agent_job_status(job_id)
                await sio.emit("agent_job_status", status_obj, room=sid)
            elif action == "list":
                status_obj = audio_loop.get_agent_job_status(None)
                await sio.emit("agent_job_status", status_obj, room=sid)
            elif action == "stop":
                result = await audio_loop.stop_agent_job(job_id)
                await sio.emit("agent_job_status", result, room=sid)
            elif action == "resume":
                result = await audio_loop.resume_agent_job(job_id)
                await sio.emit("agent_job_status", result, room=sid)
            else:
                await sio.emit("agent_job_status", {"ok": False, "error": "unknown action"}, room=sid)
        except Exception as e:
            await sio.emit("agent_job_status", {"ok": False, "error": str(e)}, room=sid)

    async def _list_skills_impl(sid, data=None):
        include_ineligible = bool((data or {}).get("include_ineligible", False))
        include_disabled = bool((data or {}).get("include_disabled", False))
        manager = _skills_manager()
        if not manager:
            payload = {
                "count": 0,
                "skills": [],
                "error": "Skills manager unavailable",
            }
        else:
            skills = manager.list_skills(
                include_ineligible=include_ineligible,
                include_disabled=include_disabled,
            )
            payload = {"count": len(skills), "skills": skills}
        await _emit_skills_payload(sid, payload)

    @sio.event
    async def list_openclaw_skills(sid, data=None):
        await _list_skills_impl(sid, data)

    @sio.on("list_skills")
    async def list_skills(sid, data=None):
        await _list_skills_impl(sid, data)

    async def _refresh_skills_impl(sid, data=None):
        include_ineligible = bool((data or {}).get("include_ineligible", True))
        include_disabled = bool((data or {}).get("include_disabled", True))
        manager = _skills_manager()
        if not manager:
            payload = {
                "count": 0,
                "skills": [],
                "error": "Skills manager unavailable",
            }
        else:
            _ = manager.refresh()
            skills = manager.list_skills(
                include_ineligible=include_ineligible,
                include_disabled=include_disabled,
            )
            payload = {"count": len(skills), "skills": skills}
        await _emit_skills_payload(sid, payload)

    @sio.event
    async def refresh_openclaw_skills(sid, data=None):
        await _refresh_skills_impl(sid, data)

    @sio.on("refresh_skills")
    async def refresh_skills(sid, data=None):
        await _refresh_skills_impl(sid, data)

    async def _install_skill_zip_impl(sid, data=None):
        filename = str((data or {}).get("filename") or "skill.zip").strip() or "skill.zip"
        zip_b64 = (data or {}).get("zip_b64") or ""
        replace = bool((data or {}).get("replace", True))

        manager = _skills_manager()
        if not manager:
            await _emit_skill_install_result(
                sid,
                {
                    "ok": False,
                    "error": "Skills manager unavailable",
                },
            )
            return

        if not zip_b64:
            await _emit_skill_install_result(
                sid,
                {
                    "ok": False,
                    "error": "Missing zip_b64 payload",
                },
            )
            return

        try:
            raw_zip = base64.b64decode(str(zip_b64), validate=False)
        except Exception as e:
            await _emit_skill_install_result(
                sid,
                {
                    "ok": False,
                    "error": f"Invalid base64 ZIP payload: {e}",
                },
            )
            return

        try:
            result = manager.install_from_zip_bytes(
                raw_zip,
                filename=filename,
                replace=replace,
            )
            skills = manager.list_skills(
                include_ineligible=True,
                include_disabled=True,
            )
            await _emit_skill_install_result(
                sid,
                {
                    "ok": True,
                    "result": result,
                },
            )
            await _emit_skills_payload(sid, {"count": len(skills), "skills": skills})
        except Exception as e:
            await _emit_skill_install_result(
                sid,
                {
                    "ok": False,
                    "error": str(e),
                },
            )

    @sio.event
    async def install_openclaw_skill_zip(sid, data=None):
        await _install_skill_zip_impl(sid, data)

    @sio.on("install_skill_zip")
    async def install_skill_zip(sid, data=None):
        await _install_skill_zip_impl(sid, data)

    async def _install_skill_source_impl(sid, data=None):
        source = str((data or {}).get("source") or "").strip()
        raw_skill_name = (data or {}).get("skill_name")
        raw_skill_names = (data or {}).get("skill_names")
        agent = str((data or {}).get("agent") or "codex").strip() or "codex"
        global_scope = bool((data or {}).get("global_scope", False))
        copy_files = bool((data or {}).get("copy_files", True))

        manager = _skills_manager()
        if not manager:
            await _emit_skill_install_result(
                sid,
                {
                    "ok": False,
                    "error": "Skills manager unavailable",
                },
            )
            return

        if not source:
            await _emit_skill_install_result(
                sid,
                {
                    "ok": False,
                    "error": "source is required",
                },
            )
            return

        skill_names = []
        if isinstance(raw_skill_names, list):
            skill_names.extend(str(item or "").strip() for item in raw_skill_names)
        elif isinstance(raw_skill_names, str) and raw_skill_names.strip():
            skill_names.extend(part.strip() for part in raw_skill_names.split(","))
        if raw_skill_name:
            skill_names.append(str(raw_skill_name).strip())
        skill_names = [name for name in skill_names if name]

        try:
            result = manager.install_from_source(
                source,
                skill_names=skill_names,
                agent=agent,
                global_scope=global_scope,
                copy_files=copy_files,
                yes=True,
            )
            skills = manager.list_skills(
                include_ineligible=True,
                include_disabled=True,
            )
            await _emit_skill_install_result(
                sid,
                {
                    "ok": True,
                    "result": result,
                },
            )
            await _emit_skills_payload(sid, {"count": len(skills), "skills": skills})
        except Exception as e:
            await _emit_skill_install_result(
                sid,
                {
                    "ok": False,
                    "error": str(e),
                },
            )

    @sio.event
    async def install_openclaw_skill_source(sid, data=None):
        await _install_skill_source_impl(sid, data)

    @sio.on("install_skill_source")
    async def install_skill_source(sid, data=None):
        await _install_skill_source_impl(sid, data)

    async def _uninstall_skill_impl(sid, data=None):
        name = str((data or {}).get("name") or "").strip()
        if not name:
            await _emit_skill_uninstall_result(
                sid,
                {
                    "ok": False,
                    "error": "name is required",
                },
            )
            return

        manager = _skills_manager()
        if not manager:
            await _emit_skill_uninstall_result(
                sid,
                {
                    "ok": False,
                    "error": "Skills manager unavailable",
                },
            )
            return

        try:
            result = manager.uninstall_skill(name)
            skills = manager.list_skills(
                include_ineligible=True,
                include_disabled=True,
            )
            await _emit_skill_uninstall_result(
                sid,
                {
                    "ok": True,
                    "result": result,
                },
            )
            await _emit_skills_payload(sid, {"count": len(skills), "skills": skills})
        except Exception as e:
            await _emit_skill_uninstall_result(
                sid,
                {
                    "ok": False,
                    "error": str(e),
                },
            )

    @sio.event
    async def uninstall_openclaw_skill(sid, data=None):
        await _uninstall_skill_impl(sid, data)

    @sio.on("uninstall_skill")
    async def uninstall_skill(sid, data=None):
        await _uninstall_skill_impl(sid, data)
