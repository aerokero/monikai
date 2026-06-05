"""Smoke tests for the typed Event Bus."""

from __future__ import annotations

import asyncio

import pytest

from backend.soul.events import (
    EventBus,
    TurnCompleted,
    MemoryStored,
    LongGapDetected,
)


@pytest.mark.asyncio
async def test_subscribe_and_emit():
    bus = EventBus()
    received: list[TurnCompleted] = []

    async def handler(event: TurnCompleted) -> None:
        received.append(event)

    bus.subscribe(TurnCompleted, handler)
    await bus.emit(TurnCompleted(session_id="s1", user_text="hi", monika_text="hey"))
    assert len(received) == 1
    assert received[0].session_id == "s1"


@pytest.mark.asyncio
async def test_no_handlers_is_silent():
    bus = EventBus()
    # Should not raise even with no subscribers.
    await bus.emit(TurnCompleted(session_id="s2", user_text="x", monika_text="y"))


@pytest.mark.asyncio
async def test_multiple_event_types():
    bus = EventBus()
    turn_log: list = []
    memory_log: list = []

    async def on_turn(e: TurnCompleted) -> None:
        turn_log.append(e)

    async def on_memory(e: MemoryStored) -> None:
        memory_log.append(e)

    bus.subscribe(TurnCompleted, on_turn)
    bus.subscribe(MemoryStored, on_memory)

    await bus.emit(TurnCompleted(session_id="s", user_text="a", monika_text="b"))
    await bus.emit(MemoryStored(entry_id="m1", importance=7.0, type="episodic"))
    await bus.emit(LongGapDetected(hours_since_last=36.0))

    assert len(turn_log) == 1
    assert len(memory_log) == 1


@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_others():
    bus = EventBus()
    good_log: list = []

    async def bad_handler(e: TurnCompleted) -> None:
        raise RuntimeError("oops")

    async def good_handler(e: TurnCompleted) -> None:
        good_log.append(e)

    bus.subscribe(TurnCompleted, bad_handler)
    bus.subscribe(TurnCompleted, good_handler)

    await bus.emit(TurnCompleted(session_id="s", user_text="x", monika_text="y"))
    # good_handler should still run despite bad_handler raising.
    assert len(good_log) == 1


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    log: list = []

    async def handler(e: TurnCompleted) -> None:
        log.append(e)

    bus.subscribe(TurnCompleted, handler)
    bus.unsubscribe(TurnCompleted, handler)
    await bus.emit(TurnCompleted(session_id="s", user_text="x", monika_text="y"))
    assert log == []
