"""Shared pytest fixtures for MonikAI v2 tests."""

from __future__ import annotations

from pathlib import Path

import pytest_asyncio


@pytest_asyncio.fixture
async def tmp_db(tmp_path: Path):
    """Initialised in-memory-like temp database for each test."""
    from backend.soul.db import init_db
    db_path = tmp_path / "test_monika.db"
    await init_db(path=db_path)
    return db_path
