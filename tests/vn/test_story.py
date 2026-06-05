"""Tests for the story loader."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.vn.story import Story, StoryBranch, StoryEnding, load_story, list_stories


def _write_story(tmp_path: Path, content: str, name: str = "test_story.yaml") -> Path:
    d = tmp_path / "stories"
    d.mkdir(exist_ok=True)
    (d / name).write_text(textwrap.dedent(content), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# Real story loading
# ---------------------------------------------------------------------------

def test_load_real_onboarding():
    story = load_story("onboarding")
    assert story is not None
    assert story.id == "onboarding"
    assert story.title
    assert story.opening
    assert len(story.branches) > 0
    assert len(story.endings) > 0


def test_load_real_rainy_evening():
    story = load_story("rainy_evening")
    assert story is not None
    assert story.preferred_weather == "rain"
    assert story.discovery == "first_story"


def test_list_stories_includes_known():
    ids = list_stories()
    assert "onboarding" in ids
    assert "rainy_evening" in ids


# ---------------------------------------------------------------------------
# Synthetic loading tests
# ---------------------------------------------------------------------------

def test_load_story_not_found(tmp_path):
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir()
    result = load_story("nonexistent", stories_dir=stories_dir)
    assert result is None


def test_load_story_parses_fields(tmp_path):
    d = _write_story(tmp_path, """
    id: test_story
    title: "Test Story"
    unlock: always
    discovery: test_discovery

    scene:
      bg: test_bg
      outfit: test_outfit
      expr: happy
      light: bright

    opening:
      context: |
        She opens with warmth.

    branches:
      - id: branch_a
        when: "user is happy"
        context: "Happy branch context."
      - id: branch_b
        when: "user is sad"
        context: "Sad branch context."

    endings:
      - id: good_end
        when: "things went well"
        context: "It was a good evening."
    """)
    story = load_story("test_story", stories_dir=d)
    assert story is not None
    assert story.id == "test_story"
    assert story.title == "Test Story"
    assert story.scene.bg == "test_bg"
    assert story.scene.expr == "happy"
    assert "warmth" in story.opening
    assert len(story.branches) == 2
    assert story.branches[0].id == "branch_a"
    assert story.discovery == "test_discovery"
    assert len(story.endings) == 1


def test_load_story_preferred_time_as_list(tmp_path):
    d = _write_story(tmp_path, """
    id: timed_story
    title: "Timed"
    unlock: always
    preferred_time: [evening, night]
    opening:
      context: "Evening vibes."
    """, name="timed_story.yaml")
    story = load_story("timed_story", stories_dir=d)
    assert story is not None
    assert story.preferred_time == ["evening", "night"]


def test_load_story_preferred_time_as_string(tmp_path):
    d = _write_story(tmp_path, """
    id: single_time
    title: X
    unlock: always
    preferred_time: evening
    opening:
      context: "x"
    """, name="single_time.yaml")
    story = load_story("single_time", stories_dir=d)
    assert story is not None
    assert story.preferred_time == ["evening"]


def test_load_story_malformed_returns_none(tmp_path):
    d = tmp_path / "stories"
    d.mkdir()
    (d / "bad.yaml").write_text("{ not: valid: yaml: at: all", encoding="utf-8")
    result = load_story("bad", stories_dir=d)
    assert result is None


def test_list_stories_from_custom_dir(tmp_path):
    d = _write_story(tmp_path, "id: s1\ntitle: S1\nunlock: always\nopening:\n  context: x", "s1.yaml")
    _write_story(tmp_path, "id: s2\ntitle: S2\nunlock: always\nopening:\n  context: y", "s2.yaml")
    ids = list_stories(stories_dir=d)
    assert "s1" in ids
    assert "s2" in ids
