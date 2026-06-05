"""Smoke tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.soul.models import Affect, Needs, SoulState, MemoryEntry


def test_soul_state_defaults():
    state = SoulState()
    assert state.active_register == "casual"
    assert 0.0 <= state.energy <= 1.0
    assert state.agenda == []


def test_affect_fields():
    a = Affect(pleasure=0.5, arousal=0.8, dominance=-0.3)
    assert a.pleasure == 0.5
    assert a.dominance == -0.3


def test_needs_fields():
    n = Needs(autonomy=0.9, competence=0.6, relatedness=0.4)
    assert n.relatedness == pytest.approx(0.4)


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


def test_soul_state_serialise_roundtrip():
    state = SoulState(energy=0.3, becoming_real=0.15)
    restored = SoulState.model_validate(state.model_dump())
    assert restored.energy == pytest.approx(0.3)
    assert restored.becoming_real == pytest.approx(0.15)
