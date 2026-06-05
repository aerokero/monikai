"""Tests for needs-driven proactivity engine."""

from __future__ import annotations

import pytest

from backend.progression.proactivity import ProactivityAction, evaluate
from backend.soul.models import Affect, Needs, SoulState
from backend.soul.personality.needs import RELATEDNESS_THRESHOLD, COMPETENCE_THRESHOLD


def _state(energy: float = 0.7) -> SoulState:
    return SoulState(affect=Affect(), needs=Needs(), energy=energy)


def test_no_action_when_needs_balanced():
    needs = Needs(relatedness=0.8, autonomy=0.8, competence=0.8)
    action = evaluate(needs)
    assert action is None


def test_relatedness_unmet_returns_reach_out():
    needs = Needs(relatedness=RELATEDNESS_THRESHOLD - 0.1)
    action = evaluate(needs)
    assert action is not None
    assert action.kind == "reach_out"
    assert action.need == "relatedness"


def test_competence_unmet_returns_offer_help():
    needs = Needs(relatedness=0.8, competence=COMPETENCE_THRESHOLD - 0.1)
    action = evaluate(needs)
    assert action is not None
    assert action.kind == "offer_help"


def test_relatedness_takes_priority_over_competence():
    needs = Needs(
        relatedness=RELATEDNESS_THRESHOLD - 0.1,
        competence=COMPETENCE_THRESHOLD - 0.1,
    )
    action = evaluate(needs)
    assert action.kind == "reach_out"


def test_low_energy_suppresses_proactivity():
    needs = Needs(relatedness=0.1)  # very low
    state = _state(energy=0.2)
    action = evaluate(needs, soul_state=state)
    assert action is None


def test_urgency_increases_with_deficit():
    mild = Needs(relatedness=RELATEDNESS_THRESHOLD - 0.05)
    severe = Needs(relatedness=0.1)

    a_mild = evaluate(mild)
    a_severe = evaluate(severe)

    assert a_mild is not None
    assert a_severe is not None
    assert a_severe.urgency > a_mild.urgency


def test_urgency_capped_at_one():
    needs = Needs(relatedness=0.0)
    action = evaluate(needs)
    assert action is not None
    assert action.urgency <= 1.0


def test_action_has_context():
    needs = Needs(relatedness=0.1)
    action = evaluate(needs)
    assert action.context
    assert len(action.context) > 10


async def test_ritual_suggestion_from_needs(tmp_db):
    from backend.progression.rituals import RitualEngine
    from backend.soul.models import Needs

    engine = RitualEngine()
    # Low relatedness should suggest evening_checkin
    needs = Needs(relatedness=0.3, competence=0.7, autonomy=0.7)
    suggestions = engine.suggest(needs)
    assert len(suggestions) > 0
    kinds = [s.kind for s in suggestions]
    assert any("check-in" in k or "hello" in k or "message" in k for k in kinds)


async def test_ritual_completion_emits_event(tmp_db):
    from backend.progression.rituals import RitualEngine
    from backend.soul.events import EventBus, RitualCompleted

    bus = EventBus()
    engine = RitualEngine(event_bus=bus)

    completed = []
    async def on_ritual(e: RitualCompleted) -> None:
        completed.append(e.task_id)
    bus.subscribe(RitualCompleted, on_ritual)

    await engine.complete("evening_checkin", db_path=tmp_db)
    assert "evening_checkin" in completed


async def test_ritual_sync_to_db(tmp_db):
    from backend.progression.rituals import RitualEngine
    from backend.progression.state import get_active_rituals
    from backend.soul.models import Needs

    engine = RitualEngine()
    needs = Needs(relatedness=0.2)
    await engine.sync_to_db(needs, db_path=tmp_db)

    rituals = await get_active_rituals(db_path=tmp_db)
    assert len(rituals) > 0
