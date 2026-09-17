from backend.core.routers.frontend_router import is_active_frontend_sid


def register_chat_input_handlers(
    sio,
    *,
    get_audio_loop,
    emit_to_frontend,
    audio_loop_mark_user_activity,
    get_vn_user_buf,
    set_vn_user_buf,
    set_vn_user_last_ts,
    get_vn_scene_task,
    set_vn_scene_task,
    create_debounced_vn_scene_task,
    is_private_web_task_request,
    study_reader,
    screen_ocr_runtime,
):
    """Register the desktop text bridge.

    Text and attachments use the same native Odysseus request as the Agent
    composer. Gemini Live is an audio/ASR transport only; this module must
    never send it user text or inline attachment bytes.
    """

    @sio.event
    async def conversation_probe_status(sid):
        audio_loop = get_audio_loop()
        gateway = getattr(audio_loop, "conversation_gateway", None) if audio_loop else None
        return {
            "running": bool(audio_loop),
            "ready": bool(audio_loop and gateway),
            "author": "odysseus" if gateway else None,
        }

    @sio.event
    async def conversation_probe_turn(sid, data):
        """Local diagnostic RPC for the native text/attachment route."""
        payload = data if isinstance(data, dict) else {}
        text = str(payload.get("text") or "").strip()
        attachment_ids = _native_attachment_ids(payload.get("attachments"))
        if not text and not attachment_ids:
            return {"ok": False, "error": "text or attachments are required"}
        if attachment_ids is None:
            return {"ok": False, "error": "attachments must contain native upload IDs"}

        audio_loop = get_audio_loop()
        if not audio_loop or not getattr(audio_loop, "conversation_gateway", None):
            return {"ok": False, "error": "Native Odysseus gateway is not configured"}
        try:
            timeout_sec = max(5.0, min(180.0, float(payload.get("timeout_sec") or 90.0)))
            response = await audio_loop.submit_native_turn(
                text,
                attachment_ids=attachment_ids,
                timeout_sec=timeout_sec,
            )
            trace = dict(getattr(audio_loop, "_last_programmatic_turn_trace", {}) or {})
            trace.update({"ok": True, "response": response})
            return trace
        except Exception as exc:
            return {"ok": False, "error": str(exc), "user": text}

    @sio.event
    async def user_input(sid, data):
        if not is_active_frontend_sid(sid):
            return

        payload = data if isinstance(data, dict) else {}
        text = str(payload.get("text") or "").strip()
        attachment_ids = _native_attachment_ids(payload.get("attachments"))
        if attachment_ids is None:
            await sio.emit(
                "error",
                {"msg": "Załączniki muszą być przesłane przez natywny endpoint upload."},
                room=sid,
            )
            return
        if not text and not attachment_ids:
            return

        audio_loop = get_audio_loop()
        if not audio_loop:
            await sio.emit("error", {"msg": "Monika nie jest jeszcze gotowa."}, room=sid)
            return
        if not getattr(audio_loop, "conversation_gateway", None):
            await sio.emit(
                "error",
                {"msg": "Natywny gateway Odysseusa nie jest skonfigurowany."},
                room=sid,
            )
            return

        # Keep the VN activity signal independent from the conversation author.
        try:
            audio_loop_mark_user_activity(audio_loop, text or "[attachments]")
        except Exception:
            pass
        try:
            if text:
                buf = (get_vn_user_buf() + " " + text).strip()[-400:]
                set_vn_user_buf(buf)
                import time
                set_vn_user_last_ts(time.time())
                scene_task = get_vn_scene_task()
                if scene_task is None or scene_task.done():
                    set_vn_scene_task(create_debounced_vn_scene_task())
        except Exception:
            pass

        try:
            await audio_loop.submit_native_turn(
                text,
                attachment_ids=attachment_ids,
                timeout_sec=120.0,
            )
        except Exception as exc:
            print(f"[SERVER DEBUG] Native Odysseus turn failed: {exc}")
            await sio.emit("error", {"msg": "Natywna tura Odysseusa nie powiodła się."}, room=sid)


def _native_attachment_ids(value):
    """Normalize socket attachment references and reject inline bytes."""
    if value is None:
        return []
    if not isinstance(value, list):
        return None

    output = []
    for item in value:
        if isinstance(item, str):
            attachment_id = item.strip()
        elif isinstance(item, dict):
            attachment_id = str(item.get("id") or item.get("attachment_id") or "").strip()
            if item.get("data") and not attachment_id:
                return None
        else:
            return None
        if not attachment_id:
            return None
        output.append(attachment_id)
    return output
