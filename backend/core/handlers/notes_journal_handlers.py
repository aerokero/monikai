def register_notes_journal_handlers(
    sio,
    *,
    read_notes_text,
    write_notes_text,
    append_notes_text,
    read_journal_today,
    get_audio_loop,
):
    @sio.event
    async def notes_get(sid):
        text = read_notes_text()
        await sio.emit('notes_data', {'text': text, 'scope': 'global'}, room=sid)

    @sio.event
    async def notes_set(sid, data):
        try:
            content = (data or {}).get("content", "")
            write_notes_text(content)
            await sio.emit('notes_data', {'text': content, 'scope': 'global'}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to save notes: {e}"}, room=sid)

    @sio.event
    async def notes_append(sid, data):
        try:
            content = (data or {}).get("content", "")
            append_notes_text(content)
            text = read_notes_text()
            await sio.emit('notes_data', {'text': text, 'scope': 'global'}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to append notes: {e}"}, room=sid)

    @sio.event
    async def notes_clear(sid):
        try:
            write_notes_text("")
            await sio.emit('notes_data', {'text': "", 'scope': 'global'}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to clear notes: {e}"}, room=sid)

    @sio.event
    async def journal_get_today(sid):
        text, date_key = read_journal_today()
        await sio.emit('journal_today', {'text': text, 'date': date_key}, room=sid)

    @sio.event
    async def journal_add(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "memory_engine", None):
                await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
                return
            content = (data or {}).get("content", "")
            topics = (data or {}).get("topics") or []
            mood = (data or {}).get("mood")
            tags = (data or {}).get("tags") or []

            entry_id = audio_loop.memory_engine.journal_add_entry(
                content=content,
                topics=topics,
                mood=mood,
                tags=tags,
            )
            await sio.emit('journal_saved', {'id': entry_id}, room=sid)
            text, date_key = read_journal_today()
            await sio.emit('journal_today', {'text': text, 'date': date_key}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to add journal entry: {e}"}, room=sid)

    @sio.event
    async def journal_finalize(sid, data):
        try:
            audio_loop = get_audio_loop()
            if not audio_loop or not getattr(audio_loop, "memory_engine", None):
                await sio.emit('error', {'msg': "Memory engine not available."}, room=sid)
                return
            summary = (data or {}).get("summary", "")
            reflections = (data or {}).get("reflections")
            session_id = (data or {}).get("session_id")
            result = audio_loop.memory_engine.journal_finalize_session(
                summary=summary,
                reflections=reflections,
                session_id=session_id,
            )
            await sio.emit('journal_finalized', {'status': result}, room=sid)
        except Exception as e:
            await sio.emit('error', {'msg': f"Failed to finalize session: {e}"}, room=sid)
