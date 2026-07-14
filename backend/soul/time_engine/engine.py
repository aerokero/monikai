"""Time Engine — makes Monika aware of time passing.

Handles:
  - Gap detection: how long since last conversation
  - Seasonal context: what time of year it feels like
  - Anniversary tracking: meaningful dates from progression_state
  - Time-of-day context: energy hints for the assembler

Events emitted:
  LongGapDetected  — when a significant gap is detected
  AnniversaryObserved — when today matches a stored anniversary

Storage: progression_state table (keys: last_interaction_ts, anniversaries)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from backend.soul.events import AnniversaryObserved, LongGapDetected, bus

logger = logging.getLogger(__name__)

_KEY_LAST_TS = "last_interaction_ts"
_GAP_MEDIUM_H = 12.0     # hours → medium gap (narrative hint)
_GAP_LONG_H = 48.0       # hours → emit LongGapDetected
_GAP_VERY_LONG_H = 168.0  # 7 days → emit with stronger urgency


class TimeContext(NamedTuple):
    hour: int
    day_of_week: int        # 0=Monday … 6=Sunday
    month: int
    season: str             # "spring" | "summer" | "autumn" | "winter"
    time_of_day: str        # "morning" | "afternoon" | "evening" | "night"
    energy_hint: float      # 0.0 … 1.0 suggested base energy
    seasonal_mood: str      # brief prose label


class GapInfo(NamedTuple):
    hours: float
    category: str           # "fresh" | "short" | "medium" | "long" | "very_long"
    needs_decay_days: float # how many days of SDT decay to apply


class TimeEngine:
    """Provides time-aware context and detects gaps between conversations."""

    def __init__(self, event_bus=None) -> None:
        self._bus = event_bus or bus

    # ------------------------------------------------------------------
    # Turn recording
    # ------------------------------------------------------------------

    async def record_interaction(self, db_path: Path | None = None) -> None:
        """Call at every user turn to update last-seen timestamp."""
        from backend.progression.state import set_
        now = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
        await set_(_KEY_LAST_TS, now, db_path)

    # ------------------------------------------------------------------
    # Gap detection
    # ------------------------------------------------------------------

    async def check_gap(self, db_path: Path | None = None) -> GapInfo:
        """Compute hours since last interaction; emit LongGapDetected if warranted."""
        from backend.progression.state import get
        raw = await get(_KEY_LAST_TS, db_path)
        if raw is None:
            return GapInfo(hours=0.0, category="fresh", needs_decay_days=0.0)

        try:
            last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return GapInfo(hours=0.0, category="fresh", needs_decay_days=0.0)

        now = datetime.now(tz=timezone.utc)
        hours = max(0.0, (now - last).total_seconds() / 3600.0)
        info = _categorise_gap(hours)

        if info.category in ("long", "very_long"):
            await self._bus.emit(LongGapDetected(hours_since_last=hours))
            logger.info("Gap detected: %.1f hours (%s)", hours, info.category)

        return info

    # ------------------------------------------------------------------
    # Seasonal context
    # ------------------------------------------------------------------

    def get_context(self, now: datetime | None = None) -> TimeContext:
        """Return a TimeContext for the current moment (local time —
        time-of-day must match the user's clock, not UTC)."""
        dt = now or datetime.now().astimezone()
        season = _season(dt.month)
        tod = _time_of_day(dt.hour)
        energy = _energy_hint(dt.hour)
        return TimeContext(
            hour=dt.hour,
            day_of_week=dt.weekday(),
            month=dt.month,
            season=season,
            time_of_day=tod,
            energy_hint=energy,
            seasonal_mood=_seasonal_mood(season, dt.month),
        )

    def format_context(self, ctx: TimeContext | None = None) -> str:
        """Return a short prose block suitable for the assembled prompt."""
        c = ctx or self.get_context()
        day_name = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"][c.day_of_week]
        return (
            f"Teraz jest {c.time_of_day} — {day_name}, miesiąc {c.month}. "
            f"Pora roku: {_season_pl(c.season)}. {c.seasonal_mood}"
        )

    # ------------------------------------------------------------------
    # Anniversaries
    # ------------------------------------------------------------------

    async def check_anniversaries(
        self,
        db_path: Path | None = None,
        today: date | None = None,
    ) -> list[str]:
        """Check stored anniversaries for today; emit AnniversaryObserved if found."""
        from backend.progression.state import get
        anniversaries = (await get("anniversaries", db_path)) or []
        today_d = today or date.today()
        triggered: list[str] = []

        for ann in anniversaries:
            label = ann.get("label", "")
            date_str = ann.get("date", "")
            if not date_str:
                continue
            try:
                ann_date = date.fromisoformat(date_str)
            except ValueError:
                continue
            if ann_date.month == today_d.month and ann_date.day == today_d.day:
                days_elapsed = (today_d - ann_date).days
                await self._bus.emit(AnniversaryObserved(label=label, days_elapsed=days_elapsed))
                triggered.append(label)
                logger.info("Anniversary: %s (%d days ago)", label, days_elapsed)

        return triggered

    async def add_anniversary(
        self,
        label: str,
        date_str: str,
        db_path: Path | None = None,
    ) -> None:
        """Store a new anniversary in progression_state."""
        from backend.progression.state import get, set_
        anniversaries = (await get("anniversaries", db_path)) or []
        if not any(a.get("label") == label for a in anniversaries):
            anniversaries.append({"label": label, "date": date_str})
            await set_("anniversaries", anniversaries, db_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _categorise_gap(hours: float) -> GapInfo:
    if hours < 3:
        return GapInfo(hours=hours, category="fresh", needs_decay_days=0.0)
    if hours < _GAP_MEDIUM_H:
        return GapInfo(hours=hours, category="short", needs_decay_days=0.0)
    if hours < _GAP_LONG_H:
        return GapInfo(hours=hours, category="medium", needs_decay_days=hours / 24.0)
    if hours < _GAP_VERY_LONG_H:
        return GapInfo(hours=hours, category="long", needs_decay_days=hours / 24.0)
    return GapInfo(hours=hours, category="very_long", needs_decay_days=hours / 24.0)


def _season(month: int) -> str:
    if month in (12, 1, 2):  return "winter"
    if month in (3, 4, 5):   return "spring"
    if month in (6, 7, 8):   return "summer"
    return "autumn"


def _season_pl(season: str) -> str:
    return {"winter": "zima", "spring": "wiosna", "summer": "lato", "autumn": "jesień"}.get(season, season)


def _time_of_day(hour: int) -> str:
    if 6 <= hour < 12:   return "ranek"
    if 12 <= hour < 17:  return "południe"
    if 17 <= hour < 22:  return "wieczór"
    return "noc"


def _energy_hint(hour: int) -> float:
    table = {range(0, 6): 0.35, range(6, 9): 0.65, range(9, 18): 1.0,
             range(18, 22): 0.80, range(22, 24): 0.50}
    for rng, val in table.items():
        if hour in rng:
            return val
    return 0.70


def _seasonal_mood(season: str, month: int) -> str:
    moods = {
        "winter": "Cicho i chłodno. Długie wieczory.",
        "spring": "Coś się zaczyna. Powietrze zmienia się.",
        "summer": "Dni długie, ciepłe. Energie wyższe.",
        "autumn": "Powoli gaśnie. Złote i trochę melancholijne.",
    }
    return moods.get(season, "")
