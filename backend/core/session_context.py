import json
import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from .config import SETTINGS_PATH


def load_settings_safe() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_time_context() -> dict:
    """Returns local time context based on settings.json time_settings.

    Supports mode=system (OS local time zone) and mode=manual (IANA timezone).
    """
    settings = load_settings_safe()
    cfg = settings.get("time_settings") or {}
    mode = (cfg.get("mode") or "system").lower()

    if mode == "manual":
        tz_name = cfg.get("timezone") or "UTC"
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        offset = now.strftime("%z")
        return {
            "mode": "manual",
            "timezone": tz_name,
            "iso": now.isoformat(),
            "offset": offset,
            "epoch_ms": int(now.timestamp() * 1000),
        }

    now_local = datetime.now().astimezone()
    tzinfo = now_local.tzinfo
    tz_name = getattr(tzinfo, "key", None) or str(tzinfo) or "local"
    offset = now_local.strftime("%z")

    return {
        "mode": "system",
        "timezone": tz_name,
        "iso": now_local.isoformat(),
        "offset": offset,
        "epoch_ms": int(now_local.timestamp() * 1000),
    }


HOLIDAYS: dict[tuple[int, int], str] = {
    (1, 1): "holidays.new_year",
    (2, 14): "holidays.valentines",
    (3, 8): "holidays.womens_day",
    (3, 14): "holidays.white_day",
    (4, 1): "holidays.april_fools",
    (4, 22): "holidays.earth_day",
    (5, 1): "holidays.labor_day",
    (5, 4): "holidays.star_wars",
    (6, 5): "holidays.environment_day",
    (7, 30): "holidays.friendship_day",
    (8, 12): "holidays.youth_day",
    (9, 13): "holidays.programmers_day",
    (9, 21): "holidays.peace_day",
    (9, 22): "holidays.monika_birthday",
    (10, 4): "holidays.animal_day",
    (10, 31): "holidays.halloween",
    (11, 11): "holidays.independence_day",
    (12, 24): "holidays.christmas_eve",
    (12, 25): "holidays.christmas",
    (12, 31): "holidays.new_years_eve",
}


def get_holiday_context() -> Optional[str]:
    """Returns the holiday key for today, or None if not a special date."""
    now = datetime.now()
    month = now.month
    day = now.day

    settings = load_settings_safe()
    custom = settings.get("special_dates") or {}
    key = f"{month:02d}-{day:02d}"
    if key in custom:
        return custom[key]

    return HOLIDAYS.get((month, day))
