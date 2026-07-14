"""Tests for Monika's own Minecraft goals (v3 Phase D)."""

from __future__ import annotations

from backend.progression import minecraft_goals as mcg


async def test_add_list_complete(tmp_db):
    gid, status = await mcg.add_goal("dokończyć ogród przy bazie", db_path=tmp_db)
    assert status == "ok"

    goals = await mcg.list_goals(db_path=tmp_db)
    assert len(goals) == 1
    assert goals[0]["text"] == "dokończyć ogród przy bazie"

    assert await mcg.complete_goal("ogród", db_path=tmp_db) is True
    assert await mcg.list_goals(db_path=tmp_db) == []
    done = await mcg.list_goals(db_path=tmp_db, status="done")
    assert len(done) == 1


async def test_dedup_and_cap(tmp_db):
    _, s1 = await mcg.add_goal("cel A", db_path=tmp_db)
    _, s2 = await mcg.add_goal("cel A", db_path=tmp_db)
    assert (s1, s2) == ("ok", "dedup")

    for i in range(4):
        await mcg.add_goal(f"cel {i}", db_path=tmp_db)
    _, s_full = await mcg.add_goal("jeszcze jeden", db_path=tmp_db)
    assert s_full == "full"


async def test_complete_missing_returns_false(tmp_db):
    assert await mcg.complete_goal("nie istnieje", db_path=tmp_db) is False


async def test_format_open_goals(tmp_db):
    assert await mcg.format_open_goals(db_path=tmp_db) == ""
    await mcg.add_goal("zbudować latarnię", db_path=tmp_db)
    line = await mcg.format_open_goals(db_path=tmp_db)
    assert "latarnię" in line
