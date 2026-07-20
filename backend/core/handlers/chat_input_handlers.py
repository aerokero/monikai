import asyncio
import base64
import re
import time


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
    @sio.event
    async def user_input(sid, data):
        text = data.get('text')
        attachments = data.get('attachments') or []
        print(f"[SERVER DEBUG] User input received: '{text}'")

        audio_loop = get_audio_loop()
        if not audio_loop:
            print("[SERVER DEBUG] [Error] Audio loop is None. Cannot send text.")
            return

        if not audio_loop.session:
            print("[SERVER DEBUG] [Error] Session is None. Cannot send text.")
            return

        async def _send_with_reconnect_retry(input_payload, end_of_turn=False):
            try:
                await audio_loop.session.send(input=input_payload, end_of_turn=end_of_turn)
                return True
            except Exception as e:
                msg = str(e or "")
                if "1008" not in msg and "Requested entity was not found" not in msg:
                    raise
                try:
                    await audio_loop.wait_until_ready(timeout_sec=6.0)
                    if audio_loop.session:
                        await audio_loop.session.send(input=input_payload, end_of_turn=end_of_turn)
                        return True
                except Exception:
                    pass
                raise

        if text or attachments:
            if text:
                print(f"[SERVER DEBUG] Sending message to model: '{text}'")
            if attachments:
                print(f"[SERVER DEBUG] Received {len(attachments)} attachment(s).")

            asks_name = False
            if text:
                try:
                    t_norm = str(text).strip().lower()
                    asks_name = bool(re.search(r"\b(jak\s+mam\s+na\s+imię|jak\s+mam\s+na\s+imie|pamiętasz\s+jak\s+mam\s+na\s+imię|pamietasz\s+jak\s+mam\s+na\s+imie|what\s+is\s+my\s+name|remember\s+my\s+name)\b", t_norm))
                except Exception:
                    asks_name = False

            sent_visual = False
            sent_screen_ocr = False
            max_visual_age_sec = 2.0
            latest_age = None
            study_payload = None
            study_meta = {}

            try:
                audio_loop_mark_user_activity(audio_loop, text)
            except Exception:
                pass

            try:
                if text:
                    buf = (get_vn_user_buf() + " " + text).strip()[-400:]
                    set_vn_user_buf(buf)
                    set_vn_user_last_ts(time.time())
                    scene_task = get_vn_scene_task()
                    if scene_task is None or scene_task.done():
                        set_vn_scene_task(create_debounced_vn_scene_task())
            except Exception:
                pass

            if audio_loop and getattr(audio_loop, "session_manager", None):
                audio_loop.session_manager.log_chat("User", text)

            if audio_loop and getattr(audio_loop, "video_mode", None) == "screen":
                try:
                    await audio_loop.refresh_latest_frame(min_age_sec=0.05)
                except Exception:
                    pass

            if audio_loop and getattr(audio_loop, "video_mode", None) == "camera":
                try:
                    if getattr(audio_loop, "camera_source", "frontend") == "frontend":
                        await sio.emit("request_camera_frame", to=sid)
                        await asyncio.sleep(0.08)
                except Exception:
                    pass

            if attachments:
                try:
                    summary = []
                    for a in attachments:
                        name = a.get("name") or "unnamed"
                        mime_type = a.get("mime_type") or "application/octet-stream"
                        size = a.get("size")
                        size_str = f"{size} bytes" if isinstance(size, int) else "unknown size"
                        summary.append(f"{name} ({mime_type}, {size_str})")
                    await audio_loop.session.send(
                        input=("System Notification: User attached files: " + "; ".join(summary)),
                        end_of_turn=False,
                    )
                except Exception as e:
                    print(f"[SERVER DEBUG] Failed to send attachment summary: {e}")

                for a in attachments:
                    try:
                        payload = {
                            "mime_type": a.get("mime_type") or "application/octet-stream",
                            "data": a.get("data"),
                        }
                        if payload["data"]:
                            await audio_loop.session.send(input=payload, end_of_turn=False)
                            if str(payload["mime_type"]).startswith("image/"):
                                sent_visual = True
                    except Exception as e:
                        print(f"[SERVER DEBUG] Failed to send attachment payload: {e}")

            study_payload, study_meta = study_reader.get_latest_image(max_age_sec=45.0)

            page_request = False
            private_web_task_request = False
            if text:
                norm_text = str(text).lower()
                if re.search(r"\bcan you see (this )?current page\??\b", norm_text):
                    page_request = True
                private_web_task_request = is_private_web_task_request(norm_text)

            if page_request:
                try:
                    reminder = (
                        'System Notification: The user is asking if you can see the current study page. '
                        'You must tell them: "Send me the current page", and explain you can only read it '
                        "after they send it via the chat button."
                    )
                    await audio_loop.session.send(input=reminder, end_of_turn=False)
                except Exception:
                    pass

            if private_web_task_request:
                try:
                    web_task_nudge = (
                        "System Notification: [Private Service Routing] The user asked for help with a private web service "
                        "(e.g., email inbox). Choose approach adaptively: if a relevant Skill is available and "
                        "eligible, you may use `run_openclaw_skill_command`; otherwise use `run_openclaw_agent` (or "
                        "`manage_agent_job` action=start for longer flows). For browser flows, guide step by step. "
                        "If login/2FA is required, ask the user to complete it manually in browser. "
                        "Never ask for or store passwords."
                    )
                    await audio_loop.session.send(input=web_task_nudge, end_of_turn=False)
                except Exception:
                    pass

            if not study_payload and audio_loop and getattr(audio_loop, "video_mode", None) == "screen":
                try:
                    await audio_loop.refresh_latest_frame(min_age_sec=0.5)
                except Exception:
                    pass

            if study_payload and not sent_visual:
                try:
                    page = study_meta.get("page")
                    page_label = study_meta.get("page_label")
                    folder = study_meta.get("folder")
                    file = study_meta.get("file")
                    label_note = f" (book page {page_label})" if page_label else ""
                    meta_msg = (
                        "System Notification: [Study] "
                        f"Use the attached study page image for the user's question. "
                        f"Current page: {page}{label_note} from {folder}/{file}. "
                        "Do not use prior knowledge about the textbook. "
                        "Do not guess; if the image is unreadable, say you cannot read it."
                    )
                    await audio_loop.session.send(input=meta_msg, end_of_turn=False)
                    await audio_loop.session.send(input=study_payload, end_of_turn=False)
                    sent_visual = True

                    ocr_text, ocr_meta = study_reader.get_latest_text(max_age_sec=45.0)
                    if ocr_text and ocr_meta:
                        if ocr_meta.get("page") == page and ocr_meta.get("file") == file:
                            ocr_msg = f"System Notification: [Study OCR] Text snippet for this page: {ocr_text}"
                            await audio_loop.session.send(input=ocr_msg, end_of_turn=False)

                    tiles, tiles_meta = study_reader.get_latest_tiles(max_age_sec=45.0)
                    if tiles and tiles_meta:
                        if tiles_meta.get("page") == page and tiles_meta.get("file") == file:
                            tiles_msg = (
                                "System Notification: [Study] Zoom tiles are attached for small text. "
                                "Use them to read precise content. Do not guess."
                            )
                            await audio_loop.session.send(input=tiles_msg, end_of_turn=False)
                            for payload in tiles:
                                await audio_loop.session.send(input=payload, end_of_turn=False)
                except Exception as e:
                    print(f"[SERVER DEBUG] Failed to send study page image: {e}")

            piggyback_payload = None
            if not sent_visual and audio_loop and getattr(audio_loop, "_latest_image_payload", None):
                if getattr(audio_loop, "_latest_image_ts", None):
                    latest_age = time.time() - audio_loop._latest_image_ts
                if latest_age is None or latest_age <= max_visual_age_sec:
                    print(f"[SERVER DEBUG] Piggybacking video frame with text input.")
                    piggyback_payload = audio_loop._latest_image_payload
                    sent_visual = True
                else:
                    print(f"[SERVER DEBUG] Skipping stale visual frame (age {latest_age:.2f}s).")

            if text:
                try:
                    sent_screen_ocr = await screen_ocr_runtime.maybe_send(text)
                except Exception:
                    sent_screen_ocr = False

            if not sent_visual and not sent_screen_ocr and audio_loop and getattr(audio_loop, "video_mode", None) in ("screen", "camera"):
                note = "System Notification: No visual frame was sent with this turn. If you did not receive an image, say you cannot see the user's screen/camera."
                if latest_age is not None:
                    note += f" Last visual frame age: {latest_age:.2f}s."
                try:
                    await audio_loop.session.send(input=note, end_of_turn=False)
                except Exception:
                    pass

            # Memory is not injected into ordinary turns.  Gemini can use the
            # memory_search / recall_conversation tools when the conversation
            # actually refers to something from the past.
            if text:
                try:
                    from backend.core.runtimes.v2_runtime import get as _v2_get

                    v2_runtime = _v2_get()
                    if v2_runtime is not None:
                        await v2_runtime.observe_turn()
                except Exception as exc:
                    print(f"[SERVER DEBUG] v2 turn observation failed: {exc}")

            if text and audio_loop and getattr(audio_loop, "memory_engine", None):
                try:
                    if asks_name and hasattr(audio_loop.memory_engine, "get_user_name"):
                        remembered_name = audio_loop.memory_engine.get_user_name()
                        if remembered_name:
                            hint = (
                                "System Notification: [Memory Recall] "
                                f"The user's name in memory is: {remembered_name}. "
                                "Answer directly and naturally. Do not say you are checking memory now."
                            )
                            await _send_with_reconnect_retry(hint, end_of_turn=False)
                except Exception:
                    pass

            # Myśliciel (ścieżka tekstowa): wygeneruj głębszą myśl i wstrzyknij
            # ją PRZED tekstem użytkownika, żeby model widział ją, zanim
            # odpowie. Sam gate'uje (flaga, potakiwania, odstęp); brak myśli
            # albo błąd = wysyłka idzie dalej bez zmian.
            if text:
                try:
                    thinker = getattr(audio_loop, "thinker", None)
                    if thinker is not None:
                        thought = await thinker.think_for_text(text)
                        if thought:
                            await _send_with_reconnect_retry(
                                f"(Internal Monologue) {thought}", end_of_turn=False
                            )
                except Exception as e:
                    print(f"[SERVER DEBUG] Thinker (text path) failed: {e}")

            if text:
                try:
                    if piggyback_payload and hasattr(audio_loop.session, "send_client_content"):
                        from google.genai import types as _genai_types
                        _raw = base64.b64decode(piggyback_payload["data"])
                        _mime = piggyback_payload.get("mime_type", "image/jpeg")
                        _content = _genai_types.Content(
                            role="user",
                            parts=[
                                _genai_types.Part(inline_data=_genai_types.Blob(data=_raw, mime_type=_mime)),
                                _genai_types.Part(text=text),
                            ],
                        )
                        await audio_loop.session.send_client_content(turns=_content, turn_complete=True)
                    else:
                        await _send_with_reconnect_retry(text, end_of_turn=True)
                    print(f"[SERVER DEBUG] Message sent to model successfully.")
                except Exception as e:
                    print(f"[SERVER DEBUG] Failed to send message to model: {e}")
                    await emit_to_frontend('status', {'msg': 'Connection lost. Reconnecting...'})
            else:
                try:
                    await _send_with_reconnect_retry(
                        "System Notification: User sent attachments without additional text.",
                        end_of_turn=True,
                    )
                    print(f"[SERVER DEBUG] Attachments-only message sent to model.")
                except Exception as e:
                    print(f"[SERVER DEBUG] Failed to send attachments-only message: {e}")
                    await emit_to_frontend('status', {'msg': 'Connection lost. Reconnecting...'})
