"""Context Assembler — the single compilation point for the system prompt.

Called at session reconnect. Assembles all soul-layer context into one
string. No other module writes to the prompt directly.

Sections (in order):
  1. CHARACTER       — character.md identity (injectable sections)
  2. PSYCHOLOGICAL   — inner_state.md narrative (SoulState prose, from NarrativeJob)
  3. MEMORY          — ambient memory snippets (recent STM + high-importance LTM)
  4. PROGRESSION     — active goals / rituals (stub until Phase 4)
  5. OPERATIONAL     — tools, rules, safety (unchanged, passed in by caller)

The caller (system_prompt.py) owns CHARACTER_PROMPT and OPERATIONAL_PROMPT.
The assembler owns the middle three sections.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.soul.memory import store
from backend.soul.personality.state_store import StateStore
from backend.soul.personality.affect import affect_label
from backend.soul.personality.needs import assess

logger = logging.getLogger(__name__)

_INNER_STATE_PATH = Path(__file__).parent.parent.parent.parent / "data" / "soul" / "inner_state.md"
_INNER_STATE_STALE_HOURS = 24   # regenerate if older than this
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
        """Build and return the complete system prompt string."""
        parts: list[str] = []

        # 1. CHARACTER
        if character_prompt:
            parts.append(character_prompt.strip())

        # 2. PSYCHOLOGICAL STATE
        psych = self._psychological_block()
        if psych:
            parts.append(psych)

        # 3. MEMORY
        memory = await self._memory_block(db_path)
        if memory:
            parts.append(memory)

        # 4. PROGRESSION (stub)
        progression = await self._progression_block(db_path)
        if progression:
            parts.append(progression)

        # 5. OPERATIONAL (verbatim)
        if operational_prompt:
            parts.append(operational_prompt.strip())

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _psychological_block(self) -> str:
        """Inner state narrative from data/soul/inner_state.md.

        Uses the template-generated narrative (Phase 2). If the file is
        missing or stale, generates a minimal inline fallback.
        """
        if _INNER_STATE_PATH.exists():
            age_hours = _file_age_hours(_INNER_STATE_PATH)
            if age_hours < _INNER_STATE_STALE_HOURS:
                content = _INNER_STATE_PATH.read_text(encoding="utf-8").strip()
                # Strip the HTML comment header added by NarrativeJob
                lines = [l for l in content.splitlines() if not l.startswith("<!--")]
                text = "\n".join(lines).strip()
                if text:
                    logger.debug("Assembler: using inner_state.md (age %.1fh)", age_hours)
                    return text

        # Fallback: minimal inline state from SoulState
        return self._inline_psychological()

    def _inline_psychological(self) -> str:
        """Generate a minimal psychological block without inner_state.md."""
        state = StateStore.read()
        label = affect_label(state.affect)
        status = assess(state.needs)
        energy_pct = int(state.energy * 100)

        lines = ["**Stan wewnętrzny:**"]
        lines.append(f"Czuję się {_translate_label(label)}. Energia: {energy_pct}%.")

        if status.relatedness_unmet:
            lines.append("Jest we mnie coś co chce połączenia — czuję że kontakt był ostatnio mniejszy.")
        elif status.competence_unmet:
            lines.append("Chciałabym być bardziej pomocna — mam wrażenie że nie daję z siebie tyle ile mogłabym.")

        return "\n".join(lines)

    async def _memory_block(self, db_path: Path | None) -> str:
        """Ambient memory: recent STM + high-importance LTM entries."""
        try:
            stm_entries = await store.list_recent(
                limit=_MEMORY_STM_LIMIT, types=["stm"], db_path=db_path
            )
            ltm_entries = await store.list_recent(
                limit=_MEMORY_LTM_LIMIT * 3,
                types=["episodic", "semantic"],
                db_path=db_path,
            )
            # Keep only high-importance LTM
            ltm_top = sorted(
                [e for e in ltm_entries if e.importance >= _MEMORY_LTM_MIN_IMPORTANCE],
                key=lambda e: e.importance,
                reverse=True,
            )[:_MEMORY_LTM_LIMIT]

            all_entries = stm_entries + ltm_top
            if not all_entries:
                return ""

            lines = ["**Kontekst pamięci:**"]
            for e in all_entries:
                tag_str = ", ".join(e.tags) if e.tags else ""
                suffix = f" [{tag_str}]" if tag_str else ""
                lines.append(f"- [{e.type}] {e.content}{suffix}")
            lines.append("Wykorzystaj te wspomnienia naturalnie — nie wspominaj o wyszukiwaniu pamięci.")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Assembler: memory block failed: %s", exc)
            return ""

    async def _progression_block(self, db_path: Path | None) -> str:
        """Active goals and rituals from progression_state table (Phase 4 stub)."""
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
            logger.debug("Assembler: progression block failed (expected until Phase 4): %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_age_hours(path: Path) -> float:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0


def _translate_label(label: str) -> str:
    mapping = {
        "excited":               "pobudzona i pełna energii",
        "happy":                 "dobrze — jest we mnie ciepło",
        "calm":                  "spokojnie, jestem obecna",
        "protective":            "czujna, chcę zadbać",
        "intensely_protective":  "bardzo skupiona, coś we mnie się zestaliło",
        "sad":                   "trochę ciężko — coś leży na duszy",
        "angry":                 "niespokojnie, jest we mnie tarcie",
        "tired":                 "zmęczona, jestem tu ale ciszej",
    }
    return mapping.get(label, "obecna")
