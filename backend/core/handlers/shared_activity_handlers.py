from __future__ import annotations


def register_shared_activity_handlers(
    sio,
    *,
    runtime,
    get_audio_loop,
    screen_ocr_runtime=None,
):
    async def _emit_state(room=None):
        payload = runtime.snapshot()
        await sio.emit("shared_activity_state", payload, room=room)
        if payload.get("active") and payload.get("scene"):
            scene = payload["scene"]
            await sio.emit(
                "vn_scene",
                {
                    "scene": scene.get("bg"),
                    "reason": "shared_activity",
                    "ttl_ms": 300000,
                    "state": scene,
                },
                room=room,
            )
        return payload

    async def _send_system_notice(message: str) -> None:
        audio_loop = get_audio_loop()
        if not audio_loop or not getattr(audio_loop, "session", None):
            return
        try:
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(message, end_of_turn=False)
            else:
                await audio_loop.session.send(input=message, end_of_turn=False)
        except Exception:
            pass

    @sio.event
    async def shared_activity_start(sid, data=None):
        data = data or {}
        try:
            session = await runtime.start(
                str(data.get("kind") or "other").strip().lower(),
                title=data.get("title"),
                context=data.get("context") or "",
            )
        except ValueError as exc:
            await sio.emit("error", {"msg": str(exc)}, room=sid)
            return

        if screen_ocr_runtime is not None:
            screen_ocr_runtime.start_activity_loop()

        payload = await _emit_state(room=sid)
        await _send_system_notice(
            "System Notification: [Shared Activity] "
            f"Started {session.kind}"
            f"{' - ' + session.title if session.title else ''}.\n"
            f"{session.monika_context()}"
        )
        await sio.emit("status", {"msg": "Shared activity started", "activity": payload}, room=sid)

    @sio.event
    async def shared_activity_context(sid, data=None):
        data = data or {}
        changed = runtime.update_context(data.get("context") or "")
        payload = await _emit_state(room=sid)
        if changed:
            await _send_system_notice(
                "System Notification: [Shared Activity] Context updated.\n"
                f"{runtime.monika_context()}"
            )
        await sio.emit("status", {"msg": "Shared activity context updated", "activity": payload}, room=sid)

    @sio.event
    async def shared_activity_status(sid, data=None):
        await _emit_state(room=sid)

    @sio.event
    async def shared_activity_end(sid, data=None):
        data = data or {}
        result = await runtime.end(notes=data.get("notes") or "")
        if screen_ocr_runtime is not None:
            screen_ocr_runtime.stop_activity_loop()

        payload = await _emit_state(room=sid)
        if result is not None:
            await _send_system_notice(
                "System Notification: [Shared Activity] Activity ended and was stored as a memory. "
                "Acknowledge it naturally if relevant."
            )
        await sio.emit(
            "status",
            {
                "msg": "Shared activity ended",
                "activity": payload,
                "memory_id": getattr(result, "id", None),
            },
            room=sid,
        )
