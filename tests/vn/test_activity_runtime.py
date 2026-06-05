from __future__ import annotations

import pytest

from backend.vn.activity_runtime import SharedActivityRuntime


async def test_shared_activity_runtime_start_and_snapshot(tmp_db):
    runtime = SharedActivityRuntime(db_path=tmp_db)

    session = await runtime.start("film", title="Stalker", context="opening scene")

    assert session.kind == "film"
    assert runtime.is_active()

    snapshot = runtime.snapshot()
    assert snapshot["active"] is True
    assert snapshot["kind"] == "film"
    assert snapshot["title"] == "Stalker"
    assert snapshot["scene"]["bg"] == "room_sofa_evening"


async def test_shared_activity_runtime_updates_context(tmp_db):
    runtime = SharedActivityRuntime(db_path=tmp_db)
    await runtime.start("game", title="Hollow Knight")

    changed = runtime.update_context("  boss room\n dialogue  ")

    assert changed is True
    assert "boss room dialogue" in runtime.monika_context()


async def test_shared_activity_runtime_ignores_duplicate_context(tmp_db):
    runtime = SharedActivityRuntime(db_path=tmp_db)
    await runtime.start("film", context="same subtitle")

    assert runtime.update_context("same subtitle") is False


async def test_shared_activity_runtime_rejects_unknown_kind(tmp_db):
    runtime = SharedActivityRuntime(db_path=tmp_db)

    with pytest.raises(ValueError):
        await runtime.start("sports")


async def test_shared_activity_runtime_end_clears_active(tmp_db):
    runtime = SharedActivityRuntime(db_path=tmp_db)
    await runtime.start("music", title="Album")

    result = await runtime.end(notes="Quiet session")

    assert result is not None
    assert runtime.snapshot() == {"active": False}
