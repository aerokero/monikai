"""v2 Soul Engine runtime integration.

Module-level singleton (appropriate here — it's a process-scoped resource,
same as `audio_loop` and `personality_system` in server.py).

Initialize once at server startup with `initialize()`.
Access anywhere with `get()`.

Graceful degradation: if initialization fails, `get()` returns None
and callers fall back to v1 behaviour unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DB_PATH = _DATA_DIR / "monika.db"

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
        cached_prompt: str = "",
    ) -> None:
        self._db_path = db_path
        self._personality = personality
        self._discovery = discovery
        self._milestone = milestone
        self._cached_prompt = cached_prompt

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def _create(cls, db_path: Path) -> "V2Runtime":
        from backend.soul.db import init_db
        from backend.soul.personality.engine import PersonalityEngine
        from backend.progression.discoveries import DiscoveryEngine
        from backend.progression.milestones import MilestoneEngine

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        await init_db(db_path)
        logger.info("v2: monika.db initialized at %s", db_path)

        personality = PersonalityEngine.load()
        discovery = DiscoveryEngine(db_path=db_path)
        milestone = MilestoneEngine(db_path=db_path)

        await discovery.start()
        await milestone.start()

        runtime = cls(
            db_path=db_path,
            personality=personality,
            discovery=discovery,
            milestone=milestone,
        )
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
            soul = self._personality.soul_state
            cog = await generate(user_text, soul)
            await self._personality.observe_turn(user_text, monika_text)
            self._personality.save()
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
