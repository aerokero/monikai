import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional, Any

from ..core.session_context import HOLIDAYS, get_holiday_context, load_settings_safe


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start_iso: str
    end_iso: str
    description: Optional[str] = None
    all_day: bool = False


def _parse_calendar_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt.astimezone()


def _calendar_ranges_overlap(
    event_start_iso: str,
    event_end_iso: str,
    range_start: datetime,
    range_end: datetime,
) -> bool:
    event_start = _parse_calendar_datetime(event_start_iso)
    event_end = _parse_calendar_datetime(event_end_iso)
    if event_end <= event_start:
        event_end = event_start + timedelta(minutes=1)
    return event_start < range_end and event_end > range_start


def _normalize_all_day_bounds(start_iso: str, end_iso: str) -> tuple[str, str]:
    start_dt = _parse_calendar_datetime(start_iso)
    end_dt = _parse_calendar_datetime(end_iso)
    tz = start_dt.tzinfo
    start_day = datetime(start_dt.year, start_dt.month, start_dt.day, 0, 0, 0, tzinfo=tz)
    end_day = datetime(end_dt.year, end_dt.month, end_dt.day, 0, 0, 0, tzinfo=tz)

    # Store all-day events as [start, exclusive_end). If the caller sends a
    # same-day or end-of-day timestamp, convert it to the next midnight.
    if end_day <= start_day or end_dt.time() != datetime.min.time():
        end_day = end_day + timedelta(days=1)
    return start_day.isoformat(), end_day.isoformat()


class CalendarManager:
    def __init__(self, storage_dir: Path, on_update: Optional[Callable[[], Any]] = None):
        self.storage_dir = storage_dir
        self.on_update = on_update
        self.events: Dict[str, CalendarEvent] = {}
        self.user_birthday: Optional[tuple[int, int]] = None

    def set_user_birthday(self, month: int, day: int):
        self.user_birthday = (month, day)

    def _save(self):
        data = [e.__dict__ for e in self.events.values()]
        try:
            file_path = self.storage_dir / "calendar.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if self.on_update:
                self.on_update()
        except Exception as e:
            print(f"[CALENDAR] Failed to save events: {e}")

    def load(self):
        file_path = self.storage_dir / "calendar.json"
        if not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.events.clear()
            for item in data:
                event = CalendarEvent(**item)
                self.events[event.id] = event
            if self.on_update:
                self.on_update()
        except Exception as e:
            print(f"[CALENDAR] Failed to load events: {e}")

    def create_event(
        self,
        summary: str,
        start_iso: str,
        end_iso: str,
        description: Optional[str] = None,
        all_day: bool = False,
    ) -> CalendarEvent:
        if all_day:
            start_iso, end_iso = _normalize_all_day_bounds(start_iso, end_iso)
        event_id = str(uuid.uuid4())
        event = CalendarEvent(
            id=event_id,
            summary=summary,
            start_iso=start_iso,
            end_iso=end_iso,
            description=description,
            all_day=all_day,
        )
        self.events[event_id] = event
        self._save()
        return event

    def update_event(self, event_id: str, summary: str = None) -> bool:
        if event_id in self.events:
            evt = self.events[event_id]
            if summary is not None:
                evt.summary = summary
            self._save()
            return True
        return False

    def list_events(self, start_range_iso: str, end_range_iso: str) -> list[CalendarEvent]:
        try:
            start_range = _parse_calendar_datetime(start_range_iso)
        except (ValueError, AttributeError) as e:
            print(f"[CALENDAR] Failed to parse start_range_iso: {start_range_iso}, error: {e}")
            start_range = datetime.now().astimezone()

        try:
            end_range = _parse_calendar_datetime(end_range_iso)
        except (ValueError, AttributeError) as e:
            print(f"[CALENDAR] Failed to parse end_range_iso: {end_range_iso}, error: {e}")
            end_range = datetime.now().astimezone() + timedelta(days=1)

        results = []
        for e in self.events.values():
            try:
                if _calendar_ranges_overlap(e.start_iso, e.end_iso, start_range, end_range):
                    results.append(e)
            except (ValueError, AttributeError) as err:
                print(f"[CALENDAR] Failed to parse event {e.id}: {err}")
                continue

        start_year = start_range.year
        end_year = end_range.year
        tz = start_range.tzinfo

        settings = load_settings_safe()
        custom_dates = settings.get("special_dates") or {}
        all_holidays = HOLIDAYS.copy()
        for date_str, name in custom_dates.items():
            try:
                m, d = map(int, date_str.split("-"))
                all_holidays[(m, d)] = name
            except Exception:
                pass

        for year in range(start_year, end_year + 1):
            if self.user_birthday:
                bm, bd = self.user_birthday
                try:
                    b_start = datetime(year, bm, bd, 0, 0, 0, tzinfo=tz)
                    if start_range <= b_start < end_range:
                        results.append(CalendarEvent(
                            id=f"birthday-{year}",
                            summary="User's Birthday",
                            start_iso=b_start.isoformat(),
                            end_iso=(b_start + timedelta(days=1)).isoformat(),
                            description="Happy Birthday!",
                        ))
                except ValueError:
                    pass

            for (month, day), name in all_holidays.items():
                try:
                    h_start = datetime(year, month, day, 0, 0, 0, tzinfo=tz)
                    if start_range <= h_start < end_range:
                        results.append(CalendarEvent(
                            id=f"holiday-{year}-{month:02d}-{day:02d}",
                            summary=name,
                            start_iso=h_start.isoformat(),
                            end_iso=(h_start + timedelta(days=1)).isoformat(),
                            description="Holiday",
                        ))
                except ValueError:
                    pass

        results.sort(key=lambda e: e.start_iso)
        return results

    def get_all_events(self) -> list[CalendarEvent]:
        """Returns all stored events plus holidays for current and adjacent years."""
        results = list(self.events.values())
        now = datetime.now()
        years = range(now.year - 2, now.year + 3)

        settings = load_settings_safe()
        custom_dates = settings.get("special_dates") or {}
        all_holidays = HOLIDAYS.copy()
        for date_str, name in custom_dates.items():
            try:
                m, d = map(int, date_str.split("-"))
                all_holidays[(m, d)] = name
            except Exception:
                pass

        for year in years:
            if self.user_birthday:
                bm, bd = self.user_birthday
                try:
                    h_start = datetime(year, bm, bd, 0, 0, 0).astimezone()
                    results.append(CalendarEvent(
                        id=f"birthday-{year}",
                        summary="User's Birthday",
                        start_iso=h_start.isoformat(),
                        end_iso=(h_start + timedelta(days=1)).isoformat(),
                        description="Happy Birthday!",
                    ))
                except ValueError:
                    pass

            for (month, day), name in all_holidays.items():
                try:
                    h_start = datetime(year, month, day, 0, 0, 0).astimezone()
                    results.append(CalendarEvent(
                        id=f"holiday-{year}-{month:02d}-{day:02d}",
                        summary=name,
                        start_iso=h_start.isoformat(),
                        end_iso=(h_start + timedelta(days=1)).isoformat(),
                        description="Holiday",
                    ))
                except ValueError:
                    pass

        results.sort(key=lambda e: e.start_iso)
        return results

    def get_todays_events(self) -> list[CalendarEvent]:
        now = datetime.now().astimezone()
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=now.tzinfo)
        today_end = today_start + timedelta(days=1)
        todays = []

        for e in self.events.values():
            try:
                if _calendar_ranges_overlap(e.start_iso, e.end_iso, today_start, today_end):
                    todays.append(e)
            except Exception:
                pass

        if self.user_birthday:
            bm, bd = self.user_birthday
            if now.month == bm and now.day == bd:
                start_dt = datetime(now.year, now.month, now.day, 0, 0, 0).astimezone()
                todays.append(CalendarEvent(
                    id="birthday-today",
                    summary="User's Birthday",
                    start_iso=start_dt.isoformat(),
                    end_iso=(start_dt + timedelta(days=1)).isoformat(),
                    description="Happy Birthday!",
                ))

        holiday_name = get_holiday_context()
        if holiday_name:
            start_dt = datetime(now.year, now.month, now.day, 0, 0, 0).astimezone()
            todays.append(CalendarEvent(
                id="holiday-today",
                summary=holiday_name,
                start_iso=start_dt.isoformat(),
                end_iso=(start_dt + timedelta(days=1)).isoformat(),
                description="Holiday",
            ))

        return todays

    def delete_event(self, event_id: str) -> bool:
        if event_id in self.events:
            del self.events[event_id]
            self._save()
            return True
        return False
