from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
from datetime import datetime

from backend.services.personality_notifications import to_frontend_personality_event
from backend.core.routers.frontend_router import get_active_frontend_sid


def register_audio_lifecycle_handlers(
    sio,
    *,
    get_settings,
    get_audio_loop,
    set_audio_loop,
    get_loop_task,
    set_loop_task,
    get_authenticator,
    set_authenticator,
    set_active_frontend_sid,
    clear_active_frontend_sid,
    schedule_emit_to_frontend,
    emit_to_frontend,
    serialize_reminders,
    screen_ocr_runtime,
    vn_scene_runtime,
    data_dir,
    monikai_module,
    get_calendar_manager,
    get_reminder_manager,
    get_spotify_manager,
    get_personality_system,
    get_hue_agent,
    get_home_assistant_agent,
    get_minecraft_bot_manager,
    shutdown_and_exit,
):
    last_start_params = {"sid": None, "data": None}

    async def _start_audio_impl(sid, data=None):
        nonlocal last_start_params
        audio_loop = get_audio_loop()
        last_start_params = {"sid": sid, "data": data}

        print("[SYSTEM NOTIFICATION] Starting Audio Loop...")

        device_index = None
        device_name = None
        if data:
            if "device_index" in data:
                device_index = data["device_index"]
            if "device_name" in data:
                device_name = data["device_name"]

        print(f"[SYSTEM NOTIFICATION] Using input device: Name='{device_name}', Index={device_index}")

        loop_task = get_loop_task()
        if loop_task and not loop_task.done():
            if get_active_frontend_sid() != sid:
                await sio.emit("error", {"msg": "Another desktop client owns the active voice session"}, room=sid)
                return
            print("[SYSTEM NOTIFICATION] Audio loop already running. Re-connecting client to session.")
            await sio.emit("status", {"msg": "MonikAI Already Running"}, room=sid)
            return

        if audio_loop:
            if loop_task and (loop_task.done() or loop_task.cancelled()):
                print("[SYSTEM NOTIFICATION] Audio loop task appeared finished/cancelled. Clearing and restarting...")
                set_audio_loop(None)
                set_loop_task(None)
            else:
                if get_active_frontend_sid() != sid:
                    await sio.emit("error", {"msg": "Another desktop client owns the active voice session"}, room=sid)
                    return
                print("[SYSTEM NOTIFICATION] Audio loop already running. Re-connecting client to session.")
                await sio.emit("status", {"msg": "MonikAI Already Running"}, room=sid)
                return

        def on_audio_data(data_bytes):
            # Keep PCM binary on the wire. JSON-encoding every sample adds
            # substantial CPU, bandwidth and latency to remote clients.
            schedule_emit_to_frontend("audio_data", {"data": data_bytes})

        def on_web_data(data):
            log_text = str((data or {}).get("log") or "")
            job_id = (data or {}).get("job_id")
            job_status = (data or {}).get("job_status")
            if log_text:
                compact = " ".join(log_text.split())
                if len(compact) > 320:
                    compact = compact[:317] + "..."
                print(f"[WEB AGENT] job={job_id or '-'} status={job_status or '-'} log={compact}")
            else:
                print(f"Sending Browser data to frontend: {len(log_text)} chars logs")
            schedule_emit_to_frontend("browser_frame", data)

        def on_transcription(data):
            # Conversation content belongs to the desktop client that owns
            # the active Live session, not to every connected frontend.
            asyncio.create_task(sio.emit("transcription", data, room=sid))

            try:
                sender = (data or {}).get("sender", "")
                text = (data or {}).get("text") or ""
                if sender in ("Ty", "User") and text:
                    norm_text = str(text).lower()
                    if re.search(r"\bcan you see (this )?current page\??\b", norm_text):
                        schedule_emit_to_frontend("study_request_share", {"reason": "current_page"})

                        async def _send_reminder():
                            reminder = (
                                "System Notification: The user is asking if you can see the current study page. "
                                "You must tell them: \"Send me the current page\", and explain you can only read it "
                                "after they send it via the chat button."
                            )
                            try:
                                if hasattr(audio_loop, "send_system_message"):
                                    await audio_loop.send_system_message(reminder, end_of_turn=False)
                                else:
                                    await audio_loop.session.send(input=reminder, end_of_turn=False)
                            except Exception:
                                pass

                        asyncio.create_task(_send_reminder())
                    else:
                        if screen_ocr_runtime and hasattr(screen_ocr_runtime, "schedule_from_transcription"):
                            screen_ocr_runtime.schedule_from_transcription()
            except Exception:
                pass

            try:
                sender = (data or {}).get("sender", "")
                if sender in ("Ty", "User"):
                    vn_text = (data or {}).get("text") or ""
                    if vn_scene_runtime:
                        vn_scene_runtime.note_user_text(vn_text)
            except Exception:
                pass

        def on_tool_confirmation(data):
            tool_name = data.get("tool", "unknown")
            print(f"[SYSTEM NOTIFICATION] Requesting confirmation for tool: {tool_name}")
            schedule_emit_to_frontend("tool_confirmation_request", data)

        def on_session_update(session_id):
            print(f"[SYSTEM NOTIFICATION] Session updated to: {session_id}")
            schedule_emit_to_frontend("session_update", {"session": session_id})

        def on_session_prompt(payload):
            try:
                schedule_emit_to_frontend("session_prompt", payload)
            except Exception:
                pass

        def on_device_update(devices):
            print(f"[SYSTEM NOTIFICATION] Smart device list updated: {len(devices)} devices found.")
            schedule_emit_to_frontend("kasa_devices", devices)

        def on_notes_update(payload):
            try:
                print("[SYSTEM NOTIFICATION] Notes were updated.")
                schedule_emit_to_frontend("notes_data", payload)
            except Exception:
                pass

        def on_error(msg):
            print(f"[SYSTEM ERROR] {msg}")
            schedule_emit_to_frontend("error", {"msg": msg})

        def on_video_frame(payload):
            try:
                schedule_emit_to_frontend("vision_frame", payload)
            except Exception:
                pass

        def on_reminder_fired(payload):
            try:
                message = payload.get("message", "No message")
                print(f"[SYSTEM NOTIFICATION] Reminder fired: {message}")
                schedule_emit_to_frontend("reminder_fired", payload)
                schedule_emit_to_frontend("reminders_list", {"reminders": serialize_reminders()})
            except Exception as e:
                print(f"[SERVER] Failed to emit reminder_fired: {e}")

        def on_calendar_update(events):
            try:
                print(f"[SERVER] Emitting calendar_data with {len(events)} events.")
                schedule_emit_to_frontend("calendar_data", events)
            except Exception as e:
                print(f"[SERVER] Failed to emit calendar_data: {e}")

        def on_personality_update(data):
            try:
                schedule_emit_to_frontend("personality_status", data)
            except Exception as e:
                print(f"[SERVER] Failed to emit personality_status: {e}")

        def on_internal_thought(thought):
            print(f"[SYSTEM NOTIFICATION] Internal Thought: {thought}")
            schedule_emit_to_frontend("internal_thought", {"thought": thought})
            if bool(get_settings().get("show_internal_thoughts", False)):
                schedule_emit_to_frontend(
                    "transcription",
                    {"sender": "Monika (Thought)", "text": f"{thought}", "is_new": True},
                )

        def on_reminders_updated():
            try:
                schedule_emit_to_frontend("reminders_list", {"reminders": serialize_reminders()})
            except Exception as e:
                print(f"[SERVER] Failed to emit reminders_list update: {e}")

        def on_study_fields(payload):
            try:
                schedule_emit_to_frontend("study_fields", payload)
            except Exception as e:
                print(f"[SERVER] Failed to emit study_fields: {e}")

        def on_study_notes(payload):
            try:
                schedule_emit_to_frontend("study_notes", payload)
            except Exception as e:
                print(f"[SERVER] Failed to emit study_notes: {e}")

        def on_study_page(payload):
            try:
                schedule_emit_to_frontend("study_page", payload)
            except Exception as e:
                print(f"[SERVER] Failed to emit study_page: {e}")

        def on_personality_event(payload):
            try:
                raw = payload if isinstance(payload, dict) else {"type": "unknown", "raw": payload}
                event = to_frontend_personality_event(raw)
                schedule_emit_to_frontend("personality_event", event)
            except Exception as e:
                print(f"[SERVER] Failed to emit personality_event: {e}")

        try:
            video_mode = "none"
            if data and isinstance(data, dict) and data.get("video_mode"):
                video_mode = str(data.get("video_mode")).lower()
            else:
                video_mode = str(get_settings().get("video_mode", "none")).lower()

            audio_source = str(
                (data or {}).get("audio_source")
                or get_settings().get("audio_source", "backend")
            ).lower()
            play_audio_locally = bool(
                (data or {}).get("play_audio_locally", audio_source == "backend")
            )
            screen_source = str(
                (data or {}).get("screen_source")
                or get_settings().get("screen_source", "backend")
            ).lower()

            print(f"[SYSTEM NOTIFICATION] Initializing AudioLoop with device_index={device_index}, video_mode={video_mode}")
            audio_loop = monikai_module.AudioLoop(
                video_mode=video_mode,
                on_audio_data=on_audio_data,
                on_video_frame=on_video_frame,
                on_web_data=on_web_data,
                on_transcription=on_transcription,
                on_tool_confirmation=on_tool_confirmation,
                on_session_update=on_session_update,
                on_session_prompt=on_session_prompt,
                on_device_update=on_device_update,
                on_notes_update=on_notes_update,
                on_error=on_error,
                on_reminder_fired=on_reminder_fired,
                on_reminders_updated=on_reminders_updated,
                on_calendar_update=on_calendar_update,
                on_personality_update=on_personality_update,
                on_personality_event=on_personality_event,
                on_internal_thought=on_internal_thought,
                on_study_fields=on_study_fields,
                on_study_notes=on_study_notes,
                on_study_page=on_study_page,
                on_program_shutdown=lambda reason: shutdown_and_exit(f"[SERVER] {reason}"),
                input_device_index=device_index,
                input_device_name=device_name,
                calendar_manager=get_calendar_manager(),
                reminder_manager=get_reminder_manager(),
                spotify_manager=get_spotify_manager(),
                personality=get_personality_system(),
                audio_source=audio_source,
                screen_source=screen_source,
                play_audio_locally=play_audio_locally,
            )
            print("[SYSTEM NOTIFICATION] AudioLoop initialized successfully.")

            set_active_frontend_sid(sid)
            set_audio_loop(audio_loop)

            audio_loop.hue_agent = get_hue_agent()
            audio_loop.home_assistant_agent = get_home_assistant_agent()
            audio_loop.minecraft_bot_manager = get_minecraft_bot_manager()

            try:
                audio_loop.note_user_activity("start_audio")
            except Exception:
                pass

            audio_loop.update_permissions(get_settings()["tool_permissions"])

            if data and data.get("muted", False):
                print("[SYSTEM NOTIFICATION] Starting with Audio Paused")
                audio_loop.set_paused(True)

            print("[SYSTEM NOTIFICATION] Creating asyncio task for AudioLoop.run()")
            loop_task = asyncio.create_task(audio_loop.run())
            set_loop_task(loop_task)

            def handle_loop_exit(task):
                try:
                    task.result()
                except asyncio.CancelledError:
                    print("[SYSTEM NOTIFICATION] Audio Loop Cancelled")
                except Exception as e:
                    print(f"[SYSTEM ERROR] Audio Loop Crashed: {e}. Attempting restart...")
                    schedule_emit_to_frontend("status", {"msg": "Connection lost. Reconnecting..."})

                    async def restart_session():
                        await asyncio.sleep(2)
                        if last_start_params.get("sid"):
                            print("[SERVER] Triggering auto-restart...")
                            await _start_audio_impl(last_start_params["sid"], last_start_params.get("data"))

                    asyncio.create_task(restart_session())

            loop_task.add_done_callback(handle_loop_exit)
            print("[SYSTEM NOTIFICATION] MonikAI Started")
            await sio.emit("status", {"msg": "MonikAI Started"}, room=sid)
        except Exception as e:
            print(f"[SYSTEM ERROR] CRITICAL ERROR STARTING MonikAI: {e}")
            import traceback

            traceback.print_exc()
            await sio.emit("error", {"msg": f"Failed to start: {str(e)}"}, room=sid)
            set_audio_loop(None)

    @sio.event
    async def connect(sid, environ, auth=None):
        expected_token = str(os.getenv("MONIKAI_SOCKET_TOKEN") or "").strip()
        if expected_token:
            supplied_token = ""
            if isinstance(auth, dict) and auth.get("token"):
                supplied_token = str(auth.get("token")).strip()
            if not supplied_token and environ:
                supplied_token = str(environ.get("HTTP_X_MONIKAI_TOKEN") or "").strip()
                if not supplied_token:
                    auth_header = str(environ.get("HTTP_AUTHORIZATION") or "").strip()
                    if auth_header.lower().startswith("bearer "):
                        supplied_token = auth_header[7:].strip()
                if not supplied_token:
                    query_string = str(environ.get("QUERY_STRING") or "")
                    for param in query_string.split("&"):
                        if param.startswith("token="):
                            supplied_token = param.split("=", 1)[1].strip()
                            break

            if not supplied_token or not hmac.compare_digest(supplied_token, expected_token):
                print(f"[SECURITY] Rejected unauthenticated Socket.IO client: {sid}")
                return False
        print(f"[SYSTEM NOTIFICATION] Client connected: {sid}")
        await sio.emit("status", {"msg": "Connected to MonikAI Backend"}, room=sid)
        await sio.emit("auth_status", {"authenticated": True}, room=sid)

    @sio.event
    async def disconnect(sid):
        was_active = get_active_frontend_sid() == sid
        clear_active_frontend_sid(sid)
        if was_active:
            audio_loop = get_audio_loop()
            if audio_loop:
                audio_loop.stop()
            loop_task = get_loop_task()
            if loop_task and not loop_task.done():
                loop_task.cancel()
                try:
                    await loop_task
                except BaseException:
                    pass
            set_audio_loop(None)
            set_loop_task(None)
            print("[SYSTEM NOTIFICATION] Active desktop session stopped after client disconnect.")
        print(f"Client disconnected: {sid}")

        pass

    @sio.event
    async def start_audio(sid, data=None):
        await _start_audio_impl(sid, data)

    @sio.event
    async def stop_audio(sid):
        audio_loop = get_audio_loop()
        if audio_loop:
            audio_loop.stop()
            print("[SYSTEM NOTIFICATION] Stopping Audio Loop")

        loop_task = get_loop_task()
        if loop_task and not loop_task.done():
            try:
                loop_task.cancel()
                await loop_task
            except Exception:
                pass
            set_loop_task(None)

        set_audio_loop(None)
        print("[SYSTEM NOTIFICATION] MonikAI Stopped")
        await sio.emit("status", {"msg": "MonikAI Stopped"}, room=sid)

    @sio.event
    async def pause_audio(sid):
        audio_loop = get_audio_loop()
        if audio_loop:
            audio_loop.set_paused(True)
            print("[SYSTEM NOTIFICATION] Audio Paused")
            await sio.emit("status", {"msg": "Audio Paused"}, room=sid)

    @sio.event
    async def resume_audio(sid):
        audio_loop = get_audio_loop()
        if audio_loop:
            audio_loop.set_paused(False)
            print("[SYSTEM NOTIFICATION] Audio Resumed")
            await sio.emit("status", {"msg": "Audio Resumed"}, room=sid)
