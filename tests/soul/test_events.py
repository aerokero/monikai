"""Smoke tests for the typed Event Bus."""

from __future__ import annotations

import asyncio

import pytest

from backend.soul.events import (
    EventBus,
    ActivityStarted,
    DiscoveryMade,
    LongGapDetected,
)


@pytest.mark.asyncio
async def test_subscribe_and_emit():
    bus = EventBus()
    received: list[ActivityStarted] = []

    async def handler(event: ActivityStarted) -> None:
        received.append(event)

    bus.subscribe(ActivityStarted, handler)
    await bus.emit(ActivityStarted(kind="s1", context="hi"))
    assert len(received) == 1
    assert received[0].kind == "s1"


@pytest.mark.asyncio
async def test_no_handlers_is_silent():
    bus = EventBus()
    # Should not raise even with no subscribers.
    await bus.emit(ActivityStarted(kind="s2", context="x"))


@pytest.mark.asyncio
async def test_multiple_event_types():
    bus = EventBus()
    turn_log: list = []
    memory_log: list = []

    async def on_turn(e: ActivityStarted) -> None:
        turn_log.append(e)

    async def on_memory(e: DiscoveryMade) -> None:
        memory_log.append(e)

    bus.subscribe(ActivityStarted, on_turn)
    bus.subscribe(DiscoveryMade, on_memory)

    await bus.emit(ActivityStarted(kind="s", context="a"))
    await bus.emit(DiscoveryMade(discovery_id="d1", title="t"))
    await bus.emit(LongGapDetected(hours_since_last=36.0))

    assert len(turn_log) == 1
    assert len(memory_log) == 1


@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_others():
    bus = EventBus()
    good_log: list = []

    async def bad_handler(e: ActivityStarted) -> None:
        raise RuntimeError("oops")

    async def good_handler(e: ActivityStarted) -> None:
        good_log.append(e)

    bus.subscribe(ActivityStarted, bad_handler)
    bus.subscribe(ActivityStarted, good_handler)

    await bus.emit(ActivityStarted(kind="s", context="x"))
    # good_handler should still run despite bad_handler raising.
    assert len(good_log) == 1


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    log: list = []

    async def handler(e: ActivityStarted) -> None:
        log.append(e)

    bus.subscribe(ActivityStarted, handler)
    bus.unsubscribe(ActivityStarted, handler)
    await bus.emit(ActivityStarted(kind="s", context="x"))
    assert log == []
