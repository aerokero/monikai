"""Context Assembler — the single compilation point for the system prompt.

Called at session reconnect. Assembles all soul-layer context into one string.

Sections (in order):
  1. CHARACTER   — character.md identity
  2. TIME        — current time-of-day context
  3. MEMORY      — ambient memory snippets (recent STM + high-importance LTM)
  4. PROGRESSION — active goals / rituals (stub)
  5. OPERATIONAL — tools, rules, safety (passed in by caller)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.soul.memory import store

logger = logging.getLogger(__name__)

_MEMORY_STM_LIMIT = 6
_MEMORY_LTM_LIMIT = 4
_MEMORY_LTM_MIN_IMPORTANCE = 7.0


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

        time_ctx = self._time_context_block()
        if time_ctx:
            parts.append(time_ctx)

        memory = await self._memory_block(db_path)
        if memory:
            parts.append(memory)

        progression = await self._progression_block(db_path)
        if progression:
            parts.append(progression)

        if operational_prompt:
            parts.append(operational_prompt.strip())

        return "\n\n".join(parts)

    def _time_context_block(self) -> str:
        try:
            from backend.soul.time_engine.engine import TimeEngine
            te = TimeEngine()
            return te.format_context()
        except Exception as exc:
            logger.debug("Assembler: time context failed: %s", exc)
            return ""

    async def _memory_block(self, db_path: Path | None) -> str:
        try:
            stm_entries = await store.list_recent(
                limit=_MEMORY_STM_LIMIT, types=["stm"], db_path=db_path
            )
            ltm_entries = await store.list_recent(
                limit=_MEMORY_LTM_LIMIT * 3,
                types=["episodic", "semantic"],
                db_path=db_path,
            )
            ltm_top = sorted(
                [e for e in ltm_entries if e.importance >= _MEMORY_LTM_MIN_IMPORTANCE],
                key=lambda e: e.importance,
                reverse=True,
            )[:_MEMORY_LTM_LIMIT]

            all_entries = stm_entries + ltm_top
            if not all_entries:
                return ""

            lines = [
                "**Kontekst pamięci (z poprzednich sesji):**",
                "Poniższe wpisy to wspomnienia — fakty i epizody z przeszłości, NIE opis tego co widzisz teraz na ekranie ani przez kamerę.",
            ]
            for e in all_entries:
                tag_str = ", ".join(e.tags) if e.tags else ""
                suffix = f" [{tag_str}]" if tag_str else ""
                lines.append(f"- [{e.type}] {e.content}{suffix}")
            lines.append("Używaj tych wspomnień naturalnie w rozmowie — nie mylić z aktualnym obrazem.")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Assembler: memory block failed: %s", exc)
            return ""

    async def _progression_block(self, db_path: Path | None) -> str:
        try:
            from backend.soul.db import get_db
            async with get_db(db_path) as conn:
                cursor = await conn.execute(
                    "SELECT key, value FROM progression_state WHERE key IN "
                    "('active_goals', 'active_rituals', 'active_anniversaries')"
                )
                rows = await cursor.fetchall()
            if not rows:
                return ""

            import json
            lines = ["**Aktywny kontekst relacji:**"]
            for row in rows:
                try:
                    data = json.loads(row["value"])
                    if data:
                        lines.append(f"- {row['key']}: {data}")
                except Exception:
                    pass

            return "\n".join(lines) if len(lines) > 1 else ""
        except Exception as exc:
            logger.debug("Assembler: progression block failed: %s", exc)
            return ""


def _file_age_hours(path: Path) -> float:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
