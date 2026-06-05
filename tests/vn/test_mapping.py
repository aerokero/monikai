"""Tests for the VN Mapping Engine."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.soul.models import Affect, Needs, SoulState
from backend.vn.mapping import MappingEngine, SceneState, _numeric_compare, _time_bucket


def _state(
    register: str = "casual",
    pleasure: float = 0.1,
    arousal: float = 0.5,
    dominance: float = 0.0,
    energy: float = 0.7,
    cycle_phase: str = "calm_neutral",
) -> SoulState:
    return SoulState(
        affect=Affect(pleasure=pleasure, arousal=arousal, dominance=dominance),
        needs=Needs(),
        energy=energy,
        cycle_phase=cycle_phase,
        active_register=register,
    )


def _make_mapping(tmp_path: Path, content: str) -> MappingEngine:
    p = tmp_path / "mapping.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return MappingEngine(mapping_path=p)


# ---------------------------------------------------------------------------
# Real mapping.yaml smoke test
# ---------------------------------------------------------------------------

def test_real_mapping_loads():
    engine = MappingEngine()
    state = _state()
    scene = engine.compute(state, hour=12)
    assert isinstance(scene, SceneState)
    assert scene.bg
    assert scene.expr


def test_real_mapping_returns_scene_state():
    engine = MappingEngine()
    scene = engine.compute(_state(register="protective"), hour=20)
    assert isinstance(scene, SceneState)


# ---------------------------------------------------------------------------
# Synthetic mapping tests
# ---------------------------------------------------------------------------

def test_defaults_when_no_rules_match(tmp_path):
    engine = _make_mapping(tmp_path, """
    defaults:
      bg: room_day
      outfit: casual
      expr: neutral
      light: natural
    rules: []
    """)
    scene = engine.compute(_state(), hour=12)
    assert scene.bg == "room_day"
    assert scene.expr == "neutral"


def test_register_rule_matches(tmp_path):
    engine = _make_mapping(tmp_path, """
    defaults: {bg: room_day, outfit: casual, expr: neutral, light: natural}
    rules:
      - when:
          register: protective
        scene:
          expr: serious
          light: cool_blue
    """)
    scene = engine.compute(_state(register="protective"), hour=12)
    assert scene.expr == "serious"
    assert scene.light == "cool_blue"


def test_register_rule_does_not_match_wrong_register(tmp_path):
    engine = _make_mapping(tmp_path, """
    defaults: {bg: room_day, outfit: casual, expr: neutral, light: natural}
    rules:
      - when:
          register: protective
        scene:
          expr: serious
    """)
    scene = engine.compute(_state(register="casual"), hour=12)
    assert scene.expr == "neutral"


def test_time_rule_matches(tmp_path):
    engine = _make_mapping(tmp_path, """
    defaults: {bg: room_day, outfit: casual, expr: neutral, light: natural}
    rules:
      - when:
          time: night
        scene:
          bg: room_night
          light: dim_warm
    """)
    scene = engine.compute(_state(), hour=23)
    assert scene.bg == "room_night"
    assert scene.light == "dim_warm"


def test_affect_numeric_rule_matches(tmp_path):
    engine = _make_mapping(tmp_path, """
    defaults: {bg: room_day, outfit: casual, expr: neutral, light: natural}
    rules:
      - when:
          affect_pleasure: ">0.5"
        scene:
          expr: happy
    """)
    scene = engine.compute(_state(pleasure=0.7), hour=12)
    assert scene.expr == "happy"

    scene2 = engine.compute(_state(pleasure=0.3), hour=12)
    assert scene2.expr == "neutral"


def test_weather_rule_matches(tmp_path):
    engine = _make_mapping(tmp_path, """
    defaults: {bg: room_day, outfit: casual, expr: neutral, light: natural}
    rules:
      - when:
          weather: rain
        scene:
          bg: room_window_rain
          ambience: rain_window
    """)
    scene = engine.compute(_state(), hour=12, weather="Rainy, 15°C in Warsaw")
    assert scene.bg == "room_window_rain"
    assert scene.ambience == "rain_window"


def test_rules_merge_not_overwrite(tmp_path):
    """Later matching rules update only the keys they specify."""
    engine = _make_mapping(tmp_path, """
    defaults: {bg: room_day, outfit: casual, expr: neutral, light: natural}
    rules:
      - when:
          register: protective
        scene:
          expr: serious
      - when:
          affect_pleasure: "<-0.2"
        scene:
          light: cool_dim
    """)
    scene = engine.compute(_state(register="protective", pleasure=-0.4), hour=12)
    assert scene.expr == "serious"   # from first rule
    assert scene.light == "cool_dim"  # from second rule
    assert scene.bg == "room_day"     # from defaults


def test_energy_rule(tmp_path):
    engine = _make_mapping(tmp_path, """
    defaults: {bg: room_day, outfit: casual, expr: neutral, light: natural}
    rules:
      - when:
          energy: "<0.35"
        scene:
          expr: tired
    """)
    scene = engine.compute(_state(energy=0.2), hour=12)
    assert scene.expr == "tired"


# ---------------------------------------------------------------------------
# Numeric comparison helper
# ---------------------------------------------------------------------------

def test_numeric_compare_gte():
    assert _numeric_compare(0.5, ">=0.4")
    assert not _numeric_compare(0.3, ">=0.4")


def test_numeric_compare_lt():
    assert _numeric_compare(-0.3, "<0.0")
    assert not _numeric_compare(0.1, "<0.0")


def test_numeric_compare_negative():
    assert _numeric_compare(-0.2, "<-0.1")
    assert not _numeric_compare(-0.05, "<-0.1")


# ---------------------------------------------------------------------------
# Time bucket
# ---------------------------------------------------------------------------

def test_time_bucket_morning():
    assert _time_bucket(8) == "morning"


def test_time_bucket_evening():
    assert _time_bucket(19) == "evening"


def test_time_bucket_night():
    assert _time_bucket(23) == "night"
    assert _time_bucket(3) == "night"
