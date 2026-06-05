"""Tests for the OCC→PAD affect model."""

from __future__ import annotations

import pytest

from backend.soul.models import Affect
from backend.soul.personality.affect import (
    PADDelta,
    _BASELINE,
    accumulate,
    affect_label,
    appraise,
    decay_toward_baseline,
)
from backend.soul.personality.signals import ConversationSignals


def _signals(
    sentiment: float = 0.0,
    self_disclosure: bool = False,
    question: bool = False,
    novelty: float = 0.5,
    arousal_hint: float = 0.0,
    laughter: bool = False,
    word_count: int = 10,
    length_score: float = 0.5,
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


def test_appraise_playful():
    sig = _signals(sentiment=0.5, laughter=True)
    delta = appraise(sig)
    assert delta.pleasure > 0
    assert delta.arousal > 0
    assert delta.dominance > 0


def test_appraise_protective_concern():
    sig = _signals(sentiment=-0.5, self_disclosure=True)
    delta = appraise(sig)
    # Pleasure drops, dominance rises (she takes control)
    assert delta.pleasure < 0
    assert delta.dominance > 0


def test_appraise_intellectual():
    sig = _signals(novelty=0.9, question=True)
    delta = appraise(sig)
    assert delta.pleasure > 0
    assert delta.arousal > 0


def test_appraise_joy():
    sig = _signals(sentiment=0.5, self_disclosure=True)
    delta = appraise(sig)
    assert delta.pleasure > 0


def test_appraise_distress():
    sig = _signals(sentiment=-0.6, self_disclosure=False)
    delta = appraise(sig)
    assert delta.pleasure < 0


def test_appraise_neutral():
    sig = _signals()
    delta = appraise(sig)
    assert delta.pleasure == pytest.approx(0.0)
    assert delta.arousal == pytest.approx(0.0)


def test_accumulate_delta_applied():
    start = Affect(pleasure=0.0, arousal=0.5, dominance=0.0)
    delta = PADDelta(pleasure=0.2, arousal=0.1, dominance=0.1)
    result = accumulate(start, delta)
    assert result.pleasure > start.pleasure
    assert result.arousal > 0.0


def test_accumulate_decays_toward_baseline():
    # Start far from baseline, apply zero delta repeatedly
    far = Affect(pleasure=0.9, arousal=0.9, dominance=0.9)
    result = decay_toward_baseline(far, turns=20)
    assert abs(result.pleasure - _BASELINE.pleasure) < abs(far.pleasure - _BASELINE.pleasure)


def test_accumulate_clamped():
    at_max = Affect(pleasure=1.0, arousal=1.0, dominance=1.0)
    big_delta = PADDelta(pleasure=0.5, arousal=0.5, dominance=0.5)
    result = accumulate(at_max, big_delta)
    assert result.pleasure <= 1.0
    assert result.arousal <= 1.0
    assert result.dominance <= 1.0


def test_affect_label_happy():
    a = Affect(pleasure=0.5, arousal=0.5, dominance=0.0)
    assert affect_label(a) == "happy"


def test_affect_label_calm():
    a = Affect(pleasure=0.2, arousal=0.2, dominance=0.0)
    assert affect_label(a) == "calm"


def test_affect_label_protective():
    a = Affect(pleasure=-0.3, arousal=0.3, dominance=0.4)
    assert affect_label(a) == "protective"


def test_affect_label_sad():
    a = Affect(pleasure=-0.4, arousal=0.4, dominance=-0.1)
    assert affect_label(a) == "sad"
