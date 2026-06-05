"""Ritual generation from SDT psychological needs.

Rituals are suggested daily patterns generated dynamically — no scheduler,
no timers. When a need drops, the ritual that addresses it surfaces.
This replaces the old daily-task / nudge system.

Usage:
    engine = RitualEngine(catalog_dir=catalog_dir)
    rituals = engine.suggest(needs)  # list[RitualEntry] for today
    await engine.complete(ritual_id, db_path)  # marks done + emits event
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.progression.catalog import RitualEntry, load_rituals
from backend.progression.state import get_active_rituals, set_active_rituals
from backend.soul.events import EventBus, RitualCompleted, bus as _global_bus
from backend.soul.models import Needs

logger = logging.getLogger(__name__)

_MAX_SUGGESTED = 3


class RitualEngine:
    """Suggests rituals from the catalog based on current SDT needs."""

    def __init__(
        self,
        catalog_dir: Path | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._catalog = load_rituals(catalog_dir)
        self._bus = event_bus or _global_bus

    def suggest(self, needs: Needs) -> list[RitualEntry]:
        """Return up to _MAX_SUGGESTED rituals appropriate for the current needs."""
        needs_map = {
            "relatedness": needs.relatedness,
            "competence": needs.competence,
            "autonomy": needs.autonomy,
        }
        candidates = []
        for entry in self._catalog:
            need_value = needs_map.get(entry.need_trigger, 1.0)
            # Ritual activates when the need is *below* its trigger threshold
            if need_value < entry.min_need_deficit:
                deficit = entry.min_need_deficit - need_value
                candidates.append((deficit, entry))

        # Sort by how severe the deficit is — most urgent first
        candidates.sort(key=lambda t: t[0], reverse=True)
        return [entry for _, entry in candidates[:_MAX_SUGGESTED]]

    async def complete(
        self,
        ritual_id: str,
        db_path: Path | None = None,
    ) -> bool:
        """Mark a ritual as completed today and emit RitualCompleted."""
        rituals = await get_active_rituals(db_path)
        for r in rituals:
            if r.get("id") == ritual_id:
                r["completed_today"] = True
                await set_active_rituals(rituals, db_path)
                await self._bus.emit(RitualCompleted(task_id=ritual_id))
                logger.info("Ritual completed: %s", ritual_id)
                return True

        # Not in active list yet — add and complete
        rituals.append({"id": ritual_id, "completed_today": True})
        await set_active_rituals(rituals, db_path)
        await self._bus.emit(RitualCompleted(task_id=ritual_id))
        return True

    async def sync_to_db(
        self,
        needs: Needs,
        db_path: Path | None = None,
    ) -> list[dict]:
        """Regenerate today's ritual list in the DB from current needs."""
        suggested = self.suggest(needs)
        existing = await get_active_rituals(db_path)
        existing_ids = {r["id"] for r in existing}

        new_list = list(existing)
        for entry in suggested:
            if entry.id not in existing_ids:
                new_list.append({"id": entry.id, "kind": entry.kind, "completed_today": False})

        await set_active_rituals(new_list, db_path)
        return new_list
