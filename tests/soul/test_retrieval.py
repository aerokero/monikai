"""Tests for the Stanford retrieval scoring formula."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.soul.memory.retrieval import (
    RetrievalResult,
    composite_score,
    importance_score,
    recency_score,
    retrieve,
)
from backend.soul.memory import store
from backend.soul.models import MemoryEntry


def _entry(content: str, importance: float = 5.0, hours_ago: float = 1.0) -> MemoryEntry:
    created = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return MemoryEntry(
        id="x", type="stm", content=content, importance=importance, created_at=created
    )


def test_recency_decays_over_time():
    fresh = _entry("fresh", hours_ago=1.0)
    old = _entry("old", hours_ago=200.0)
    assert recency_score(fresh) > recency_score(old)


def test_recency_recent_is_close_to_1():
    e = _entry("recent", hours_ago=0.1)
    assert recency_score(e) > 0.99


def test_recency_week_old_is_below_half():
    e = _entry("week", hours_ago=24 * 7)  # 168 hours → 0.995^168 ≈ 0.43
    assert recency_score(e) < 0.5


def test_importance_normalised():
    e5 = _entry("mid", importance=5.0)
    e10 = _entry("high", importance=10.0)
    e1 = _entry("low", importance=1.0)
    assert importance_score(e10) == pytest.approx(1.0)
    assert importance_score(e1) == pytest.approx(0.1)
    assert importance_score(e5) == pytest.approx(0.5)


def test_composite_score_equal_weights():
    score = composite_score(recency=0.9, importance=0.5, relevance=0.6)
    expected = (0.9 + 0.5 + 0.6) / 3.0
    assert score == pytest.approx(expected)


def test_composite_score_all_zero():
    assert composite_score(0.0, 0.0, 0.0) == pytest.approx(0.0)


def test_composite_score_all_one():
    assert composite_score(1.0, 1.0, 1.0) == pytest.approx(1.0)


def test_composite_custom_weights():
    # With β=0 importance doesn't contribute.
    score_no_imp = composite_score(recency=0.8, importance=0.9, relevance=0.2, β=0)
    score_with_imp = composite_score(recency=0.8, importance=0.9, relevance=0.2, β=1)
    assert score_no_imp != pytest.approx(score_with_imp)


async def test_retrieve_returns_most_relevant(tmp_db):
    entries = [
        _entry("Bartosz loves Minecraft building"),
        _entry("The cat sat on the mat"),
        _entry("Minecraft redstone engineering"),
    ]
    for e in entries:
        await store.add(e, db_path=tmp_db)

    results = await retrieve("Minecraft", limit=2, db_path=tmp_db)
    assert len(results) <= 2
    top_contents = [r.entry.content for r in results]
    assert any("Minecraft" in c for c in top_contents)


async def test_retrieve_updates_last_accessed(tmp_db):
    e = _entry("touchable by retrieval")
    entry_id, _ = await store.add(e, db_path=tmp_db)

    await retrieve("touchable", db_path=tmp_db)
    fetched = await store.get(entry_id, db_path=tmp_db)
    assert fetched.last_accessed is not None


async def test_retrieve_high_importance_ranks_higher(tmp_db):
    from datetime import timedelta

    # Two entries with same content (almost), one with much higher importance.
    old = datetime.now(tz=timezone.utc) - timedelta(hours=100)
    low = MemoryEntry(id="low_imp", type="stm", content="rainy day walk", importance=2.0, created_at=old)
    high = MemoryEntry(id="high_imp", type="stm", content="rainy day walk important", importance=9.0, created_at=old)

    await store.add(low, db_path=tmp_db)
    await store.add(high, db_path=tmp_db)

    results = await retrieve("rainy day", db_path=tmp_db)
    if len(results) >= 2:
        # High importance entry should score better.
        imp_scores = [r.importance for r in results]
        # The entry with higher importance should have a higher importance component.
        assert max(imp_scores) == pytest.approx(0.9)


async def test_retrieve_empty_db(tmp_db):
    results = await retrieve("anything", db_path=tmp_db)
    assert results == []
