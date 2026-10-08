"""Smoke tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.soul.models import MemoryEntry


def test_memory_entry_importance_bounds():
    with pytest.raises(ValidationError):
        MemoryEntry(id="x", type="stm", content="test", importance=0.5)
    with pytest.raises(ValidationError):
        MemoryEntry(id="x", type="stm", content="test", importance=11.0)


def test_memory_entry_valid():
    entry = MemoryEntry(id="m1", type="episodic", content="First talk", importance=7.0)
    assert entry.type == "episodic"
    assert entry.perspective == "factual"
    assert entry.embedding is None
