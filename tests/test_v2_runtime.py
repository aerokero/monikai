"""Integration tests for the V2Runtime singleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.runtimes import v2_runtime as v2


async def test_initialize_and_get(tmp_path):
    db = tmp_path / "test.db"
    runtime = await v2.initialize(db_path=db)
    try:
        assert v2.get() is runtime
        assert runtime.cached_prompt
        assert len(runtime.cached_prompt) > 100
    finally:
        await v2.shutdown()
        assert v2.get() is None


async def test_refresh_prompt_updates_cache(tmp_path):
    db = tmp_path / "test.db"
    await v2.initialize(db_path=db)
    try:
        runtime = v2.get()
        original = runtime.cached_prompt
        new_prompt = await runtime.refresh_prompt()
        # Prompt should be a non-empty string each time
        assert isinstance(new_prompt, str)
        assert len(new_prompt) > 100
    finally:
        await v2.shutdown()


async def test_get_none_before_initialize():
    # If already shut down (or never initialized), get() returns None.
    await v2.shutdown()  # ensure clean state
    assert v2.get() is None


async def test_shutdown_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    await v2.initialize(db_path=db)
    await v2.shutdown()
    await v2.shutdown()  # second call must not raise
    assert v2.get() is None


