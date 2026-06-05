"""Tests for the memory store (CRUD + dedup)."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from backend.soul.memory import store
from backend.soul.models import MemoryEntry


def _entry(content: str, type_: str = "stm", importance: float = 5.0, **kw) -> MemoryEntry:
    return MemoryEntry(id="ignored", type=type_, content=content, importance=importance, **kw)


async def test_add_and_get(tmp_db):
    e = _entry("Bartosz likes dark rye bread")
    entry_id, status = await store.add(e, db_path=tmp_db)
    assert status == "ok"
    assert entry_id.startswith("mem_")

    fetched = await store.get(entry_id, db_path=tmp_db)
    assert fetched is not None
    assert fetched.content == "Bartosz likes dark rye bread"
    assert fetched.type == "stm"
    assert fetched.importance == pytest.approx(5.0)


async def test_dedup(tmp_db):
    e = _entry("Bartosz likes dark rye bread")
    id1, s1 = await store.add(e, db_path=tmp_db)
    id2, s2 = await store.add(e, db_path=tmp_db)
    assert s1 == "ok"
    assert s2 == "dedup"
    assert id1 == id2


async def test_different_type_no_dedup(tmp_db):
    e1 = _entry("test content", type_="stm")
    e2 = _entry("test content", type_="episodic")
    _, s1 = await store.add(e1, db_path=tmp_db)
    _, s2 = await store.add(e2, db_path=tmp_db)
    assert s1 == "ok"
    assert s2 == "ok"


async def test_list_recent(tmp_db):
    for i in range(5):
        await store.add(_entry(f"entry {i}", importance=float(i + 1)), db_path=tmp_db)

    recent = await store.list_recent(limit=3, db_path=tmp_db)
    assert len(recent) == 3


async def test_list_recent_filter_type(tmp_db):
    await store.add(_entry("stm entry", type_="stm"), db_path=tmp_db)
    await store.add(_entry("episodic entry", type_="episodic"), db_path=tmp_db)

    stm = await store.list_recent(types=["stm"], db_path=tmp_db)
    assert all(e.type == "stm" for e in stm)


async def test_touch_updates_last_accessed(tmp_db):
    e = _entry("touchable entry")
    entry_id, _ = await store.add(e, db_path=tmp_db)

    await store.touch(entry_id, db_path=tmp_db)
    fetched = await store.get(entry_id, db_path=tmp_db)
    assert fetched.last_accessed is not None


async def test_promote_stm_to_episodic(tmp_db):
    e = _entry("something meaningful", type_="stm")
    entry_id, _ = await store.add(e, db_path=tmp_db)

    await store.promote(entry_id, "episodic", db_path=tmp_db)
    fetched = await store.get(entry_id, db_path=tmp_db)
    assert fetched.type == "episodic"


async def test_delete_batch(tmp_db):
    ids = []
    for i in range(4):
        entry_id, _ = await store.add(_entry(f"deletable {i}"), db_path=tmp_db)
        ids.append(entry_id)

    deleted = await store.delete_batch(ids[:2], db_path=tmp_db)
    assert deleted == 2

    remaining = await store.list_recent(db_path=tmp_db)
    remaining_ids = {e.id for e in remaining}
    assert ids[0] not in remaining_ids
    assert ids[2] in remaining_ids


async def test_get_stm_with_cutoff(tmp_db):
    from datetime import timedelta

    old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    new_time = datetime.now(tz=timezone.utc)

    e_old = MemoryEntry(
        id="old", type="stm", content="old stm", importance=3.0,
        created_at=old_time,
    )
    e_new = MemoryEntry(
        id="new", type="stm", content="new stm", importance=3.0,
        created_at=new_time,
    )

    await store.add(e_old, db_path=tmp_db)
    await store.add(e_new, db_path=tmp_db)

    cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
    old_entries = await store.get_stm(older_than=cutoff, db_path=tmp_db)
    ids = [e.id for e in old_entries]
    assert "old" in ids or any(e.content == "old stm" for e in old_entries)
    assert not any(e.content == "new stm" for e in old_entries)


async def test_search_fts(tmp_db):
    await store.add(_entry("Bartosz loves building in Minecraft"), db_path=tmp_db)
    await store.add(_entry("The weather in Poland is cold today"), db_path=tmp_db)
    await store.add(_entry("Minecraft mobs attack at night"), db_path=tmp_db)

    results = await store.search_fts("Minecraft", db_path=tmp_db)
    assert len(results) >= 1
    contents = [e.content for e, _ in results]
    assert any("Minecraft" in c for c in contents)


async def test_update_importance(tmp_db):
    e = _entry("test importance update", importance=4.0)
    entry_id, _ = await store.add(e, db_path=tmp_db)

    await store.update_importance(entry_id, 9.0, db_path=tmp_db)
    fetched = await store.get(entry_id, db_path=tmp_db)
    assert fetched.importance == pytest.approx(9.0)
