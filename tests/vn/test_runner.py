"""Tests for the Story Runner."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.soul.models import Affect, Needs, SoulState
from backend.vn.runner import StoryRunner, is_unlocked, list_available_stories
from backend.vn.story import load_story


def _state(register: str = "casual", pleasure: float = 0.1) -> SoulState:
    return SoulState(
        affect=Affect(pleasure=pleasure),
        needs=Needs(),
        energy=0.7,
        active_register=register,
    )


def _make_stories_dir(tmp_path: Path) -> Path:
    d = tmp_path / "stories"
    d.mkdir()
    (d / "warmth_story.yaml").write_text(textwrap.dedent("""
    id: warmth_story
    title: "Warm Evening"
    unlock: always

    scene:
      bg: room_day
      expr: soft
      light: warm
      outfit: casual

    opening:
      context: "She is warm and present."

    branches:
      - id: if_melancholic
        when: "user seems heavy"
        context: "She stays close. No fixing."
      - id: if_playful
        when: "easy mood"
        context: "She leans into laughter."

    endings:
      - id: warmth
        when: "things went well"
        context: "Something good happened tonight."
      - id: depth
        when: "something landed deeply"
        context: "She lets the weight sit."
    """), encoding="utf-8")
    return d


async def test_start_story_returns_context(tmp_path):
    d = _make_stories_dir(tmp_path)
    runner = StoryRunner()
    context = await runner.start("warmth_story", _state(), stories_dir=d)
    assert context is not None
    assert "Warm Evening" in context
    assert runner.is_active()


async def test_start_story_not_found_returns_none(tmp_path):
    d = _make_stories_dir(tmp_path)
    runner = StoryRunner()
    result = await runner.start("nonexistent_story", _state(), stories_dir=d)
    assert result is None


async def test_start_selects_protective_branch(tmp_path):
    d = _make_stories_dir(tmp_path)
    runner = StoryRunner()
    context = await runner.start("warmth_story", _state(register="protective"), stories_dir=d)
    assert context is not None
    assert runner.active_branch_id == "if_melancholic"


async def test_start_selects_casual_branch(tmp_path):
    d = _make_stories_dir(tmp_path)
    runner = StoryRunner()
    await runner.start("warmth_story", _state(register="casual"), stories_dir=d)
    assert runner.active_branch_id == "if_playful"


async def test_start_uses_opt_in_branch_selector(tmp_path):
    d = _make_stories_dir(tmp_path)

    async def selector(context):
        return "if_playful"

    runner = StoryRunner(branch_selection_mode="llm", branch_selector=selector)
    await runner.start("warmth_story", _state(register="protective"), stories_dir=d)
    assert runner.active_branch_id == "if_playful"


async def test_start_selector_falls_back_to_heuristic(tmp_path):
    d = _make_stories_dir(tmp_path)

    async def selector(context):
        return "missing"

    runner = StoryRunner(branch_selection_mode="llm", branch_selector=selector)
    await runner.start("warmth_story", _state(register="protective"), stories_dir=d)
    assert runner.active_branch_id == "if_melancholic"


async def test_end_story_returns_ending_context(tmp_path):
    d = _make_stories_dir(tmp_path)
    runner = StoryRunner()
    await runner.start("warmth_story", _state(), stories_dir=d)
    ending = await runner.end("warmth_story", _state(pleasure=0.3), stories_dir=d)
    assert ending is not None
    assert "tonight" in ending or "weight" in ending


async def test_end_story_clears_active(tmp_path):
    d = _make_stories_dir(tmp_path)
    runner = StoryRunner()
    await runner.start("warmth_story", _state(), stories_dir=d)
    assert runner.is_active()
    await runner.end(soul_state=_state(), stories_dir=d)
    assert not runner.is_active()


async def test_end_sad_soul_picks_depth_ending(tmp_path):
    d = _make_stories_dir(tmp_path)
    runner = StoryRunner()
    await runner.start("warmth_story", _state(), stories_dir=d)
    ending = await runner.end("warmth_story", _state(pleasure=-0.4), stories_dir=d)
    assert ending is not None
    assert "weight" in ending


async def test_is_unlocked_always(tmp_path):
    story = load_story("onboarding")
    assert story is not None
    assert await is_unlocked(story, db_path=None)


async def test_is_unlocked_turn_count(tmp_path, tmp_db):
    d = tmp_path / "stories"
    d.mkdir()
    (d / "locked.yaml").write_text(textwrap.dedent("""
    id: locked
    title: Locked
    unlock: "turn_count >= 5"
    opening:
      context: "You unlocked this."
    """), encoding="utf-8")
    story = load_story("locked", stories_dir=d)
    assert story is not None

    # Below threshold
    assert not await is_unlocked(story, db_path=tmp_db)

    # Simulate 5 turns
    from backend.progression.state import increment_turn_count
    for _ in range(5):
        await increment_turn_count(db_path=tmp_db)

    assert await is_unlocked(story, db_path=tmp_db)


async def test_list_available_filters_by_unlock(tmp_path, tmp_db):
    d = tmp_path / "stories"
    d.mkdir()
    (d / "free.yaml").write_text("id: free\ntitle: Free\nunlock: always\nopening:\n  context: x", encoding="utf-8")
    (d / "locked.yaml").write_text("id: locked\ntitle: Locked\nunlock: 'turn_count >= 100'\nopening:\n  context: y", encoding="utf-8")

    available = await list_available_stories(_state(), db_path=tmp_db, stories_dir=d)
    ids = [s.id for s in available]
    assert "free" in ids
    assert "locked" not in ids


async def test_is_unlocked_date(tmp_path):
    from datetime import datetime
    now = datetime.now()
    d = tmp_path / "stories"
    d.mkdir()
    
    # Matching date
    (d / "today.yaml").write_text(f"id: today\ntitle: Today\nunlock: 'date[{now.month:02d}-{now.day:02d}]'\nopening:\n  context: x", encoding="utf-8")
    # Non-matching date
    other_month = 1 if now.month != 1 else 2
    (d / "other_day.yaml").write_text(f"id: other_day\ntitle: Other\nunlock: 'date[{other_month:02d}-15]'\nopening:\n  context: y", encoding="utf-8")
    
    s1 = load_story("today", stories_dir=d)
    s2 = load_story("other_day", stories_dir=d)
    
    assert await is_unlocked(s1)
    assert not await is_unlocked(s2)


async def test_is_unlocked_date_range(tmp_path):
    from datetime import datetime, timedelta
    now = datetime.now()
    d = tmp_path / "stories"
    d.mkdir()
    
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)
    
    # Active range
    (d / "active.yaml").write_text(
        f"id: active\ntitle: Active\nunlock: 'date_range[{yesterday.month:02d}-{yesterday.day:02d} to {tomorrow.month:02d}-{tomorrow.day:02d}]'\nopening:\n  context: x",
        encoding="utf-8"
    )
    
    # Past range
    past_start = now - timedelta(days=5)
    past_end = now - timedelta(days=3)
    (d / "past.yaml").write_text(
        f"id: past\ntitle: Past\nunlock: 'date_range[{past_start.month:02d}-{past_start.day:02d} to {past_end.month:02d}-{past_end.day:02d}]'\nopening:\n  context: y",
        encoding="utf-8"
    )
    
    s1 = load_story("active", stories_dir=d)
    s2 = load_story("past", stories_dir=d)
    
    assert await is_unlocked(s1)
    assert not await is_unlocked(s2)
