"""v2 runtime — lightweight soul layer.

Owns: TimeEngine, AgendaManager, session_turns buffer, memory access.
Removed: PersonalityEngine, UserMoodTracker, MilestoneEngine, DiscoveryEngine.

Module-level singleton — initialize once at startup with initialize(),
access anywhere with get().
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import time
from typing import Optional
import urllib.request

from ..config import DATA_DIR as _DATA_DIR

logger = logging.getLogger(__name__)

_DB_PATH = _DATA_DIR / "monika.db"

_weather_cache = None
_weather_cache_ts = 0.0
_weather_cache_lock = asyncio.Lock()
_WEATHER_CACHE_TTL_SECONDS = 1800


def _weather_condition_from_code(code: int) -> str:
    if code == 0:
        return "clear"
    if code == 1:
        return "mostly_clear"
    if code == 2:
        return "partly_cloudy"
    if code == 3:
        return "cloudy"
    if code in {45, 48}:
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or 85 <= code <= 86:
        return "snow"
    if 95 <= code <= 99:
        return "storm"
    return "cloudy"


async def get_cached_weather() -> dict | None:
    global _weather_cache, _weather_cache_ts

    now = time.time()
    if _weather_cache_ts and now - _weather_cache_ts <= _WEATHER_CACHE_TTL_SECONDS:
        return _weather_cache

    async with _weather_cache_lock:
        now = time.time()
        if _weather_cache_ts and now - _weather_cache_ts <= _WEATHER_CACHE_TTL_SECONDS:
            return _weather_cache

        def fetch():
            try:
                with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as url:
                    loc_data = json.loads(url.read().decode("utf-8"))
                if loc_data.get("status") != "success":
                    return None
                lat = loc_data.get("lat")
                lon = loc_data.get("lon")
                city = loc_data.get("city", "")
                if lat is None or lon is None:
                    return None

                w_url = (
                    f"https://api.open-meteo.com/v1/forecast"
                    f"?latitude={lat}&longitude={lon}"
                    "&current_weather=true"
                    "&current=temperature_2m,weather_code"
                    "&timezone=auto"
                )
                with urllib.request.urlopen(w_url, timeout=6) as url:
                    w_data = json.loads(url.read().decode("utf-8"))
                current = w_data.get("current", {}) or {}
                current_weather = w_data.get("current_weather", {}) or {}
                code = int(current.get("weather_code", current_weather.get("weathercode", -1)))
                temp = current.get("temperature_2m", current_weather.get("temperature"))
                return {
                    "code": code,
                    "condition": _weather_condition_from_code(code),
                    "temp": temp,
                    "city": city,
                }
            except Exception as e:
                logger.warning("Error fetching weather: %s", e)
                return None

        try:
            loop = asyncio.get_running_loop()
            _weather_cache = await loop.run_in_executor(None, fetch)
            _weather_cache_ts = time.time()
        except Exception as e:
            _weather_cache = None
            _weather_cache_ts = time.time()
            logger.warning("Failed to fetch cached weather: %s", e)

    return _weather_cache


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional["V2Runtime"] = None


def get() -> Optional["V2Runtime"]:
    return _instance


async def initialize(db_path: Path | None = None) -> "V2Runtime":
    global _instance
    _instance = await V2Runtime._create(db_path or _DB_PATH)
    return _instance


async def shutdown() -> None:
    global _instance
    if _instance is not None:
        await _instance._shutdown()
        _instance = None


# ---------------------------------------------------------------------------
# V2Runtime
# ---------------------------------------------------------------------------

class V2Runtime:
    """Lightweight runtime for prompt, time and background session digestion."""

    def __init__(
        self,
        db_path: Path,
        time_engine=None,
        cached_prompt: str = "",
    ) -> None:
        self._db_path = db_path
        self._time_engine = time_engine
        self._cached_prompt = cached_prompt
        self._digest_task: asyncio.Task | None = None

    @classmethod
    async def _create(cls, db_path: Path) -> "V2Runtime":
        from backend.soul.db import init_db
        from backend.soul.time_engine.engine import TimeEngine

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        await init_db(db_path)
        logger.info("v2: monika.db initialized at %s", db_path)

        time_engine = TimeEngine()
        await time_engine.check_gap(db_path)
        await time_engine.check_anniversaries(db_path)

        runtime = cls(db_path=db_path, time_engine=time_engine)
        runtime._cached_prompt = await runtime.refresh_prompt()
        runtime._digest_task = asyncio.create_task(runtime._digest_loop())
        logger.info("v2: runtime initialized (prompt=%d chars)", len(runtime._cached_prompt))
        return runtime

    # ------------------------------------------------------------------
    # Background digestion — sessions become memory
    # ------------------------------------------------------------------

    _DIGEST_SCAN_INTERVAL_S = 20 * 60

    async def _digest_loop(self) -> None:
        """Periodically digest finished sessions into long-term memory.

        First scan runs shortly after startup (catch-up for sessions that
        ended while the app was off), then every _DIGEST_SCAN_INTERVAL_S.
        """
        await asyncio.sleep(90)  # let startup settle before touching Ollama
        while True:
            try:
                from backend.soul.memory.digest import scan_and_digest

                current_id = None
                try:
                    from backend.core import server as _srv
                    sm = getattr(_srv.audio_loop, "session_manager", None)
                    if sm is not None:
                        current_id = sm.get_current_session_id()
                except Exception:
                    pass

                digested = await scan_and_digest(
                    db_path=self._db_path, current_session_id=current_id
                )
                if digested:
                    await self.refresh_prompt()

                try:
                    from backend.soul.proactivity import maybe_poke
                    await maybe_poke(db_path=self._db_path)
                except Exception as exc:
                    logger.warning("v2: proactivity error: %s", exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("v2: digest loop error: %s", exc)
            await asyncio.sleep(self._DIGEST_SCAN_INTERVAL_S)

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    async def refresh_prompt(self) -> str:
        try:
            from backend.core.system_prompt import assemble_prompt
            self._cached_prompt = await assemble_prompt(db_path=self._db_path)
        except Exception as exc:
            logger.warning("v2: prompt assembly failed, keeping cached: %s", exc)
        return self._cached_prompt

    @property
    def cached_prompt(self) -> str:
        return self._cached_prompt

    # ------------------------------------------------------------------
    # Per-turn bookkeeping
    # ------------------------------------------------------------------

    async def observe_turn(self) -> None:
        """Record interaction metadata without adding context to the model."""
        try:
            if self._time_engine is not None:
                await self._time_engine.record_interaction(self._db_path)

            try:
                from backend.core.routers.frontend_router import schedule_emit_to_frontend
                status_payload = await self.get_status_payload()
                schedule_emit_to_frontend("personality_status", status_payload)
            except Exception as e:
                logger.debug("v2: failed to emit personality_status: %s", e)

        except Exception as exc:
            logger.warning("v2: observe_turn failed: %s", exc)

    # ------------------------------------------------------------------
    # State / status
    # ------------------------------------------------------------------

    @property
    def time_engine(self):
        return self._time_engine

    async def generate_briefing(self, language: str = "pl") -> str:
        """Stub — will be replaced by local model call."""
        return ""

    async def get_status_payload(self) -> dict:
        """Honest status: only data the system actually has. No synthetic
        mood/needs numbers — absent is better than fake."""
        weather = await get_cached_weather()

        memory_counts: dict[str, int] = {}
        try:
            from backend.soul.db import get_db
            async with get_db(self._db_path) as conn:
                cursor = await conn.execute(
                    "SELECT type, COUNT(*) AS n FROM memory_entries GROUP BY type"
                )
                rows = await cursor.fetchall()
            memory_counts = {r["type"]: r["n"] for r in rows}
        except Exception as exc:
            logger.debug("v2: memory counts failed: %s", exc)

        # Real energy: time-of-day hint from the TimeEngine (local clock).
        energy = None
        try:
            if self._time_engine is not None:
                energy = self._time_engine.get_context().energy_hint
        except Exception:
            pass

        return {
            "v2": True,
            "mood": None,
            "energy": energy,
            "weather": weather,
            "memory": {
                "semantic": memory_counts.get("semantic", 0),
                "episodic": memory_counts.get("episodic", 0),
                "stm": memory_counts.get("stm", 0),
                "total": sum(memory_counts.values()),
            },
        }

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def _shutdown(self) -> None:
        try:
            if self._digest_task is not None:
                self._digest_task.cancel()
                try:
                    await self._digest_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._digest_task = None
            from backend.llm import ollama_client
            await ollama_client.shutdown()
            logger.info("v2: runtime shut down cleanly")
        except Exception as exc:
            logger.warning("v2: shutdown error: %s", exc)
