import asyncio
from datetime import datetime

from .therapy_persona import resolve_session_kind


# Model used for the auto-generated session summary fallback (Gemini, like the
# rest of the app). Kept small/fast since it runs in the background.
import os

SESSION_SUMMARY_MODEL = os.getenv("SESSION_SUMMARY_MODEL", "gemini-2.5-flash")


def _build_relationship_context(memory_engine) -> str:
    """Assemble what Monika "remembers" about this person from past sessions.

    This is the alliance-over-time layer: a therapist who remembers you. We pull
    the most recent session summaries (reflection entries tagged
    'session_summary') and present them as her own knowledge, not as a quoted
    record.
    """
    if not memory_engine:
        return ""
    try:
        recent = memory_engine.list_recent(limit=25, types=["reflection"])
    except Exception:
        recent = []
    summaries = [r for r in recent if "session_summary" in (r.get("tags") or [])][:4]
    if not summaries:
        return ""

    lines = [
        "[Co pamiętasz o tej osobie z poprzednich sesji — nie wspominaj, że to "
        "czytasz; po prostu o tym wiedz i nawiązuj naturalnie, jeśli to pasuje:]"
    ]
    for s in summaries:
        date = (s.get("created_at") or "")[:10]
        content = (s.get("content") or "").strip().replace("\n", " ")
        if len(content) > 240:
            content = content[:240].rstrip() + "…"
        if content:
            lines.append(f"- {date}: {content}")
    return "\n".join(lines) if len(lines) > 1 else ""


async def _generate_session_summary(turns) -> str:
    """Generate a concise Polish session summary from the turns, via Gemini.

    Used only as the auto-finalize fallback when the model didn't write its own.
    Returns "" if there's nothing meaningful to summarize.
    """
    convo = "\n".join(
        f"{t.get('sender', '?')}: {(t.get('text') or '').strip()}"
        for t in (turns or [])
        if (t.get('text') or '').strip()
    )
    if not convo.strip():
        return ""

    prompt = (
        "Poniżej zapis sesji terapeutycznej między użytkownikiem a Moniką. "
        "Napisz zwięzłe podsumowanie po polsku (3-5 zdań) z perspektywy terapeutki: "
        "z czym przyszedł użytkownik, co się pojawiło, nad czym pracowaliście i co "
        "zostało otwarte na przyszłość. Bez nagłówków, sam tekst.\n\n" + convo
    )
    try:
        from google.genai import types
        from .model_config import client
        resp = await client.aio.models.generate_content(
            model=SESSION_SUMMARY_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=300, temperature=0.4),
        )
        return (resp.text or "").strip()
    except Exception:
        # Last-resort fallback: a compact transcript excerpt so continuity still
        # has something to build on.
        excerpt = convo.strip()
        return excerpt[:600] + ("…" if len(excerpt) > 600 else "")


def _read_summary_text(summary_path) -> str:
    try:
        raw = summary_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    # Strip the markdown header line if present.
    lines = [ln for ln in raw.splitlines() if not ln.startswith("# Session Summary")]
    return "\n".join(lines).strip()


async def _auto_finalize_after_delay(audio_loop, sio, sid, session_id, delay_sec=8):
    """Guarantee the session gets finalized + a summary surfaced to the user.

    Gives the model a chance to write its own summary first; after the delay, if
    summary.md still doesn't exist, generates one from the turns. Either way,
    emits 'session_finalized' so the user sees a wrap-up.
    """
    await asyncio.sleep(delay_sec)
    try:
        mem = getattr(audio_loop, "memory_engine", None)
        sm = getattr(audio_loop, "session_manager", None)
        if not mem or not sm or not session_id:
            return

        session_path = sm.get_session_path(session_id)
        summary_path = (session_path / "summary.md") if session_path else None

        if summary_path and summary_path.exists():
            # Model already finalized — just surface it.
            summary_text = _read_summary_text(summary_path)
            await sio.emit(
                "session_finalized",
                {"summary": summary_text, "auto": False},
                room=sid,
            )
            return

        # Auto-generate from this session's turns.
        turns = []
        if session_id == sm.get_current_session_id():
            turns = sm.get_current_session_turns(limit=24)
        summary_text = await _generate_session_summary(turns)
        if not summary_text:
            return

        result = mem.journal_finalize_session(
            summary=summary_text, reflections="", session_id=session_id
        )
        if result == "ok" and session_id == sm.get_current_session_id():
            try:
                sm.update_meta(finalized=True)
            except Exception:
                pass
        await sio.emit(
            "session_finalized",
            {"summary": summary_text, "auto": True},
            room=sid,
        )
    except Exception:
        pass


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
            active = bool((data or {}).get("active", False))
            kind = resolve_session_kind((data or {}).get("kind"))
            audio_loop = get_audio_loop()

            if not audio_loop:
                await sio.emit("session_mode", {"active": active, "kind": kind}, room=sid)
                return

            sm = getattr(audio_loop, "session_manager", None)
            mem = getattr(audio_loop, "memory_engine", None)

            if active:
                # Prepare what she'll "remember" BEFORE the reconnect rebuilds
                # the config, so it lands in the therapeutic system instruction.
                try:
                    audio_loop._session_relationship_context = _build_relationship_context(mem)
                except Exception:
                    audio_loop._session_relationship_context = None

                if sm:
                    try:
                        sm.update_meta(mode=kind)
                    except Exception:
                        pass

                # Flip the flag + trigger reconnect. Monika reconnects as the
                # therapist and opens the session herself (handled in run loop).
                audio_loop.set_session_mode(active=True, kind=kind)
                await sio.emit("session_mode", {"active": True, "kind": kind}, room=sid)
                return

            # --- Deactivating -------------------------------------------------
            session_id = sm.get_current_session_id() if sm else None

            # Best-effort: let her write a richer summary and close warmly while
            # still connected as the therapist (before the exit reconnect).
            if getattr(audio_loop, "session", None):
                try:
                    close_msg = (
                        "System Notification: Sesja dobiega końca. Pożegnaj się ciepło "
                        "jednym–dwoma zdaniami, a następnie wywołaj journal_finalize_session "
                        "z wewnętrznym podsumowaniem i refleksjami. Nie pokazuj podsumowania "
                        "użytkownikowi."
                    )
                    if hasattr(audio_loop, "send_system_message"):
                        await audio_loop.send_system_message(close_msg, end_of_turn=True)
                    else:
                        await audio_loop.session.send(input=close_msg, end_of_turn=True)
                except Exception:
                    pass

            # Flip the flag + trigger reconnect back to normal Monika.
            audio_loop.set_session_mode(active=False, kind=kind)

            if sm:
                try:
                    sm.update_meta(
                        ended_at=datetime.now().astimezone().isoformat(timespec="seconds")
                    )
                except Exception:
                    pass

            # Guaranteed finalization + summary surfaced to the user.
            asyncio.create_task(
                _auto_finalize_after_delay(audio_loop, sio, sid, session_id, delay_sec=8)
            )

            await sio.emit("session_mode", {"active": False, "kind": kind}, room=sid)
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to set session mode: {e}"}, room=sid)

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

            # Always let Monika know the user completed an exercise. send_system_message
            # handles a missing/closed session gracefully (queues or no-ops), so we
            # don't gate this behind audio_loop.session being present.
            if audio_loop and hasattr(audio_loop, "send_system_message"):
                try:
                    await audio_loop.send_system_message(
                        f"System Notification: The user completed an exercise '{title}'. "
                        "You can respond briefly and empathetically.",
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
