import asyncio
import base64


def register_study_socket_handlers(
    sio,
    *,
    get_audio_loop,
    study_reader,
    safe_study_path,
    ocr_image_bytes_fn,
):
    @sio.event
    async def study_select(sid, data):
        try:
            audio_loop = get_audio_loop()
            folder = (data or {}).get("folder") or ""
            file = (data or {}).get("file") or ""
            rel_path = (data or {}).get("path") or ""
            if not rel_path:
                return

            safe_path = safe_study_path(rel_path)
            if not safe_path.exists():
                return

            answer_keys = []
            try:
                for f in safe_path.parent.glob("*.pdf"):
                    if "answer key" in f.name.lower():
                        answer_keys.append(f)
            except Exception:
                answer_keys = []

            if audio_loop and getattr(audio_loop, "session", None):
                ak_list = ", ".join([str(p) for p in answer_keys]) if answer_keys else "(none found)"
                msg = (
                    "System Notification: [Study] "
                    f"User opened: {folder}/{file}. "
                    f"Answer key files (for your use only): {ak_list}. "
                    "Do not reveal the answer key unless the user explicitly asks. "
                    "You can create answer fields with the study_set_fields tool and change pages with study_set_page. "
                    "When asked about page contents, rely on the provided page text snippet and/or attached page image; if none is available, say you cannot see that page."
                )
                if hasattr(audio_loop, "send_system_message"):
                    await audio_loop.send_system_message(msg, end_of_turn=False)
                else:
                    await audio_loop.session.send(input=msg, end_of_turn=False)
        except Exception as e:
            await sio.emit("error", {"msg": f"Study select failed: {e}"}, room=sid)

    @sio.event
    async def study_answers_submit(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "session", None):
                return
            folder = (data or {}).get("folder") or ""
            file = (data or {}).get("file") or ""
            fields = (data or {}).get("fields") or {}
            notes = (data or {}).get("notes") or ""
            lines = [f"Study answers for: {folder}/{file}"]
            if isinstance(fields, dict) and fields:
                for k, v in fields.items():
                    if v is None or str(v).strip() == "":
                        continue
                    lines.append(f"- {k}: {v}")
            if notes:
                lines.append("")
                lines.append(f"Notes: {notes}")
            msg = "System Notification: [Study] " + "\n".join(lines)
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
        except Exception as e:
            await sio.emit("error", {"msg": f"Study submit failed: {e}"}, room=sid)

    @sio.event
    async def study_page_user(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "session", None):
                return
            folder = (data or {}).get("folder") or ""
            file = (data or {}).get("file") or ""
            page = (data or {}).get("page")
            page_label = (data or {}).get("page_label") or ""
            text = (data or {}).get("text") or ""
            if not page:
                return
            print(f"[SERVER DEBUG] [Study] Page update: {folder}/{file} page={page} label={page_label} text_len={len(text or '')}")
            snippet = ""
            if text:
                cleaned = " ".join(str(text).split())
                snippet = cleaned[:1200] + ("..." if len(cleaned) > 1200 else "")
            study_reader.update_page_text(
                text=snippet or "",
                meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
            )
            label_note = f" (book page {page_label})" if page_label else ""
            msg = f"System Notification: [Study] User is viewing page {page} of {folder}/{file}{label_note}."
            if snippet:
                msg += f" Page text snippet: {snippet}"
            else:
                msg += " Page text snippet: (unavailable)"
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
        except Exception as e:
            await sio.emit("error", {"msg": f"Study page update failed: {e}"}, room=sid)

    @sio.event
    async def study_page_image(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "session", None):
                return
            folder = (data or {}).get("folder") or ""
            file = (data or {}).get("file") or ""
            page = (data or {}).get("page")
            page_label = (data or {}).get("page_label") or ""
            mime_type = (data or {}).get("mime_type") or "image/jpeg"
            b64 = (data or {}).get("data") or ""
            if not page or not b64:
                return
            payload = {"mime_type": mime_type, "data": b64}
            study_reader.update_page_image(
                payload=payload,
                meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
            )
            print(f"[SERVER DEBUG] [Study] Page image received: {folder}/{file} page={page} label={page_label} mime={mime_type} bytes={len(b64)}")
            label_note = f" (book page {page_label})" if page_label else ""
            msg = (
                f"System Notification: [Study] Image of page {page} from {folder}/{file}{label_note}. "
                "Use this image to answer questions about this page only. "
                "Do not use prior knowledge. Do not guess if unreadable."
            )
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
            await audio_loop.session.send(input=payload, end_of_turn=False)

            try:
                last_text, last_meta = study_reader.get_latest_text(max_age_sec=20.0)
                if last_meta.get("page") == page and last_meta.get("file") == file and last_text:
                    return
            except Exception:
                pass

            async def _run_ocr():
                try:
                    loop_audio = get_audio_loop()
                    if not loop_audio or not getattr(loop_audio, "session", None):
                        return
                    raw = base64.b64decode(b64)
                    text, err = await asyncio.to_thread(ocr_image_bytes_fn, raw)
                    if not text:
                        if err:
                            print(f"[SERVER DEBUG] [Study OCR] Unavailable: {err}")
                        return
                    cleaned = " ".join(str(text).split())
                    snippet = cleaned[:2000] + ("..." if len(cleaned) > 2000 else "")
                    study_reader.update_page_text(
                        text=snippet,
                        meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
                    )
                    ocr_msg = f"System Notification: [Study OCR] Extracted text snippet: {snippet}"
                    if hasattr(loop_audio, "send_system_message"):
                        await loop_audio.send_system_message(ocr_msg, end_of_turn=False)
                    else:
                        await loop_audio.session.send(input=ocr_msg, end_of_turn=False)
                except Exception as e:
                    print(f"[SERVER DEBUG] [Study OCR] Failed: {e}")

            asyncio.create_task(_run_ocr())
        except Exception as e:
            await sio.emit("error", {"msg": f"Study page image failed: {e}"}, room=sid)

    @sio.event
    async def study_page_share(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "session", None):
                return
            folder = (data or {}).get("folder") or ""
            file = (data or {}).get("file") or ""
            page = (data or {}).get("page")
            page_label = (data or {}).get("page_label") or ""
            mime_type = (data or {}).get("mime_type") or "image/jpeg"
            b64 = (data or {}).get("data") or ""
            if not page or not b64:
                return
            payload = {"mime_type": mime_type, "data": b64}
            study_reader.update_page_image(
                payload=payload,
                meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
            )
            print(f"[SERVER DEBUG] [Study] Page shared: {folder}/{file} page={page} label={page_label} mime={mime_type} bytes={len(b64)}")
            label_note = f" (book page {page_label})" if page_label else ""
            msg = (
                "System Notification: [Study Share] The user explicitly shared this page for deep reading. "
                f"Current page: {page}{label_note} from {folder}/{file}. "
                "Read ONLY the attached image. Do not guess if unreadable. "
                "Then produce: (1) concise notes (4-8 bullets), (2) key vocabulary/phrases (jp + romaji + meaning if visible), "
                "and (3) 3-6 short exercises. Use study_set_notes to fill the scratchpad, and study_set_fields to create answer inputs. "
                "If text is unclear, ask the user to zoom/share again."
            )
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
            await audio_loop.session.send(input=payload, end_of_turn=False)

            async def _run_ocr_share():
                try:
                    loop_audio = get_audio_loop()
                    if not loop_audio or not getattr(loop_audio, "session", None):
                        return
                    raw = base64.b64decode(b64)
                    text, err = await asyncio.to_thread(ocr_image_bytes_fn, raw)
                    if not text:
                        if err:
                            print(f"[SERVER DEBUG] [Study OCR] Unavailable: {err}")
                        return
                    cleaned = " ".join(str(text).split())
                    snippet = cleaned[:2000] + ("..." if len(cleaned) > 2000 else "")
                    study_reader.update_page_text(
                        text=snippet,
                        meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
                    )
                    ocr_msg = f"System Notification: [Study OCR] Extracted text snippet: {snippet}"
                    if hasattr(loop_audio, "send_system_message"):
                        await loop_audio.send_system_message(ocr_msg, end_of_turn=False)
                    else:
                        await loop_audio.session.send(input=ocr_msg, end_of_turn=False)
                except Exception as e:
                    print(f"[SERVER DEBUG] [Study OCR] Failed: {e}")

            asyncio.create_task(_run_ocr_share())
        except Exception as e:
            await sio.emit("error", {"msg": f"Study page share failed: {e}"}, room=sid)

    @sio.event
    async def study_page_tiles(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "session", None):
                return
            folder = (data or {}).get("folder") or ""
            file = (data or {}).get("file") or ""
            page = (data or {}).get("page")
            page_label = (data or {}).get("page_label") or ""
            tiles = (data or {}).get("tiles") or []
            if not page or not tiles:
                return
            payloads = []
            for tile in tiles:
                mime = tile.get("mime_type") or "image/png"
                b64 = tile.get("data") or ""
                if not b64:
                    continue
                payloads.append({"mime_type": mime, "data": b64})
            if not payloads:
                return
            study_reader.update_page_tiles(
                payloads=payloads,
                meta={"folder": folder, "file": file, "page": page, "page_label": page_label},
            )
            label_note = f" (book page {page_label})" if page_label else ""
            msg = (
                f"System Notification: [Study] Received {len(payloads)} zoom tiles for page {page} "
                f"from {folder}/{file}{label_note}. Use them to read small text."
            )
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
            for payload in payloads:
                await audio_loop.session.send(input=payload, end_of_turn=False)
        except Exception as e:
            await sio.emit("error", {"msg": f"Study page tiles failed: {e}"}, room=sid)
