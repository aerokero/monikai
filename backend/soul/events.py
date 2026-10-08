"""Typed Event Bus — the primary integration mechanism between subsystems.

In-process pub/sub. Subsystems subscribe to event types; they never import
each other. Adding a feature = subscribing to events, not modifying existing
modules.

Cross-process events (main ↔ background worker) go through the `events`
table in monika.db — see backend/soul/db.py.

Usage:
    from backend.soul.events import bus, ActivityStarted

    # subscribe
    bus.subscribe(ActivityStarted, my_handler)

    # emit (from async context)
    await bus.emit(ActivityStarted(kind="chat", context="hi"))
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseEvent(BaseModel):
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class CompactionDone(BaseEvent):
    entries_kept: int
    entries_discarded: int


class DiscoveryMade(BaseEvent):
    discovery_id: str
    title: str


class AnniversaryObserved(BaseEvent):
    label: str
    days_elapsed: int


class ActivityStarted(BaseEvent):
    kind: str
    context: str


class LongGapDetected(BaseEvent):
    hours_since_last: float


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """Async in-process pub/sub bus.

    Subscription is synchronous (safe from any context).
    Emit is async: all handlers run concurrently via asyncio.gather.
    Handler exceptions are caught and logged — one bad handler doesn't
    kill the others.
    """

    def __init__(self) -> None:
        self._subs: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._subs[event_type].append(handler)
        logger.debug("Subscribed %s to %s", handler.__qualname__, event_type.__name__)

    def unsubscribe(self, event_type: type, handler: EventHandler) -> None:
        try:
            self._subs[event_type].remove(handler)
        except ValueError:
            pass

    async def emit(self, event: BaseEvent) -> None:
        handlers = self._subs.get(type(event), [])
        if not handlers:
            return
        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler %s raised on %s: %s",
                    handlers[i].__qualname__,
                    type(event).__name__,
                    result,
                    exc_info=result,
                )
        logger.debug("Emitted %s to %d handler(s)", type(event).__name__, len(handlers))


# Module-level singleton — the single shared bus for the process.
bus = EventBus()
