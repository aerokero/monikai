"""Context Assembler — the single compilation point for the system prompt.

Called at session reconnect. Assembles all soul-layer context into one string.

Sections (in order):
  1. CHARACTER   — character.md identity
  2. WORLD       — live time/weather/device snapshot
  3. OPERATIONAL — tools, rules, safety (passed in by caller)
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Assembles the full system prompt from all soul-layer sources."""

    async def assemble(
        self,
        character_prompt: str,
        operational_prompt: str,
        db_path: Path | None = None,
    ) -> str:
        parts: list[str] = []

        if character_prompt:
            parts.append(character_prompt.strip())

        world = await self._world_block(db_path)
        if world:
            parts.append(world)

        if operational_prompt:
            parts.append(operational_prompt.strip())

        return "\n\n".join(parts)

    async def _world_block(self, db_path: Path | None) -> str:
        """Live world snapshot (time, weather, gap, Spotify, screen).
        Supersedes the bare time-context block."""
        try:
            from backend.soul.world_snapshot import build_snapshot
            return await build_snapshot(db_path)
        except Exception as exc:
            logger.debug("Assembler: world snapshot failed: %s", exc)
            # Degrade to bare time context rather than losing time awareness.
            try:
                from backend.soul.time_engine.engine import TimeEngine
                return TimeEngine().format_context()
            except Exception:
                return ""
