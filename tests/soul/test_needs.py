"""Tests for the SDT needs engine."""

from __future__ import annotations

import pytest

from backend.soul.models import Needs
from backend.soul.personality.needs import (
    NeedsStatus,
    assess,
    decay_daily,
    decay_session,
    update_from_turn,
    RELATEDNESS_THRESHOLD,
    AUTONOMY_THRESHOLD,
    COMPETENCE_THRESHOLD,
)
from backend.soul.personality.signals import ConversationSignals


def _signals(
    sentiment: float = 0.0,
    self_disclosure: bool = False,
    question: bool = False,
    novelty: float = 0.5,
    length_score: float = 0.5,
    laughter: bool = False,
    arousal_hint: float = 0.0,
    word_count: int = 10,
) -> ConversationSignals:
    return ConversationSignals(
        sentiment=sentiment,
        self_disclosure=self_disclosure,
        question=question,
        novelty=novelty,
        arousal_hint=arousal_hint,
        laughter=laughter,
        word_count=word_count,
        length_score=length_score,
    )


def test_relatedness_grows_from_disclosure():
    needs = Needs(relatedness=0.5)
    updated = update_from_turn(needs, _signals(self_disclosure=True))
    assert updated.relatedness > needs.relatedness


def test_relatedness_drops_on_negative_exchange():
    needs = Needs(relatedness=0.5)
    updated = update_from_turn(needs, _signals(sentiment=-0.6))
    assert updated.relatedness < needs.relatedness


def test_autonomy_grows_from_reciprocity():
    needs = Needs(autonomy=0.5)
    updated = update_from_turn(needs, _signals(), reciprocity=True)
    assert updated.autonomy > needs.autonomy


def test_competence_grows_on_positive_response():
    needs = Needs(competence=0.5)
    updated = update_from_turn(needs, _signals(sentiment=0.6))
    assert updated.competence > needs.competence


def test_delta_is_capped_per_turn():
    needs = Needs(relatedness=0.5)
    # A single very intense turn shouldn't jump more than 0.04
    updated = update_from_turn(
        needs,
        _signals(self_disclosure=True, sentiment=1.0, length_score=1.0),
    )
    assert (updated.relatedness - needs.relatedness) <= 0.04 + 1e-9


def test_values_clamped_to_unit():
    needs = Needs(relatedness=0.99, autonomy=0.99, competence=0.99)
    for _ in range(20):
        needs = update_from_turn(needs, _signals(self_disclosure=True, sentiment=1.0), reciprocity=True)
    assert needs.relatedness <= 1.0
    assert needs.autonomy <= 1.0
    assert needs.competence <= 1.0


def test_decay_session_nudges_toward_midpoint():
    high = Needs(relatedness=0.9, autonomy=0.9, competence=0.9)
    decayed = decay_session(high)
    assert decayed.relatedness < high.relatedness
    assert decayed.relatedness > 0.5


def test_decay_daily_drops_relatedness():
    needs = Needs(relatedness=0.8, autonomy=0.7, competence=0.7)
    decayed = decay_daily(needs, days_elapsed=3.0)
    assert decayed.relatedness < needs.relatedness


def test_assess_all_ok():
    needs = Needs(relatedness=0.8, autonomy=0.7, competence=0.7)
    status = assess(needs)
    assert not status.any_unmet


def test_assess_relatedness_unmet():
    needs = Needs(relatedness=RELATEDNESS_THRESHOLD - 0.1)
    status = assess(needs)
    assert status.relatedness_unmet
    assert status.priority_need == "relatedness"


def test_assess_competence_unmet():
    needs = Needs(relatedness=0.7, autonomy=0.7, competence=COMPETENCE_THRESHOLD - 0.1)
    status = assess(needs)
    assert status.competence_unmet


def test_assess_priority_relatedness_over_competence():
    needs = Needs(
        relatedness=RELATEDNESS_THRESHOLD - 0.1,
        competence=COMPETENCE_THRESHOLD - 0.1,
    )
    status = assess(needs)
    assert status.priority_need == "relatedness"
