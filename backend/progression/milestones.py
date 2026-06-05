"""Milestone detection engine.

Milestones are permanent relationship markers. A MemoryStored event with
importance >= 8 is a milestone *candidate*. Very high importance (>= 9)
is auto-confirmed. 8-9 range is flagged for later review (Phase 5+).

Emits RelationshipDeepened when a milestone is confirmed.

Each milestone permanently changes what's possible — new stories unlock,
her register shifts, her agenda may reference it. Those effects are
registered by other subsystems listening to RelationshipDeepened.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.progression.state import add_milestone, get_milestones
from backend.soul.events import (
    EventBus,
    MemoryStored,
    RelationshipDeepened,
    bus as _global_bus,
)

logger = logging.getLogger(__name__)

_AUTO_CONFIRM_THRESHOLD = 9.0   # importance >= this → auto-confirm
_CANDIDATE_THRESHOLD = 8.0      # importance >= this → candidate (flagged)


class MilestoneEngine:
    """Listens for important memories and promotes them to milestones."""

    def __init__(
        self,
        db_path: Path | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db_path = db_path
        self._bus = event_bus or _global_bus

    async def start(self) -> None:
        self._bus.subscribe(MemoryStored, self._on_memory_stored)
        logger.info("MilestoneEngine: started")

    async def stop(self) -> None:
        self._bus.unsubscribe(MemoryStored, self._on_memory_stored)

    async def _on_memory_stored(self, event: MemoryStored) -> None:
        if event.importance < _CANDIDATE_THRESHOLD:
            return

        milestone_id = f"milestone_mem_{event.entry_id[:12]}"
        existing = await get_milestones(self._db_path)

        if any(m["id"] == milestone_id for m in existing):
            return

        if event.importance >= _AUTO_CONFIRM_THRESHOLD:
            added = await add_milestone(
                milestone_id=milestone_id,
                effect=f"Memory {event.entry_id!r} confirmed as milestone (importance={event.importance:.1f})",
                db_path=self._db_path,
            )
            if added:
                logger.info("Milestone confirmed: %s (importance=%.1f)", milestone_id, event.importance)
                await self._bus.emit(RelationshipDeepened(milestone_id=milestone_id))
        else:
            # 8 ≤ importance < 9 — flag for review without confirming
            added = await add_milestone(
                milestone_id=milestone_id,
                effect=f"Candidate milestone (importance={event.importance:.1f}) — pending review",
                db_path=self._db_path,
            )
            if added:
                logger.info("Milestone candidate flagged: %s (importance=%.1f)", milestone_id, event.importance)

    async def confirm_milestone(self, milestone_id: str) -> bool:
        """Manually confirm a pending candidate milestone."""
        milestones = await get_milestones(self._db_path)
        for m in milestones:
            if m["id"] == milestone_id and "pending review" in m.get("effect", ""):
                m["effect"] = m["effect"].replace(" — pending review", " — confirmed")
                from backend.progression.state import set_
                await set_("milestones", milestones, self._db_path)
                await self._bus.emit(RelationshipDeepened(milestone_id=milestone_id))
                return True
        return False
