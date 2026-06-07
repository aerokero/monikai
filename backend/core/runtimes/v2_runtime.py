"""v2 Soul Engine runtime integration.

Module-level singleton (appropriate here — it's a process-scoped resource,
same as `audio_loop` and `personality_system` in server.py).

Initialize once at server startup with `initialize()`.
Access anywhere with `get()`.

Graceful degradation: if initialization fails, `get()` returns None
and callers fall back to v1 behaviour unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from pathlib import Path
import time
from typing import Optional
import urllib.request

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
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
    """Return the active V2Runtime, or None if not yet initialized."""
    return _instance


async def initialize(db_path: Path | None = None) -> "V2Runtime":
    """Create and return the V2Runtime singleton. Safe to call once at startup."""
    global _instance
    _instance = await V2Runtime._create(db_path or _DB_PATH)
    return _instance


async def shutdown() -> None:
    """Shut down the singleton cleanly (call at server shutdown)."""
    global _instance
    if _instance is not None:
        await _instance._shutdown()
        _instance = None


# ---------------------------------------------------------------------------
# V2Runtime
# ---------------------------------------------------------------------------

class V2Runtime:
    """Owns all v2 Soul Engine components for the lifetime of the server process."""

    def __init__(
        self,
        db_path: Path,
        personality,    # PersonalityEngine
        discovery,      # DiscoveryEngine
        milestone,      # MilestoneEngine
        time_engine=None,    # TimeEngine
        mood_tracker=None,   # UserMoodTracker
        cached_prompt: str = "",
    ) -> None:
        self._db_path = db_path
        self._personality = personality
        self._discovery = discovery
        self._milestone = milestone
        self._time_engine = time_engine
        self._mood_tracker = mood_tracker
        self._cached_prompt = cached_prompt
        self._session_turns: deque[str] = deque(maxlen=8)
        from backend.soul.agenda import AgendaManager
        self._agenda = AgendaManager()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def _create(cls, db_path: Path) -> "V2Runtime":
        from backend.soul.db import init_db
        from backend.soul.personality.engine import PersonalityEngine
        from backend.progression.discoveries import DiscoveryEngine
        from backend.progression.milestones import MilestoneEngine
        from backend.soul.time_engine.engine import TimeEngine
        from backend.soul.user_model import UserMoodTracker

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        await init_db(db_path)
        logger.info("v2: monika.db initialized at %s", db_path)

        personality = PersonalityEngine.load()
        discovery = DiscoveryEngine(db_path=db_path)
        milestone = MilestoneEngine(db_path=db_path)
        time_engine = TimeEngine()
        mood_tracker = UserMoodTracker.load()

        await discovery.start()
        await milestone.start()

        # Initialize first interaction timestamp if not present
        try:
            from backend.progression.state import get_first_interaction_ts
            await get_first_interaction_ts(db_path)
        except Exception as e:
            logger.warning("v2: failed to initialize first_interaction_ts: %s", e)

        # Check for gap since last session; apply needs decay if needed
        gap = await time_engine.check_gap(db_path)
        if gap.needs_decay_days > 0:
            personality.apply_daily_decay(days_elapsed=gap.needs_decay_days)

        # Check for anniversaries (silent — events are emitted to bus)
        await time_engine.check_anniversaries(db_path)

        runtime = cls(
            db_path=db_path,
            personality=personality,
            discovery=discovery,
            milestone=milestone,
            time_engine=time_engine,
            mood_tracker=mood_tracker,
        )

        # Generate fresh inner_state.md before assembling the prompt
        try:
            from backend.worker.narrative_job import NarrativeJob
            await NarrativeJob().run(db_path=db_path, mood_tracker=mood_tracker)
        except Exception as e:
            logger.warning("v2: NarrativeJob failed at startup: %s", e)

        runtime._cached_prompt = await runtime.refresh_prompt()
        logger.info("v2: runtime initialized (prompt=%d chars)", len(runtime._cached_prompt))
        return runtime

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    async def refresh_prompt(self) -> str:
        """Re-assemble and cache the system prompt. Call at each reconnect."""
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
    # Per-turn processing
    # ------------------------------------------------------------------

    async def process_turn(
        self,
        user_text: str,
        monika_text: str = "",
    ) -> str:
        """Update personality from this turn. Return cognition monologue message."""
        try:
            from backend.llm.cognition import generate
            from backend.soul.personality.signals import extract
            from backend.soul.memory import store as mem_store

            signals = extract(user_text)

            # Track user mood signals
            if self._mood_tracker is not None:
                self._mood_tracker.observe(signals)
                self._mood_tracker.save()

            # Update personality engine (affect + needs)
            soul = self._personality.soul_state
            await self._personality.observe_turn(user_text, monika_text, reciprocity=None)
            self._personality.save()

            # Pull recent STM entries for cognition context
            stm_entries: list = []
            try:
                stm_entries = await mem_store.list_recent(
                    limit=4, types=["stm"], db_path=self._db_path
                )
            except Exception as e:
                logger.debug("v2: stm fetch failed: %s", e)

            # Get mood summary
            mood_summary: str | None = None
            if self._mood_tracker is not None:
                try:
                    mood_summary = self._mood_tracker.weekly_summary() or None
                except Exception:
                    pass

            # Agenda: age existing items, extract new ones from this turn
            self._agenda.age()
            new_agenda = self._agenda.extract_from_turn(user_text, signals)

            # Build cognition with full context
            session_turns = list(self._session_turns)
            cog = await generate(
                user_text,
                soul,
                signals=signals,
                stm_entries=stm_entries or None,
                session_turns=session_turns or None,
                mood_summary=mood_summary,
                agenda=self._agenda.active() or None,
            )

            # Add new agenda items after generating cognition (they go into next turn)
            self._agenda.add_items(new_agenda)

            # Record this turn in session buffer
            if user_text.strip():
                self._session_turns.append(user_text.strip())

            # Record last interaction timestamp for gap detection
            if self._time_engine is not None:
                await self._time_engine.record_interaction(self._db_path)

            # Emit personality status update to frontend
            try:
                from backend.core.routers.frontend_router import schedule_emit_to_frontend
                status_payload = await self.get_status_payload()
                schedule_emit_to_frontend("personality_status", status_payload)
            except Exception as e:
                logger.warning("v2: failed to emit personality_status after process_turn: %s", e)

            return cog.as_message()
        except Exception as exc:
            logger.warning("v2: process_turn failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    @property
    def soul_state(self):
        return self._personality.soul_state

    @property
    def needs_status(self):
        return self._personality.needs_status

    @property
    def time_engine(self):
        return self._time_engine

    @property
    def mood_tracker(self):
        return self._mood_tracker

    async def generate_briefing(self, language: str = "pl") -> str:
        """Generate today's daily briefing using all available context."""
        try:
            from backend.llm.briefing import generate as gen_briefing
            return await gen_briefing(
                soul_state=self._personality.soul_state,
                time_engine=self._time_engine,
                mood_tracker=self._mood_tracker,
                db_path=self._db_path,
                language=language,
            )
        except Exception as exc:
            logger.warning("v2: briefing generation failed: %s", exc)
            return ""

    async def get_status_payload(self) -> dict:
        from backend.soul.personality.affect import affect_label
        from backend.progression.state import get_bond_state, get_first_interaction_ts
        from datetime import datetime, timezone

        soul = self.soul_state
        mood = affect_label(soul.affect)
        bond = await get_bond_state(self._db_path)
        affection = bond.get("closeness", 0.0)

        first_ts_str = await get_first_interaction_ts(self._db_path)
        try:
            first_dt = datetime.fromisoformat(first_ts_str.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            days = (now_dt.date() - first_dt.date()).days + 1
            if days < 1:
                days = 1
        except Exception:
            days = 1

        weather = await get_cached_weather()

        score = affection / 10.0
        full = int(score)
        hearts = "❤️" * full + "🤍" * (10 - full)

        needs = {
            "relatedness": round(soul.needs.relatedness * 100),
            "autonomy": round(soul.needs.autonomy * 100),
            "competence": round(soul.needs.competence * 100),
        }

        return {
            "v2": True,
            "mood": mood,
            "affection": affection,
            "affection_hearts": f"{hearts} ({score:.1f}/10)",
            "relationship_days": days,
            "weather": weather,
            "needs": needs,
        }

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def _shutdown(self) -> None:
        try:
            await self._discovery.stop()
            await self._milestone.stop()
            self._personality.apply_session_end()
            self._personality.save()
            logger.info("v2: runtime shut down cleanly")
        except Exception as exc:
            logger.warning("v2: shutdown error: %s", exc)
