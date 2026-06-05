"""Tests for YAML catalog loading and trigger parsing."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from backend.progression.catalog import (
    DiscoveryEntry,
    GoalEntry,
    RitualEntry,
    check_condition,
    load_discoveries,
    load_goals,
    load_rituals,
    parse_trigger,
    trigger_matches,
)


# ---------------------------------------------------------------------------
# Real catalog loading
# ---------------------------------------------------------------------------

def test_load_discoveries_nonempty():
    entries = load_discoveries()
    assert len(entries) > 0


def test_load_discoveries_types():
    entries = load_discoveries()
    assert all(isinstance(e, DiscoveryEntry) for e in entries)


def test_load_goals_nonempty():
    entries = load_goals()
    assert len(entries) > 0


def test_load_rituals_nonempty():
    entries = load_rituals()
    assert len(entries) > 0


def test_discoveries_have_required_fields():
    entries = load_discoveries()
    for e in entries:
        assert e.id
        assert e.title
        assert e.trigger


def test_rituals_have_valid_need_trigger():
    valid_needs = {"relatedness", "competence", "autonomy"}
    for e in load_rituals():
        assert e.need_trigger in valid_needs, f"{e.id}: invalid need_trigger {e.need_trigger!r}"


# ---------------------------------------------------------------------------
# Trigger parsing
# ---------------------------------------------------------------------------

def test_parse_trigger_simple():
    name, cond = parse_trigger("TurnCompleted")
    assert name == "TurnCompleted"
    assert cond is None


def test_parse_trigger_with_condition():
    name, cond = parse_trigger("MemoryStored[importance>=9]")
    assert name == "MemoryStored"
    assert cond == "importance>=9"


def test_parse_trigger_count():
    name, cond = parse_trigger("count:5")
    assert name == "count"
    assert cond == "5"


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def test_check_condition_gte():
    assert check_condition("importance>=8", {"importance": 9.0})
    assert not check_condition("importance>=8", {"importance": 7.0})


def test_check_condition_lte():
    assert check_condition("depth<=0.5", {"depth": 0.4})
    assert not check_condition("depth<=0.5", {"depth": 0.6})


def test_check_condition_exact():
    assert check_condition("story_id=first_movie", {"story_id": "first_movie"})
    assert not check_condition("story_id=first_movie", {"story_id": "second_movie"})


def test_check_condition_missing_key():
    assert not check_condition("importance>=5", {})


def test_check_condition_bool():
    assert check_condition("laughter=true", {"laughter": True})
    assert not check_condition("laughter=true", {"laughter": False})


# ---------------------------------------------------------------------------
# Trigger matching
# ---------------------------------------------------------------------------

def test_trigger_matches_simple():
    assert trigger_matches("TurnCompleted", "TurnCompleted", {})
    assert not trigger_matches("TurnCompleted", "MemoryStored", {})


def test_trigger_matches_with_condition():
    assert trigger_matches("MemoryStored[importance>=9]", "MemoryStored", {"importance": 9.5})
    assert not trigger_matches("MemoryStored[importance>=9]", "MemoryStored", {"importance": 7.0})


def test_trigger_matches_count_returns_false():
    # count: triggers are handled by DiscoveryEngine, not trigger_matches
    assert not trigger_matches("count:5", "TurnCompleted", {})


# ---------------------------------------------------------------------------
# Malformed catalog handling
# ---------------------------------------------------------------------------

def test_load_discoveries_skips_malformed(tmp_path):
    bad = tmp_path / "discoveries.yaml"
    bad.write_text(textwrap.dedent("""
    - id: good
      title: Good Entry
      trigger: "TurnCompleted"
    - title: Missing ID
      trigger: "X"
    - id: no_title
      trigger: "Y"
    """), encoding="utf-8")
    entries = load_discoveries(catalog_dir=tmp_path)
    assert len(entries) == 1
    assert entries[0].id == "good"
