"""Tests for the event-driven DiscoveryEngine."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.progression.discoveries import DiscoveryEngine
from backend.progression.state import get_unlocked_discoveries, get_turn_count
from backend.soul.events import (
    DiscoveryMade,
    EventBus,
    MemoryStored,
    TurnCompleted,
    UserDisclosure,
)


def _make_catalog(tmp_path: Path, content: str) -> Path:
    d = tmp_path / "catalog"
    d.mkdir(exist_ok=True)
    (d / "discoveries.yaml").write_text(textwrap.dedent(content), encoding="utf-8")
    return d


async def test_count_trigger_unlocks_on_nth_turn(tmp_path, tmp_db):
    catalog = _make_catalog(tmp_path, """
    - id: first_convo
      title: "First Words"
      trigger: "count:1"
      hidden: false
    """)
    bus = EventBus()
    engine = DiscoveryEngine(db_path=tmp_db, event_bus=bus, catalog_dir=catalog)
    await engine.start()

    fired = []
    async def on_discovery(e: DiscoveryMade) -> None:
        fired.append(e.discovery_id)
    bus.subscribe(DiscoveryMade, on_discovery)

    await bus.emit(TurnCompleted(session_id="s", user_text="hi", monika_text="hello"))
    assert "first_convo" in fired
    await engine.stop()


async def test_count_trigger_fires_only_once(tmp_path, tmp_db):
    catalog = _make_catalog(tmp_path, """
    - id: first_convo
      title: "First Words"
      trigger: "count:1"
      hidden: false
    """)
    bus = EventBus()
    engine = DiscoveryEngine(db_path=tmp_db, event_bus=bus, catalog_dir=catalog)
    await engine.start()

    fired = []
    async def on_discovery(e: DiscoveryMade) -> None:
        fired.append(e.discovery_id)
    bus.subscribe(DiscoveryMade, on_discovery)

    for _ in range(5):
        await bus.emit(TurnCompleted(session_id="s", user_text="hi", monika_text="hello"))

    assert fired.count("first_convo") == 1
    await engine.stop()


async def test_memory_trigger_with_importance_condition(tmp_path, tmp_db):
    catalog = _make_catalog(tmp_path, """
    - id: worth_keeping
      title: "Worth Keeping"
      trigger: "MemoryStored[importance>=9]"
      hidden: true
    """)
    bus = EventBus()
    engine = DiscoveryEngine(db_path=tmp_db, event_bus=bus, catalog_dir=catalog)
    await engine.start()

    fired = []
    async def on_discovery(e: DiscoveryMade) -> None:
        fired.append(e.discovery_id)
    bus.subscribe(DiscoveryMade, on_discovery)

    # Below threshold — should not fire
    await bus.emit(MemoryStored(entry_id="m1", importance=7.0, type="stm"))
    assert not fired

    # At threshold — should fire
    await bus.emit(MemoryStored(entry_id="m2", importance=9.5, type="episodic"))
    assert "worth_keeping" in fired
    await engine.stop()


async def test_user_disclosure_trigger(tmp_path, tmp_db):
    catalog = _make_catalog(tmp_path, """
    - id: opening_up
      title: "Opening Up"
      trigger: "UserDisclosure[emotional_depth>=0.7]"
      hidden: true
    """)
    bus = EventBus()
    engine = DiscoveryEngine(db_path=tmp_db, event_bus=bus, catalog_dir=catalog)
    await engine.start()

    fired = []
    async def on_discovery(e: DiscoveryMade) -> None:
        fired.append(e.discovery_id)
    bus.subscribe(DiscoveryMade, on_discovery)

    await bus.emit(UserDisclosure(content="heavy stuff", topic="life", emotional_depth=0.8))
    assert "opening_up" in fired
    await engine.stop()


async def test_simple_event_trigger_no_condition(tmp_path, tmp_db):
    catalog = _make_catalog(tmp_path, """
    - id: first_story
      title: "Evening Together"
      trigger: "StoryEnded"
      hidden: true
    """)
    from backend.soul.events import StoryEnded
    bus = EventBus()
    engine = DiscoveryEngine(db_path=tmp_db, event_bus=bus, catalog_dir=catalog)
    await engine.start()

    fired = []
    async def on_discovery(e: DiscoveryMade) -> None:
        fired.append(e.discovery_id)
    bus.subscribe(DiscoveryMade, on_discovery)

    await bus.emit(StoryEnded(story_id="rainy_evening", ending_id="warmth"))
    assert "first_story" in fired
    await engine.stop()


async def test_turn_count_is_persisted(tmp_path, tmp_db):
    catalog = _make_catalog(tmp_path, """
    - id: placeholder
      title: X
      trigger: "count:99"
      hidden: false
    """)
    bus = EventBus()
    engine = DiscoveryEngine(db_path=tmp_db, event_bus=bus, catalog_dir=catalog)
    await engine.start()

    for _ in range(3):
        await bus.emit(TurnCompleted(session_id="s", user_text="x", monika_text="y"))

    assert await get_turn_count(db_path=tmp_db) == 3
    await engine.stop()
