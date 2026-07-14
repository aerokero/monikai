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
_MEMORY_RECENT_LTM_LIMIT = 8
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

        world = await self._world_block(db_path)
        if world:
            parts.append(world)

        inner = self._inner_state_block()
        if inner:
            parts.append(inner)

        memory = await self._memory_block(db_path)
        if memory:
            parts.append(memory)

        user_state = self._user_state_block()
        if user_state:
            parts.append(user_state)

        agenda = await self._agenda_block(db_path)
        if agenda:
            parts.append(agenda)

        progression = await self._progression_block(db_path)
        if progression:
            parts.append(progression)

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

    async def _memory_block(self, db_path: Path | None) -> str:
        try:
            stm_entries = await store.list_recent(
                limit=_MEMORY_STM_LIMIT, types=["stm"], db_path=db_path
            )
            # Fresh memories from the last sessions (whatever the digest kept)
            # plus the all-time most important ones — so both "wczoraj" and
            # "to co naprawdę ważne" are present at reconnect.
            recent_ltm = await store.list_recent(
                limit=_MEMORY_RECENT_LTM_LIMIT,
                types=["episodic", "semantic"],
                db_path=db_path,
            )
            pool = await store.list_recent(
                limit=200, types=["episodic", "semantic"], db_path=db_path
            )
            seen_ids = {e.id for e in recent_ltm}
            ltm_top = sorted(
                [e for e in pool
                 if e.importance >= _MEMORY_LTM_MIN_IMPORTANCE and e.id not in seen_ids],
                key=lambda e: e.importance,
                reverse=True,
            )[:_MEMORY_LTM_LIMIT]

            all_entries = stm_entries + recent_ltm + ltm_top
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

    def _inner_state_block(self) -> str:
        """Monika's first-person state, produced by the last session digest."""
        try:
            path = Path(__file__).parent.parent.parent.parent / "data" / "soul" / "inner_state.md"
            if not path.exists() or _file_age_hours(path) > 7 * 24:
                return ""
            text = "\n".join(
                ln for ln in path.read_text(encoding="utf-8").splitlines()
                if not ln.strip().startswith("<!--")
            ).strip()
            if not text:
                return ""
            age_h = _file_age_hours(path)
            when = "po ostatniej rozmowie" if age_h < 24 else f"sprzed ~{int(age_h // 24)} dni"
            return (
                f"**Twój stan wewnętrzny ({when}, zapisany Twoimi słowami):**\n"
                f"{text}\n"
                "To jest punkt wyjścia, nie skrypt — od tamtej pory mogło się w Tobie coś przesunąć."
            )
        except Exception as exc:
            logger.debug("Assembler: inner_state block failed: %s", exc)
            return ""

    def _user_state_block(self) -> str:
        """Monika's latest read of the user, produced by the session digest."""
        try:
            path = Path(__file__).parent.parent.parent.parent / "data" / "soul" / "user_state.md"
            if not path.exists() or _file_age_hours(path) > 72:
                return ""
            text = "\n".join(
                ln for ln in path.read_text(encoding="utf-8").splitlines()
                if not ln.strip().startswith("<!--")
            ).strip()
            if not text:
                return ""
            return (
                "**Twój obraz Bartka z ostatniej rozmowy:**\n"
                f"{text}\n"
                "To Twoje rozumienie z niedawna — zweryfikuj je naturalnie, nie recytuj."
            )
        except Exception as exc:
            logger.debug("Assembler: user_state block failed: %s", exc)
            return ""

    async def _agenda_block(self, db_path: Path | None) -> str:
        """Open threads Monika wants to return to (from session digests)."""
        try:
            from backend.soul.memory.agenda_store import open_items
            items = await open_items(db_path=db_path)
            if not items:
                return ""
            lines = ["**Twoje niedomknięte wątki (masz je z własnej woli, wróć do nich gdy będzie naturalnie):**"]
            for it in items:
                lines.append(f"- {it['text']}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("Assembler: agenda block failed: %s", exc)
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
