"""Smoke tests for SQLite schema initialisation."""

from __future__ import annotations

import pytest

from backend.soul.db import get_db


@pytest.mark.asyncio
async def test_schema_tables_exist(tmp_db):
    expected_tables = {
        "memory_entries",
        "kg_entities",
        "kg_relationships",
        "progression_state",
        "events",
        "jobs",
    }
    async with get_db(path=tmp_db) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        rows = await cursor.fetchall()
    found = {row["name"] for row in rows}
    assert expected_tables.issubset(found), f"Missing tables: {expected_tables - found}"


@pytest.mark.asyncio
async def test_memory_entry_insert_and_retrieve(tmp_db):
    async with get_db(path=tmp_db) as conn:
        await conn.execute(
            """
            INSERT INTO memory_entries (id, type, content, importance)
            VALUES ('m1', 'stm', 'Test memory', 5.0)
            """
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT content, importance FROM memory_entries WHERE id = 'm1'"
        )
        row = await cursor.fetchone()
    assert row is not None
    assert row["content"] == "Test memory"
    assert row["importance"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_importance_constraint(tmp_db):
    import aiosqlite
    async with get_db(path=tmp_db) as conn:
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO memory_entries (id, type, content, importance) "
                "VALUES ('bad', 'stm', 'x', 0.5)"
            )


@pytest.mark.asyncio
async def test_job_queue_insert(tmp_db):
    async with get_db(path=tmp_db) as conn:
        await conn.execute(
            """
            INSERT INTO jobs (id, kind, payload)
            VALUES ('j1', 'CompactionJob', '{}')
            """
        )
        await conn.commit()
        cursor = await conn.execute("SELECT status FROM jobs WHERE id = 'j1'")
        row = await cursor.fetchone()
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_events_table_insert(tmp_db):
    async with get_db(path=tmp_db) as conn:
        await conn.execute(
            """
            INSERT INTO events (id, type, payload)
            VALUES ('e1', 'TurnCompleted', '{"session_id": "s1"}')
            """
        )
        await conn.commit()
        cursor = await conn.execute("SELECT consumed_by FROM events WHERE id = 'e1'")
        row = await cursor.fetchone()
    assert row["consumed_by"] is None


@pytest.mark.asyncio
async def test_init_db_is_idempotent(tmp_path):
    from backend.soul.db import init_db
    db_path = tmp_path / "idem.db"
    await init_db(path=db_path)
    await init_db(path=db_path)  # second call must not raise
