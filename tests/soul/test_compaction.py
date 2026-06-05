"""Tests for the STM → LTM compaction pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.soul.memory import store
from backend.soul.memory.compaction import CompactionResult, run_compaction
from backend.soul.models import MemoryEntry


def _old_stm(content: str, importance: float, hours_ago: float = 200.0) -> MemoryEntry:
    created = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return MemoryEntry(
        id="x", type="stm", content=content, importance=importance, created_at=created
    )


async def test_compaction_skips_when_below_threshold(tmp_db):
    # Only a few low-importance entries → cumulative importance < 150.
    for i in range(5):
        await store.add(_old_stm(f"minor thing {i}", importance=3.0), db_path=tmp_db)

    result = await run_compaction(db_path=tmp_db, importance_threshold=150.0)
    assert result.skipped is True
    assert result.cumulative_importance == pytest.approx(15.0)


async def test_compaction_runs_above_threshold(tmp_db):
    # Enough important entries to cross threshold.
    for i in range(10):
        await store.add(_old_stm(f"important event {i}", importance=8.0), db_path=tmp_db)
    # cumulative = 80 > threshold=50 for test.

    result = await run_compaction(
        db_path=tmp_db,
        importance_threshold=50.0,
        promote_top_n=5,
    )
    assert result.skipped is False
    assert result.promoted_episodic + result.promoted_semantic > 0


async def test_compaction_promotes_and_discards(tmp_db):
    high_imp_content = "czuję że to było ważne wydarzenie w moim życiu"

    for i in range(15):
        if i < 5:
            # High importance emotional content → should be promoted to episodic
            entry = _old_stm(f"emotional: {high_imp_content} #{i}", importance=8.5)
        else:
            entry = _old_stm(f"minor fact {i}", importance=4.0)
        await store.add(entry, db_path=tmp_db)
    # cumulative = 5*8.5 + 10*4.0 = 42.5+40 = 82.5 > 50

    result = await run_compaction(
        db_path=tmp_db,
        importance_threshold=50.0,
        promote_top_n=5,
    )
    assert result.skipped is False
    assert result.promoted_episodic + result.promoted_semantic == 5
    assert result.discarded == 10

    # Verify promoted entries are no longer STM.
    stm_remaining = await store.get_stm(db_path=tmp_db)
    assert len(stm_remaining) == 0


async def test_compaction_only_processes_old_stm(tmp_db):
    """New STM entries (< stm_age_hours) should not be touched."""
    old_entry = _old_stm("old memory", importance=8.0, hours_ago=200.0)
    new_entry = MemoryEntry(
        id="new", type="stm", content="fresh memory", importance=8.0,
        created_at=datetime.now(tz=timezone.utc) - timedelta(minutes=30),
    )
    await store.add(old_entry, db_path=tmp_db)
    new_id, _ = await store.add(new_entry, db_path=tmp_db)

    result = await run_compaction(
        db_path=tmp_db,
        stm_age_hours=168,
        importance_threshold=5.0,
        promote_top_n=10,
    )
    # Only old_entry (>168h) was considered.
    assert result.cumulative_importance == pytest.approx(8.0)

    fresh = await store.get(new_id, db_path=tmp_db)
    assert fresh.type == "stm"


async def test_compaction_empty_db(tmp_db):
    result = await run_compaction(db_path=tmp_db)
    assert result.skipped is True
    assert result.cumulative_importance == pytest.approx(0.0)


async def test_compaction_emits_event(tmp_db):
    from backend.soul.events import CompactionDone, bus

    received = []

    async def handler(e: CompactionDone) -> None:
        received.append(e)

    bus.subscribe(CompactionDone, handler)
    try:
        for i in range(8):
            await store.add(_old_stm(f"data {i}", importance=8.0), db_path=tmp_db)
        # cumulative = 64 > 50
        await run_compaction(db_path=tmp_db, importance_threshold=50.0, promote_top_n=4)
        assert len(received) == 1
        assert received[0].entries_kept == 4
        assert received[0].entries_discarded == 4
    finally:
        bus.unsubscribe(CompactionDone, handler)
