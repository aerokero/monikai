"""Tests for conversation signal extraction."""

from __future__ import annotations

import pytest
from collections import deque

from backend.soul.personality.signals import ConversationSignals, SignalHistory, extract


def test_empty_text():
    s = extract("")
    assert s.word_count == 0
    assert s.sentiment == 0.0
    assert s.self_disclosure is False


def test_positive_sentiment():
    s = extract("dziękuję, to było świetne, lubię to!")
    assert s.sentiment > 0


def test_negative_sentiment():
    s = extract("Czuję się źle, wszystko mnie wkurza i jest smutno.")
    assert s.sentiment < 0


def test_self_disclosure():
    s = extract("Czuję, że ostatnio jest mi ciężko.")
    assert s.self_disclosure is True


def test_no_self_disclosure():
    s = extract("Jaka jest pogoda w Warszawie?")
    assert s.self_disclosure is False


def test_question_detected_mark():
    s = extract("Co o tym myślisz?")
    assert s.question is True


def test_question_detected_keyword():
    s = extract("Dlaczego to tak działa")
    assert s.question is True


def test_no_question():
    s = extract("Rozumiem, dziękuję.")
    assert s.question is False


def test_laughter_detected():
    s = extract("haha to było super xD")
    assert s.laughter is True


def test_laughter_case_sensitive():
    s = extract("to było xD niesamowite")
    assert s.laughter is True


def test_length_score_short():
    s = extract("ok")
    assert s.length_score < 0.2


def test_length_score_long():
    s = extract(" ".join(["word"] * 30))
    assert s.length_score == pytest.approx(1.0)


def test_novelty_no_history():
    s = extract("brand new topic", recent_tokens=None)
    assert s.novelty == pytest.approx(0.5)


def test_novelty_with_fresh_history():
    history = deque([frozenset(["other", "words"])], maxlen=6)
    s = extract("completely different content", recent_tokens=history)
    assert s.novelty > 0.7


def test_novelty_with_repeated_history():
    tokens = frozenset(["completely", "different", "content"])
    history = deque([tokens], maxlen=6)
    s = extract("completely different content", recent_tokens=history)
    assert s.novelty < 0.3


def test_signal_history_extract_and_push():
    h = SignalHistory(maxlen=3)
    s1 = h.extract("pierwsze zdanie tutaj jakiś tekst")
    s2 = h.extract("pierwsze zdanie tutaj jakiś tekst")
    # Second identical message should have lower novelty
    assert s2.novelty < s1.novelty


def test_arousal_hint_exclamation():
    s = extract("Tak!!! Niesamowite!!!")
    assert s.arousal_hint > 0.2
