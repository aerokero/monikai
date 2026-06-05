"""Event-driven discovery unlock engine.

Subscribes to the Event Bus and checks every incoming event against the
discoveries catalog. When a trigger fires for the first time, the discovery
is unlocked silently and a DiscoveryMade event is emitted.

Usage:
    engine = DiscoveryEngine(db_path=db_path)
    await engine.start()   # subscribe to bus, load catalog
    # ... engine runs passively via event subscriptions
    await engine.stop()    # unsubscribe
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.progression.catalog import (
    DiscoveryEntry,
    load_discoveries,
    parse_trigger,
    trigger_matches,
)
from backend.progression.state import (
    get_turn_count,
    increment_turn_count,
    is_unlocked,
    unlock_discovery,
)
from backend.soul.events import (
    AnniversaryObserved,
    DiscoveryMade,
    EventBus,
    LongGapDetected,
    MemoryStored,
    RelationshipDeepened,
    RitualCompleted,
    StoryEnded,
    TurnCompleted,
    UserDisclosure,
    bus as _global_bus,
)

logger = logging.getLogger(__name__)


class DiscoveryEngine:
    """Listens on the Event Bus and unlocks discoveries from the catalog."""

    def __init__(
        self,
        db_path: Path | None = None,
        event_bus: EventBus | None = None,
        catalog_dir: Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._bus = event_bus or _global_bus
        self._catalog: list[DiscoveryEntry] = []
        self._catalog_dir = catalog_dir

    async def start(self) -> None:
        """Load catalog and subscribe to all relevant event types."""
        self._catalog = load_discoveries(self._catalog_dir)
        logger.info("DiscoveryEngine: loaded %d entries", len(self._catalog))

        self._bus.subscribe(TurnCompleted, self._on_turn)
        self._bus.subscribe(MemoryStored, self._on_memory_stored)
        self._bus.subscribe(UserDisclosure, self._on_user_disclosure)
        self._bus.subscribe(StoryEnded, self._on_story_ended)
        self._bus.subscribe(RelationshipDeepened, self._on_relationship_deepened)

    async def stop(self) -> None:
        """Unsubscribe all handlers."""
        self._bus.unsubscribe(TurnCompleted, self._on_turn)
        self._bus.unsubscribe(MemoryStored, self._on_memory_stored)
        self._bus.unsubscribe(UserDisclosure, self._on_user_disclosure)
        self._bus.unsubscribe(StoryEnded, self._on_story_ended)
        self._bus.unsubscribe(RelationshipDeepened, self._on_relationship_deepened)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_turn(self, event: TurnCompleted) -> None:
        count = await increment_turn_count(self._db_path)
        await self._check_all("TurnCompleted", {}, count=count)

    async def _on_memory_stored(self, event: MemoryStored) -> None:
        await self._check_all("MemoryStored", {
            "importance": event.importance,
            "type": event.type,
            "entry_id": event.entry_id,
        })

    async def _on_user_disclosure(self, event: UserDisclosure) -> None:
        await self._check_all("UserDisclosure", {
            "emotional_depth": event.emotional_depth,
            "topic": event.topic,
        })

    async def _on_story_ended(self, event: StoryEnded) -> None:
        await self._check_all("StoryEnded", {
            "story_id": event.story_id,
            "ending_id": event.ending_id,
        })

    async def _on_relationship_deepened(self, event: RelationshipDeepened) -> None:
        await self._check_all("RelationshipDeepened", {
            "milestone_id": event.milestone_id,
        })

    # ------------------------------------------------------------------
    # Core check logic
    # ------------------------------------------------------------------

    async def _check_all(
        self,
        event_name: str,
        payload: dict,
        count: int | None = None,
    ) -> None:
        for entry in self._catalog:
            if await is_unlocked(entry.id, self._db_path):
                continue

            fired = self._fires(entry.trigger, event_name, payload, count)
            if fired:
                newly_unlocked = await unlock_discovery(entry.id, self._db_path)
                if newly_unlocked:
                    logger.info("Discovery: %s — %s", entry.id, entry.title)
                    await self._bus.emit(DiscoveryMade(
                        discovery_id=entry.id,
                        title=entry.title,
                    ))

    def _fires(
        self,
        trigger: str,
        event_name: str,
        payload: dict,
        count: int | None,
    ) -> bool:
        t_name, condition = parse_trigger(trigger)

        # Counter-based trigger: count:N fires when turn_count >= N
        if t_name == "count":
            if event_name != "TurnCompleted" or count is None:
                return False
            try:
                return count >= int(condition or "1")
            except ValueError:
                return False

        return trigger_matches(trigger, event_name, payload)
