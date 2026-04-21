from __future__ import annotations

from datetime import datetime


def serialize_reminders(reminder_manager):
    if not reminder_manager:
        return []

    items = reminder_manager.list()
    result = []
    for reminder in items:
        try:
            when_dt = datetime.fromisoformat(reminder.when_iso)
            when_epoch_ms = int(when_dt.timestamp() * 1000)
        except Exception:
            when_epoch_ms = None

        result.append(
            {
                "id": reminder.id,
                "message": reminder.message,
                "when_iso": reminder.when_iso,
                "speak": bool(reminder.speak),
                "when_epoch_ms": when_epoch_ms,
                "alert": bool(getattr(reminder, "alert", True)),
                "created_iso": getattr(reminder, "created_iso", None),
            }
        )

    result.sort(key=lambda x: (x["when_epoch_ms"] is None, x["when_epoch_ms"] or 0))
    return result
