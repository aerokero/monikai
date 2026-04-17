def register_calendar_reminder_handlers(
    sio,
    *,
    get_calendar_manager,
    get_reminder_manager,
    serialize_reminders,
    get_audio_loop,
):
    @sio.event
    async def list_reminders(sid, data=None):
        """Frontend requests current reminder list."""
        result = {"reminders": serialize_reminders()}
        await sio.emit("reminders_list", result, room=sid)
        return result

    @sio.event
    async def reminders_list(sid, data=None):
        """Compatibility handler for clients that request reminders via reminders_list event."""
        result = {"reminders": serialize_reminders()}
        await sio.emit("reminders_list", result, room=sid)
        return result

    @sio.event
    async def list_calendar(sid, data=None):
        """Frontend requests current calendar events."""
        events = []
        calendar_manager = get_calendar_manager()
        if calendar_manager:
            events = [e.__dict__ for e in calendar_manager.get_all_events()]
        await sio.emit("calendar_data", events, room=sid)

    @sio.event
    async def delete_event(sid, data):
        """Frontend deletes a calendar event."""
        eid = (data or {}).get("id")
        if not eid:
            return
        calendar_manager = get_calendar_manager()
        if calendar_manager:
            calendar_manager.delete_event(eid)

    @sio.event
    async def update_reminder(sid, data):
        rid = data.get("id")
        msg = data.get("message")
        reminder_manager = get_reminder_manager()
        if reminder_manager and rid:
            reminder_manager.update(rid, message=msg)
            await sio.emit("reminders_list", {"reminders": serialize_reminders()}, room=sid)

    @sio.event
    async def update_event(sid, data):
        eid = data.get("id")
        summary = data.get("summary")
        calendar_manager = get_calendar_manager()
        if calendar_manager and eid:
            calendar_manager.update_event(eid, summary=summary)
            events = [e.__dict__ for e in calendar_manager.get_all_events()]
            await sio.emit("calendar_data", events, room=sid)

    @sio.event
    async def cancel_reminder(sid, data):
        """Frontend cancels a reminder by id."""
        rid = (data or {}).get("id")
        if not rid:
            await sio.emit("error", {"msg": "cancel_reminder: Missing id"}, room=sid)
            return

        reminder_manager = get_reminder_manager()
        if not reminder_manager:
            await sio.emit("error", {"msg": "Reminders not available"}, room=sid)
            return

        ok = reminder_manager.cancel(rid)
        await sio.emit("reminders_list", {"reminders": serialize_reminders()}, room=sid)
        if ok:
            await sio.emit("status", {"msg": "Reminder cancelled"}, room=sid)
        else:
            await sio.emit("status", {"msg": "Reminder not found"}, room=sid)

    @sio.event
    async def create_reminder(sid, data):
        """Optional: Frontend can create a reminder (same semantics as the model tool)."""
        reminder_manager = get_reminder_manager()
        if not reminder_manager:
            await sio.emit("error", {"msg": "Reminders not available"}, room=sid)
            return

        data = data or {}
        message = (data.get("message") or "").strip()
        at = data.get("at")
        in_minutes = data.get("in_minutes")
        in_seconds = data.get("in_seconds")
        speak = data.get("speak", True)
        alert = data.get("alert", True)

        if not message:
            await sio.emit("error", {"msg": "create_reminder: Missing message"}, room=sid)
            return

        try:
            rem = reminder_manager.create(
                message=message,
                at=at,
                in_minutes=in_minutes,
                in_seconds=in_seconds,
                speak=speak,
                alert=alert,
            )
            await sio.emit("status", {"msg": f"Reminder created ({rem.id})"}, room=sid)

            try:
                audio_loop = get_audio_loop()
                if getattr(audio_loop, "session", None):
                    kind = "timer" if (in_seconds is not None or in_minutes is not None) and (at is None) else "reminder"
                    when_desc = rem.when_iso
                    await audio_loop.session.send(
                        input=(
                            f"System Notification: User manually created a {kind}. \
Message: {rem.message}. \
When: {when_desc}. \
Speak: {bool(rem.speak)}. Alert: {bool(getattr(rem, 'alert', True))}."
                        ),
                        end_of_turn=False,
                    )
            except Exception as e:
                print(f"[SERVER] Failed to notify model about reminder: {e}")
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to create reminder: {e}"}, room=sid)

        await sio.emit("reminders_list", {"reminders": serialize_reminders()}, room=sid)

    @sio.event
    async def create_event(sid, data):
        """Frontend creates a calendar event."""
        calendar_manager = get_calendar_manager()
        if not calendar_manager:
            await sio.emit("error", {"msg": "Calendar not available"}, room=sid)
            return

        data = data or {}
        summary = data.get("summary")
        start_iso = data.get("start_iso")
        end_iso = data.get("end_iso")
        description = data.get("description")

        if not summary or not start_iso or not end_iso:
            await sio.emit("error", {"msg": "create_event: Missing summary, start_iso, or end_iso"}, room=sid)
            return

        try:
            event = calendar_manager.create_event(
                summary=summary,
                start_iso=start_iso,
                end_iso=end_iso,
                description=description,
            )
            await sio.emit("status", {"msg": f"Event created ({event.id})"}, room=sid)
        except Exception as e:
            await sio.emit("error", {"msg": f"Failed to create event: {e}"}, room=sid)

        if calendar_manager:
            events = [e.__dict__ for e in calendar_manager.get_all_events()]
            await sio.emit("calendar_data", events, room=sid)
