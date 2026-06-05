from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from backend.progression.state import get, set_
from backend.soul.time_engine.engine import TimeEngine


def test_time_engine_context_uses_supplied_datetime():
    engine = TimeEngine()
    ctx = engine.get_context(datetime(2026, 6, 5, 21, tzinfo=timezone.utc))

    assert ctx.season == "summer"
    assert ctx.time_of_day == "wieczór"
    assert ctx.day_of_week == 4
    assert ctx.energy_hint == 0.80


async def test_time_engine_records_interaction(tmp_db):
    engine = TimeEngine()

    await engine.record_interaction(tmp_db)

    raw = await get("last_interaction_ts", tmp_db)
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


async def test_time_engine_detects_long_gap(tmp_db):
    engine = TimeEngine()
    old = datetime.now(tz=timezone.utc) - timedelta(hours=72)
    await set_("last_interaction_ts", old.isoformat(timespec="seconds"), tmp_db)

    gap = await engine.check_gap(tmp_db)

    assert gap.category == "long"
    assert gap.hours >= 71
    assert gap.needs_decay_days >= 2.9


async def test_time_engine_anniversary_matching(tmp_db):
    engine = TimeEngine()
    await set_(
        "anniversaries",
        [
            {"label": "First film", "date": "2025-06-05"},
            {"label": "Other day", "date": "2025-06-06"},
        ],
        tmp_db,
    )

    labels = await engine.check_anniversaries(tmp_db, today=date(2026, 6, 5))

    assert labels == ["First film"]


async def test_time_engine_add_anniversary_deduplicates(tmp_db):
    engine = TimeEngine()

    await engine.add_anniversary("First talk", "2026-06-05", tmp_db)
    await engine.add_anniversary("First talk", "2026-06-05", tmp_db)

    anniversaries = await get("anniversaries", tmp_db)
    assert anniversaries == [{"label": "First talk", "date": "2026-06-05"}]
