"""Socket API for the conversation sidebar (v3 Phase G).

Events (client → server → reply):
  conversations_list     {limit?, offset?}      → "conversations_list"
  conversations_get      {id, max_turns?}       → "conversation_detail"
  conversations_new      {}                     → "conversation_started"
  conversations_continue {id}                   → "conversation_started"
  conversations_delete   {id}                   → "conversation_deleted"

Continuing an old conversation NEVER reopens it — the old session stays
digested and read-only. A fresh session starts with the old digest injected
as context and ``continues: <id>`` recorded in its meta.
"""

from backend.core import conversation_store


def register_conversation_handlers(sio, *, get_audio_loop):
    def _session_manager():
        audio_loop = get_audio_loop()
        return getattr(audio_loop, "session_manager", None) if audio_loop else None

    @sio.event
    async def conversations_list(sid, data=None):
        try:
            sm = _session_manager()
            if not sm:
                await sio.emit("conversations_list", {"items": [], "current_id": None}, room=sid)
                return
            data = data or {}
            items = conversation_store.list_conversations(
                sm.sessions_dir,
                limit=max(1, min(200, int(data.get("limit", 60)))),
                offset=max(0, int(data.get("offset", 0))),
            )
            await sio.emit(
                "conversations_list",
                {"items": items, "current_id": sm.get_current_session_id()},
                room=sid,
            )
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to list conversations: {e}"}, room=sid)

    @sio.event
    async def conversations_get(sid, data=None):
        try:
            sm = _session_manager()
            session_id = str((data or {}).get("id") or "")
            if not sm or not session_id:
                await sio.emit("conversation_detail", {"item": None}, room=sid)
                return
            # Make sure the current conversation's buffered turns are readable.
            try:
                sm.flush_session(session_id)
            except Exception:
                pass
            item = conversation_store.get_conversation(
                sm.sessions_dir,
                session_id,
                max_turns=max(1, min(2000, int((data or {}).get("max_turns", 500)))),
            )
            await sio.emit("conversation_detail", {"item": item}, room=sid)
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to load conversation: {e}"}, room=sid)

    @sio.event
    async def conversations_new(sid, data=None):
        try:
            sm = _session_manager()
            if not sm:
                await sio.emit("error", {"msg": "Session manager not available."}, room=sid)
                return
            new_id = sm.start_new_session()
            audio_loop = get_audio_loop()
            if audio_loop and hasattr(audio_loop, "send_system_message"):
                try:
                    await audio_loop.send_system_message(
                        "System Notification: The user started a NEW conversation. "
                        "Treat this as a fresh start — do not carry over the previous "
                        "topic unless the user brings it up.",
                        end_of_turn=False,
                    )
                except Exception:
                    pass
            await sio.emit("conversation_started", {"id": new_id, "continues": None}, room=sid)
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to start conversation: {e}"}, room=sid)

    @sio.event
    async def conversations_delete(sid, data=None):
        try:
            sm = _session_manager()
            session_id = str((data or {}).get("id") or "")
            if not sm or not session_id:
                await sio.emit("error", {"msg": "Missing conversation id."}, room=sid)
                return

            # Deleting the LIVE conversation: rotate to a fresh session first,
            # so nothing keeps writing into the directory we remove.
            if session_id == sm.get_current_session_id():
                sm.start_new_session()
            else:
                # Flush any buffered turns so we never delete a dir mid-write.
                try:
                    sm.flush_session(session_id)
                except Exception:
                    pass

            ok = conversation_store.delete_conversation(sm.sessions_dir, session_id)
            if not ok:
                await sio.emit("error", {"msg": f"Conversation not found: {session_id}"}, room=sid)
                return
            await sio.emit(
                "conversation_deleted",
                {"id": session_id, "current_id": sm.get_current_session_id()},
                room=sid,
            )
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to delete conversation: {e}"}, room=sid)

    @sio.event
    async def conversations_continue(sid, data=None):
        try:
            sm = _session_manager()
            old_id = str((data or {}).get("id") or "")
            if not sm or not old_id:
                await sio.emit("error", {"msg": "Missing conversation id."}, room=sid)
                return

            context = conversation_store.build_continuation_context(
                sm.sessions_dir, old_id, last_turns=10
            )
            if not context:
                await sio.emit("error", {"msg": f"Conversation not found: {old_id}"}, room=sid)
                return

            new_id = sm.start_new_session(extra_meta={"continues": old_id})

            audio_loop = get_audio_loop()
            if audio_loop and hasattr(audio_loop, "send_system_message"):
                try:
                    await audio_loop.send_system_message(
                        "System Notification: The user wants to CONTINUE an earlier "
                        "conversation. You remember it — pick the thread back up "
                        "naturally, without saying you read a log.\n\n" + context,
                        end_of_turn=False,
                    )
                except Exception:
                    pass
            await sio.emit("conversation_started", {"id": new_id, "continues": old_id}, room=sid)
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to continue conversation: {e}"}, room=sid)
