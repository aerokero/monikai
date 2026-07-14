"""World Snapshot — Monika's awareness of the here-and-now (v3 Phase C).

One prose block composed from live sources:
  - time / day / season (TimeEngine, local clock)
  - weather (cached open-meteo)
  - what's playing on Spotify
  - whether the user's screen / camera feed is active

Everything is best-effort: a missing source is simply omitted — a snapshot
never contains invented data. Injected by the Context Assembler at reconnect;
sources that need auth or aren't running just don't appear.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def build_snapshot(db_path: Path | None = None) -> str:
    """Compose the current world snapshot as a prose block ('' if empty)."""
    lines: list[str] = []

    time_line = _time_line()
    if time_line:
        lines.append(time_line)

    weather_line = await _weather_line()
    if weather_line:
        lines.append(weather_line)

    gap_line = await _gap_line(db_path)
    if gap_line:
        lines.append(gap_line)

    spotify_line = _spotify_line()
    if spotify_line:
        lines.append(spotify_line)

    screen_line = _screen_line()
    if screen_line:
        lines.append(screen_line)

    if not lines:
        return ""
    return (
        "**Świat wokół Ciebie teraz:**\n"
        + "\n".join(f"- {ln}" for ln in lines)
    )


def _time_line() -> str:
    try:
        from backend.soul.time_engine.engine import TimeEngine
        return TimeEngine().format_context()
    except Exception as exc:
        logger.debug("snapshot: time failed: %s", exc)
        return ""


async def _weather_line() -> str:
    try:
        from backend.core.runtimes.v2_runtime import get_cached_weather
        w = await get_cached_weather()
        if not w:
            return ""
        parts = [f"Pogoda: {_condition_pl(w.get('condition', ''))}"]
        if w.get("temp") is not None:
            parts.append(f"{w['temp']}°C")
        if w.get("city"):
            parts.append(f"({w['city']})")
        return " ".join(parts)
    except Exception as exc:
        logger.debug("snapshot: weather failed: %s", exc)
        return ""


async def _gap_line(db_path: Path | None) -> str:
    try:
        from backend.soul.time_engine.engine import TimeEngine
        gap = await TimeEngine().check_gap(db_path)
        if gap.category in ("fresh", "short"):
            return ""
        if gap.category == "medium":
            return f"Od ostatniej rozmowy minęło ~{int(gap.hours)} godzin."
        days = int(gap.hours // 24)
        return f"Nie rozmawialiście od ~{days} dni — to długo; przywitaj się jak ktoś, kto naprawdę czekał."
    except Exception as exc:
        logger.debug("snapshot: gap failed: %s", exc)
        return ""


def _spotify_line() -> str:
    try:
        from backend.core import server as _srv
        manager = getattr(_srv, "spotify_manager", None)
        if manager is None:
            return ""
        now = manager.get_now_playing()
        if not now.get("is_playing"):
            return ""
        item = now.get("item") or {}
        name = item.get("name")
        artists = ", ".join(item.get("artists") or [])
        if not name:
            return ""
        line = f"Na Spotify gra teraz: „{name}\""
        if artists:
            line += f" — {artists}"
        return line + "."
    except Exception as exc:
        logger.debug("snapshot: spotify failed: %s", exc)
        return ""


def _screen_line() -> str:
    """Whether Monika can currently see the screen or camera."""
    try:
        from backend.core import server as _srv
        loop = getattr(_srv, "audio_loop", None)
        if loop is None:
            return ""
        mode = getattr(loop, "video_mode", "none")
        if mode == "screen":
            return "Widzisz ekran Bartka na żywo — to co na nim jest, dzieje się TERAZ."
        if mode == "camera":
            return "Widzisz Bartka przez kamerę."
        return ""
    except Exception as exc:
        logger.debug("snapshot: screen failed: %s", exc)
        return ""


def _condition_pl(condition: str) -> str:
    return {
        "clear": "bezchmurnie",
        "mostly_clear": "prawie bezchmurnie",
        "partly_cloudy": "częściowe zachmurzenie",
        "cloudy": "pochmurno",
        "fog": "mgła",
        "drizzle": "mżawka",
        "rain": "deszcz",
        "snow": "śnieg",
        "storm": "burza",
    }.get(condition, condition or "?")
