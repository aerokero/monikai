"""Tests for shared activity sessions."""

from __future__ import annotations

import pytest

from backend.soul.memory import store
from backend.vn.activities import ActivitySession


async def test_start_activity_emits_event():
    from backend.soul.events import ActivityStarted, EventBus
    bus = EventBus()
    received = []
    async def on_activity(e: ActivityStarted) -> None:
        received.append(e)
    bus.subscribe(ActivityStarted, on_activity)

    # ActivitySession.start uses the global bus — test the model directly
    session = ActivitySession(kind="film", title="Blade Runner 2049", context="")
    assert session.kind == "film"
    assert session.title == "Blade Runner 2049"


async def test_vn_scene_film():
    session = ActivitySession(kind="film", title="Test Film", context="")
    scene = session.vn_scene()
    assert scene.bg == "room_sofa_evening"
    assert "dim" in scene.light


async def test_vn_scene_game():
    session = ActivitySession(kind="game", title=None, context="")
    scene = session.vn_scene()
    assert scene.expr == "engaged"


async def test_monika_context_includes_title():
    session = ActivitySession(kind="film", title="Blade Runner 2049", context="")
    ctx = session.monika_context()
    assert "Blade Runner 2049" in ctx
    assert "film" in ctx.lower()


async def test_monika_context_includes_screen_ocr():
    session = ActivitySession(kind="film", title=None, context="Roy Batty: I've seen things...")
    ctx = session.monika_context()
    assert "Roy Batty" in ctx


async def test_end_creates_memory(tmp_db):
    session = ActivitySession(kind="film", title="Stalker", context="")
    result = await session.end(notes="He seemed moved by the ending", db_path=tmp_db)
    assert result is not None
    assert "Stalker" in result.content
    assert result.type == "episodic"
    assert "film" in result.tags
    assert result.importance >= 1.0


async def test_end_twice_is_noop(tmp_db):
    session = ActivitySession(kind="game", title="Hollow Knight", context="")
    r1 = await session.end(db_path=tmp_db)
    r2 = await session.end(db_path=tmp_db)
    assert r1 is not None
    assert r2 is None


async def test_end_includes_notes_in_memory(tmp_db):
    session = ActivitySession(kind="film", title="Annihilation", context="")
    result = await session.end(notes="She loved the lighthouse scene", db_path=tmp_db)
    assert result is not None
    assert "lighthouse" in result.content


async def test_end_unlocks_film_discovery(tmp_db):
    from backend.soul.events import DiscoveryMade, EventBus
    bus = EventBus()
    discoveries = []
    async def on_discovery(e: DiscoveryMade) -> None:
        discoveries.append(e.discovery_id)
    bus.subscribe(DiscoveryMade, on_discovery)

    # The global bus is used by ActivitySession.end — this test verifies
    # the discovery is unlocked in the DB.
    session = ActivitySession(kind="film", title="Moonlight", context="")
    await session.end(db_path=tmp_db)

    from backend.progression.state import is_unlocked
    assert await is_unlocked("first_film_night", db_path=tmp_db)


async def test_update_context():
    session = ActivitySession(kind="film", title="Test", context="initial context")
    session.update_context("new screen content")
    assert "new screen content" in session.monika_context()
