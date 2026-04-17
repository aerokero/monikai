from datetime import datetime


def register_session_mode_handlers(
    sio,
    *,
    get_audio_loop,
    journal_today_path,
    data_dir,
):
    @sio.event
    async def session_mode_set(sid, data):
        try:
            from .session_modes import get_session_mode_message, DEFAULT_KIND

            active = bool((data or {}).get("active", False))
            # Always keep session mode in AUTO so Monika can decide depth/pace.
            kind = DEFAULT_KIND
            audio_loop = get_audio_loop()
            if audio_loop and getattr(audio_loop, "set_session_mode", None):
                audio_loop.set_session_mode(active=active, kind=kind)
            await sio.emit('session_mode', {'active': active, 'kind': kind}, room=sid)

            if audio_loop and audio_loop.session:
                if active:
                    msg = get_session_mode_message(kind)
                else:
                    msg = (
                        "System Notification: Session mode disabled. "
                        "Please write an internal session summary and reflections. "
                        "Call journal_finalize_session with summary + reflections. "
                        "Do NOT show the summary to the user."
                    )
                if hasattr(audio_loop, "send_system_message"):
                    await audio_loop.send_system_message(msg, end_of_turn=False)
                else:
                    await audio_loop.session.send(input=msg, end_of_turn=False)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to set session mode: {e}"}, room=sid)

    @sio.event
    async def session_exercise_submit(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "memory_engine", None):
                await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
                return
            exercise_id = (data or {}).get("exercise_id") or "exercise"
            title = (data or {}).get("title") or exercise_id
            fields = (data or {}).get("fields") or {}
            notes = (data or {}).get("notes") or ""

            lines = [f"Exercise: {title}", ""]
            for k, v in fields.items():
                if v is None:
                    continue
                lines.append(f"- {k}: {v}")
            if notes:
                lines.extend(["", f"Notes: {notes}"])
            content = "\n".join(lines).strip()

            entry_id, _ = audio_loop.memory_engine.add_entry(
                type="reflection",
                content=content,
                tags=["exercise", exercise_id],
                entities=["user"],
                origin="real",
                confidence=0.7,
                stability="medium",
                data={"exercise_id": exercise_id, "title": title, "fields": fields, "notes": notes},
            )

            try:
                journal_path, _ = journal_today_path()
                block = [
                    f"## Exercise: {title} ({datetime.now().strftime('%H:%M')})",
                    *[f"- {k}: {v}" for k, v in fields.items() if v is not None and str(v).strip()],
                ]
                if notes:
                    block.append(f"- Notes: {notes}")
                audio_loop.memory_engine.append_page(str(journal_path), "\n".join(block) + "\n")
            except Exception:
                pass

            await sio.emit('session_exercise_saved', {'id': entry_id}, room=sid)

            if audio_loop and audio_loop.session:
                try:
                    if hasattr(audio_loop, "send_system_message"):
                        await audio_loop.send_system_message(
                            f"System Notification: The user completed an exercise '{title}'. You can respond briefly and empathetically.",
                            end_of_turn=False,
                        )
                    else:
                        await audio_loop.session.send(
                            input=f"System Notification: The user completed an exercise '{title}'. You can respond briefly and empathetically.",
                            end_of_turn=False,
                        )
                except Exception:
                    pass
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to save exercise: {e}"}, room=sid)

    @sio.event
    async def session_sketch_save(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "memory_engine", None):
                await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
                return
            image_data = (data or {}).get("image")
            label = (data or {}).get("label") or "feeling_sketch"
            if not image_data or "base64," not in image_data:
                await sio.emit('error', {'msg': "Invalid image data."}, room=sid)
                return

            header, b64 = image_data.split("base64,", 1)
            ext = "png"
            if "image/jpeg" in header:
                ext = "jpg"

            date_dir = datetime.now().strftime("%Y-%m-%d")
            out_dir = data_dir / "memory" / "pages" / "journal" / "sketches" / date_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = f"sketch_{datetime.now().strftime('%H%M%S')}.{ext}"
            path = out_dir / filename

            import base64 as _b64
            path.write_bytes(_b64.b64decode(b64))

            entry_id, _ = audio_loop.memory_engine.add_entry(
                type="reflection",
                content=f"Feeling sketch saved: {label}",
                tags=["sketch", "session"],
                entities=["user"],
                origin="real",
                confidence=0.6,
                stability="low",
                data={"file": str(path), "label": label},
            )

            try:
                journal_path, _ = journal_today_path()
                rel = path.relative_to(data_dir)
                audio_loop.memory_engine.append_page(
                    str(journal_path),
                    f"## Feeling Sketch ({datetime.now().strftime('%H:%M')})\n- file: {rel.as_posix()}\n- label: {label}\n",
                )
            except Exception:
                pass

            await sio.emit('session_sketch_saved', {'id': entry_id, 'file': str(path)}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to save sketch: {e}"}, room=sid)
