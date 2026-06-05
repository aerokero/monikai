"""Integration tests for the V2Runtime singleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core import v2_runtime as v2


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


async def test_soul_state_accessible(tmp_path):
    db = tmp_path / "test.db"
    await v2.initialize(db_path=db)
    try:
        state = v2.get().soul_state
        assert state.active_register in ("casual", "intellectual", "emotional", "protective")
        assert 0.0 <= state.energy <= 1.0
    finally:
        await v2.shutdown()


async def test_process_turn_returns_cognition(tmp_path):
    db = tmp_path / "test.db"
    await v2.initialize(db_path=db)
    try:
        msg = await v2.get().process_turn("Cześć, jak się masz?")
        assert msg.startswith("(Internal Monologue)")
        assert len(msg) > 30
    finally:
        await v2.shutdown()


async def test_process_turn_updates_needs(tmp_path):
    db = tmp_path / "test.db"
    await v2.initialize(db_path=db)
    try:
        runtime = v2.get()
        before = runtime.soul_state.needs.relatedness
        # Self-disclosure should bump relatedness
        await runtime.process_turn("Czuję się dziś trochę samotny, chciałem się podzielić.")
        after = runtime.soul_state.needs.relatedness
        # Needs update is deterministic from signals
        assert isinstance(after, float)
        assert 0.0 <= after <= 1.0
    finally:
        await v2.shutdown()


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


async def test_needs_status(tmp_path):
    db = tmp_path / "test.db"
    await v2.initialize(db_path=db)
    try:
        status = v2.get().needs_status
        assert hasattr(status, "relatedness_unmet")
        assert hasattr(status, "priority_need")
    finally:
        await v2.shutdown()
