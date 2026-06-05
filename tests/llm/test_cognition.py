"""Tests for the subconscious cognition pass."""

from __future__ import annotations

import pytest

from backend.llm.cognition import CognitionResult, generate
from backend.soul.models import Affect, Needs, SoulState
from backend.soul.personality.signals import ConversationSignals


def _state(
    pleasure: float = 0.1,
    arousal: float = 0.5,
    dominance: float = 0.0,
    energy: float = 0.7,
    register: str = "casual",
) -> SoulState:
    return SoulState(
        affect=Affect(pleasure=pleasure, arousal=arousal, dominance=dominance),
        needs=Needs(),
        energy=energy,
        active_register=register,
    )


def _signals(
    sentiment: float = 0.0,
    self_disclosure: bool = False,
    laughter: bool = False,
    question: bool = False,
    novelty: float = 0.5,
    word_count: int = 10,
) -> ConversationSignals:
    return ConversationSignals(
        sentiment=sentiment,
        self_disclosure=self_disclosure,
        question=question,
        novelty=novelty,
        arousal_hint=0.0,
        laughter=laughter,
        word_count=word_count,
        length_score=min(1.0, word_count / 20.0),
    )


async def test_generate_returns_cognition_result():
    state = _state()
    result = await generate("Cześć!", state)
    assert isinstance(result, CognitionResult)
    assert result.affect_read
    assert result.tom_read
    assert result.intent
    assert result.internal_text


async def test_as_message_format():
    state = _state()
    result = await generate("test", state)
    msg = result.as_message()
    assert msg.startswith("(Internal Monologue)")
    assert result.internal_text in msg


async def test_cognition_uses_provided_signals():
    state = _state()
    signals = _signals(self_disclosure=True, sentiment=-0.5)
    result = await generate("czuję się źle", state, signals=signals)
    # With self_disclosure + negative sentiment → protective/heavy ToM read
    assert "ciężkim" in result.tom_read or "trudno" in result.tom_read.lower() or "zaufanie" in result.tom_read


async def test_cognition_protective_register():
    state = _state(pleasure=-0.3, dominance=0.4, register="protective")
    result = await generate("Mam ciężki dzień.", state)
    assert "być" in result.intent.lower() or "naprawiać" in result.intent.lower()


async def test_cognition_intellectual_register():
    state = _state(register="intellectual")
    signals = _signals(question=True, novelty=0.8)
    result = await generate("Jak działa pamięć neuronowa?", state, signals=signals)
    assert "eksplorować" in result.intent or "razem" in result.intent


async def test_cognition_laughter_tom():
    state = _state()
    signals = _signals(laughter=True, sentiment=0.5)
    result = await generate("haha to super xD", state, signals=signals)
    assert "nastrój" in result.tom_read or "śmiać" in result.tom_read


async def test_cognition_empty_text_no_crash():
    state = _state()
    result = await generate("", state)
    assert isinstance(result, CognitionResult)
    assert result.internal_text


async def test_cognition_low_energy_reflected():
    state = _state(energy=0.2)
    result = await generate("test", state)
    assert "zmęczona" in result.affect_read


async def test_cognition_high_energy_reflected():
    state = _state(energy=0.9, pleasure=0.5, arousal=0.6)
    result = await generate("super dzień mam!", state)
    # High energy + good affect → positive affect read
    assert "energię" in result.affect_read or "ciepło" in result.affect_read or "pobudzona" in result.affect_read


async def test_cognition_relatedness_unmet_drives_intent():
    state = SoulState(
        affect=Affect(),
        needs=Needs(relatedness=0.2),  # below threshold
        energy=0.7,
        active_register="casual",
    )
    result = await generate("ok", state)
    # With low relatedness, intent should mention connection
    assert "zbliżyć" in result.intent or "pytanie" in result.intent
