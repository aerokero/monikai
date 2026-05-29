import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Any

from ..core.session_context import get_time_context


@dataclass
class Reminder:
    id: str
    message: str
    when_iso: str
    speak: bool
    alert: bool = True


class ReminderManager:
    def __init__(
        self,
        get_time_context_fn: Callable[[], dict],
        storage_dir: Path,
        on_reminder: Optional[Callable[["Reminder"], Any]] = None,
    ):
        self.get_time_context_fn = get_time_context_fn
        self.storage_dir = storage_dir
        self.on_reminder = on_reminder
        self.reminders: Dict[str, Reminder] = {}
        self.tasks: Dict[str, asyncio.Task] = {}

    def _save(self):
        data = [
            {
                "id": r.id,
                "message": r.message,
                "when_iso": r.when_iso,
                "speak": r.speak,
                "alert": getattr(r, "alert", True),
            }
            for r in self.reminders.values()
        ]
        try:
            file_path = self.storage_dir / "reminders.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[REMINDERS] Failed to save reminders: {e}")

    def load(self):
        file_path = self.storage_dir / "reminders.json"
        if not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data:
                rid = item["id"]
                if rid in self.reminders:
                    continue
                try:
                    when_iso = item["when_iso"]
                    when = datetime.fromisoformat(when_iso)
                    reminder = Reminder(
                        id=rid,
                        message=item["message"],
                        when_iso=when_iso,
                        speak=item.get("speak", True),
                        alert=item.get("alert", True),
                    )
                    self.reminders[rid] = reminder
                    self.tasks[rid] = asyncio.create_task(self._runner(reminder, when))
                except Exception as e:
                    print(f"[REMINDERS] Skipping invalid reminder: {e}")
        except Exception as e:
            print(f"[REMINDERS] Failed to load reminders: {e}")

    def clear(self):
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()
        self.reminders.clear()

    def _now(self) -> datetime:
        ctx = self.get_time_context_fn()
        return datetime.fromisoformat(ctx["iso"])

    def _parse_at_local(self, at_str: str) -> datetime:
        now = self._now()
        tz = now.tzinfo
        dt_naive = datetime.strptime(at_str, "%Y-%m-%d %H:%M")
        return dt_naive.replace(tzinfo=tz)

    async def _runner(self, reminder: "Reminder", when: datetime):
        delay = (when - self._now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

        if self.on_reminder:
            maybe = self.on_reminder(reminder)
            if asyncio.iscoroutine(maybe):
                await maybe

        self.reminders.pop(reminder.id, None)
        self._save()
        task = self.tasks.pop(reminder.id, None)
        if task:
            try:
                task.cancel()
            except Exception:
                pass

    def create(
        self,
        message: str,
        at: Optional[str] = None,
        in_minutes: Optional[int] = None,
        in_seconds: Optional[int] = None,
        speak: bool = True,
        alert: bool = True,
        dedup_window_sec: int = 60,
    ) -> "Reminder":
        message = (message or "").strip()
        if not message:
            raise ValueError("Message is required.")

        provided = sum([
            bool(at and str(at).strip()),
            in_minutes is not None,
            in_seconds is not None,
        ])
        if provided != 1:
            raise ValueError("Provide exactly one of 'at', 'in_minutes', or 'in_seconds'.")

        now = self._now()

        if in_seconds is not None:
            when = now + timedelta(seconds=int(in_seconds))
        elif in_minutes is not None:
            when = now + timedelta(minutes=int(in_minutes))
        else:
            when = self._parse_at_local(at)

        when_iso = when.isoformat(timespec="seconds")
        msg_norm = message.lower()

        for r in self.reminders.values():
            try:
                existing = datetime.fromisoformat(r.when_iso)
                if r.message.strip().lower() == msg_norm:
                    if abs((existing - when).total_seconds()) <= dedup_window_sec:
                        return r
            except Exception:
                pass

        rid = str(uuid.uuid4())
        reminder = Reminder(
            id=rid,
            message=message,
            when_iso=when_iso,
            speak=bool(speak),
            alert=bool(alert),
        )
        self.reminders[rid] = reminder
        self.tasks[rid] = asyncio.create_task(self._runner(reminder, when))
        self._save()
        return reminder

    def update(self, rid: str, message: str = None) -> bool:
        if rid in self.reminders:
            rem = self.reminders[rid]
            if message is not None:
                rem.message = message
            self._save()
            return True
        return False

    def list(self) -> list["Reminder"]:
        return list(self.reminders.values())

    def cancel(self, rid: str) -> bool:
        task = self.tasks.get(rid)
        if task:
            task.cancel()
        existed = rid in self.reminders
        self.reminders.pop(rid, None)
        self.tasks.pop(rid, None)
        if existed:
            self._save()
        return existed
