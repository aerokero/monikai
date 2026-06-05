"""Tests for progression SQLite state persistence."""

from __future__ import annotations

import pytest

from backend.progression import state as ps


async def test_get_missing_key_returns_none(tmp_db):
    result = await ps.get("nonexistent_key", db_path=tmp_db)
    assert result is None


async def test_set_and_get_roundtrip(tmp_db):
    await ps.set_("test_key", {"foo": 42, "bar": "baz"}, db_path=tmp_db)
    result = await ps.get("test_key", db_path=tmp_db)
    assert result == {"foo": 42, "bar": "baz"}


async def test_set_overwrites(tmp_db):
    await ps.set_("k", "first", db_path=tmp_db)
    await ps.set_("k", "second", db_path=tmp_db)
    assert await ps.get("k", db_path=tmp_db) == "second"


async def test_unlock_discovery(tmp_db):
    result = await ps.unlock_discovery("first_words", db_path=tmp_db)
    assert result is True
    unlocked = await ps.get_unlocked_discoveries(db_path=tmp_db)
    assert "first_words" in unlocked


async def test_unlock_discovery_idempotent(tmp_db):
    await ps.unlock_discovery("first_words", db_path=tmp_db)
    second = await ps.unlock_discovery("first_words", db_path=tmp_db)
    assert second is False


async def test_is_unlocked(tmp_db):
    assert not await ps.is_unlocked("first_words", db_path=tmp_db)
    await ps.unlock_discovery("first_words", db_path=tmp_db)
    assert await ps.is_unlocked("first_words", db_path=tmp_db)


async def test_add_milestone(tmp_db):
    added = await ps.add_milestone("m1", "New story unlocked", db_path=tmp_db)
    assert added is True
    milestones = await ps.get_milestones(db_path=tmp_db)
    assert any(m["id"] == "m1" for m in milestones)


async def test_add_milestone_idempotent(tmp_db):
    await ps.add_milestone("m1", "effect", db_path=tmp_db)
    second = await ps.add_milestone("m1", "effect", db_path=tmp_db)
    assert second is False


async def test_turn_count_increments(tmp_db):
    c1 = await ps.increment_turn_count(db_path=tmp_db)
    c2 = await ps.increment_turn_count(db_path=tmp_db)
    assert c1 == 1
    assert c2 == 2


async def test_get_turn_count_empty(tmp_db):
    assert await ps.get_turn_count(db_path=tmp_db) == 0


async def test_bond_state_defaults(tmp_db):
    bond = await ps.get_bond_state(db_path=tmp_db)
    assert "closeness" in bond
    assert "streak_days" in bond


async def test_update_bond_state(tmp_db):
    bond = await ps.update_bond_state({"streak_days": 5}, db_path=tmp_db)
    assert bond["streak_days"] == 5
    bond2 = await ps.get_bond_state(db_path=tmp_db)
    assert bond2["streak_days"] == 5
