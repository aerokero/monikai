"""Tests for self-editing memory tools."""

from __future__ import annotations

import pytest

from backend.soul.memory import store
from backend.soul.memory.tools import memory_pin, memory_promote, memory_rethink, memory_revise
from backend.soul.models import MemoryEntry


async def _add(content: str, type_: str = "stm", importance: float = 5.0, db_path=None):
    entry = MemoryEntry(id="x", type=type_, content=content, importance=importance)
    entry_id, _ = await store.add(entry, db_path=db_path)
    return entry_id


async def test_memory_revise_updates_content(tmp_db):
    eid = await _add("old content here", db_path=tmp_db)
    result = await memory_revise(eid, "new revised content", db_path=tmp_db)
    assert result is True
    fetched = await store.get(eid, db_path=tmp_db)
    assert fetched.content == "new revised content"


async def test_memory_revise_rescores_importance(tmp_db):
    eid = await _add("old content", importance=3.0, db_path=tmp_db)
    # Emotional content should score higher than plain "old content"
    await memory_revise(eid, "czuję że to było bardzo ważne doświadczenie", db_path=tmp_db)
    fetched = await store.get(eid, db_path=tmp_db)
    assert fetched.importance > 3.0


async def test_memory_revise_nonexistent_returns_false(tmp_db):
    result = await memory_revise("nonexistent_id", "content", db_path=tmp_db)
    assert result is False


async def test_memory_promote_stm_to_ltm(tmp_db):
    eid = await _add("important event happened", type_="stm", importance=8.0, db_path=tmp_db)
    new_type = await memory_promote(eid, db_path=tmp_db)
    assert new_type in ("episodic", "semantic")
    fetched = await store.get(eid, db_path=tmp_db)
    assert fetched.type == new_type


async def test_memory_promote_already_ltm_is_noop(tmp_db):
    eid = await _add("already episodic", type_="episodic", importance=7.0, db_path=tmp_db)
    new_type = await memory_promote(eid, db_path=tmp_db)
    assert new_type == "episodic"


async def test_memory_promote_nonexistent_returns_none(tmp_db):
    result = await memory_promote("bad_id", db_path=tmp_db)
    assert result is None


async def test_memory_rethink_updates_importance(tmp_db):
    eid = await _add("czuję że to było ważne wydarzenie", importance=3.0, db_path=tmp_db)
    new_imp = await memory_rethink(eid, db_path=tmp_db)
    assert new_imp is not None
    assert new_imp > 3.0  # emotional content should score higher


async def test_memory_rethink_nonexistent_returns_none(tmp_db):
    result = await memory_rethink("bad_id", db_path=tmp_db)
    assert result is None


async def test_memory_pin_sets_max_importance(tmp_db):
    eid = await _add("very important memory", importance=4.0, db_path=tmp_db)
    result = await memory_pin(eid, db_path=tmp_db)
    assert result is True
    fetched = await store.get(eid, db_path=tmp_db)
    assert fetched.importance == pytest.approx(10.0)


async def test_memory_pin_promotes_stm_to_episodic(tmp_db):
    eid = await _add("pinnable stm entry", type_="stm", db_path=tmp_db)
    await memory_pin(eid, db_path=tmp_db)
    fetched = await store.get(eid, db_path=tmp_db)
    assert fetched.type == "episodic"


async def test_memory_pin_nonexistent_returns_false(tmp_db):
    result = await memory_pin("bad_id", db_path=tmp_db)
    assert result is False
