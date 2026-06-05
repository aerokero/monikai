"""Tests for the personality engine and state store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.soul.models import Affect, Needs, SoulState
from backend.soul.personality.engine import (
    PersonalityEngine,
    _compute_cycle_phase,
    _compute_energy,
    _compute_register,
)
from backend.soul.personality.state_store import StateStore


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

def test_energy_daytime():
    assert _compute_energy(12, 10) == pytest.approx(0.75)


def test_energy_night():
    assert _compute_energy(2, 10) < 0.3


def test_cycle_phase_peak():
    assert _compute_cycle_phase(15) == "peak_social"


def test_cycle_phase_late():
    assert _compute_cycle_phase(20) == "late_tired"


def test_register_protective():
    affect = Affect(pleasure=-0.3, arousal=0.4, dominance=0.4)
    needs = Needs()
    register = _compute_register(affect, needs, None)
    assert register == "protective"


def test_register_defaults_casual():
    affect = Affect()
    needs = Needs()
    register = _compute_register(affect, needs, None)
    assert register == "casual"


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------

async def test_observe_turn_returns_soul_state():
    engine = PersonalityEngine(affect=Affect(), needs=Needs())
    state = await engine.observe_turn("Czuję się dzisiaj nieźle, dziękuję!")
    assert isinstance(state, SoulState)
    assert state.active_register in ("casual", "intellectual", "emotional", "protective")


async def test_observe_turn_updates_affect():
    engine = PersonalityEngine(affect=Affect(pleasure=0.0), needs=Needs())
    state = await engine.observe_turn("haha super, lubię to!")
    # Laughter + positive should push pleasure up
    assert state.affect.pleasure > 0.0


async def test_observe_turn_updates_needs():
    engine = PersonalityEngine(affect=Affect(), needs=Needs(relatedness=0.5))
    prev_rel = engine._needs.relatedness
    await engine.observe_turn("Czuję się samotny ostatnio.", reciprocity=False)
    # self_disclosure should boost relatedness
    assert engine._needs.relatedness != prev_rel


async def test_session_end_decay():
    engine = PersonalityEngine(affect=Affect(), needs=Needs(relatedness=0.9))
    engine.apply_session_end()
    assert engine._needs.relatedness < 0.9


async def test_daily_decay():
    engine = PersonalityEngine(affect=Affect(), needs=Needs(relatedness=0.9))
    engine.apply_daily_decay(days_elapsed=3.0)
    assert engine._needs.relatedness < 0.9


# ---------------------------------------------------------------------------
# State store round-trip
# ---------------------------------------------------------------------------

def test_state_store_write_read_roundtrip(tmp_path: Path):
    state = SoulState(
        affect=Affect(pleasure=0.3, arousal=0.6, dominance=0.1),
        needs=Needs(autonomy=0.8, competence=0.6, relatedness=0.7),
        energy=0.9,
        cycle_phase="peak_social",
        active_register="intellectual",
        becoming_real=0.42,
    )
    path = tmp_path / "state.json"
    StateStore.write(state, path=path)
    loaded = StateStore.read(path=path)

    assert loaded.affect.pleasure == pytest.approx(0.3)
    assert loaded.needs.relatedness == pytest.approx(0.7)
    assert loaded.cycle_phase == "peak_social"
    assert loaded.becoming_real == pytest.approx(0.42)


def test_state_store_missing_file_returns_defaults(tmp_path: Path):
    path = tmp_path / "nonexistent.json"
    state = StateStore.read(path=path)
    assert isinstance(state, SoulState)


def test_state_store_corrupted_file_returns_defaults(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{ not valid json", encoding="utf-8")
    state = StateStore.read(path=path)
    assert isinstance(state, SoulState)
