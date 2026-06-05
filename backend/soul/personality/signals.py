"""Conversation quality signal extraction.

Analyses a single user utterance and returns structured signals that feed
the affect model and needs engine. Kept from personality.py (cleaned up).

The extractor is stateless; novelty requires a rolling token window that
callers maintain (ConversationHistory). This keeps each component testable.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

_WORD_RE = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9']+")

_SELF_DISCLOSURE = frozenset({
    "czuję", "czuje", "myślę", "mysle", "boję", "boje", "martwi", "martwię",
    "tęsknię", "tesknie", "pragnę", "pragne", "chcę", "chce", "potrzebuję",
    "potrzebuje", "zależy", "zalezy", "smutno", "radość", "radosc",
    "jestem", "byłem", "byłam", "trudno", "mam dość", "mam dosc",
    "feel", "think", "afraid", "miss", "need", "want", "hate", "love",
    "i am", "i was", "i feel",
})

_POSITIVE = frozenset({
    "dziękuję", "dziekuje", "fajnie", "super", "świetnie", "swietnie",
    "kocham", "lubię", "lubie", "miło", "milo", "cieszę", "ciesze",
    "dobrze", "lepiej", "spoko", "wdzięczny", "wdzieczny",
    "thanks", "great", "awesome", "love", "nice", "happy", "wonderful",
})

_NEGATIVE = frozenset({
    "źle", "zle", "smutno", "wkurza", "wkurzony", "wkurzona", "nienawidzę",
    "nienawidze", "stres", "boję", "boje", "samotny", "samotna",
    "zły", "zla", "puste", "męczy", "meczy",
    "bad", "hate", "awful", "terrible", "sad", "angry", "tired", "empty",
})

_LAUGHTER = frozenset({"haha", "hehe", "ahaha", "ehehe", "lol", "xd"})

_QUESTION_WORDS = frozenset({
    "dlaczego", "co", "jak", "czy", "kiedy", "gdzie", "po co", "ile",
    "why", "what", "how", "when", "where", "who", "which",
})


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


@dataclass
class ConversationSignals:
    """Quality signals extracted from one user utterance."""
    sentiment: float       # -1.0 … 1.0 (positive / negative)
    self_disclosure: bool  # shared something personal
    question: bool         # asked a question
    novelty: float         # 0.0 … 1.0 — topic freshness vs. recent history
    arousal_hint: float    # 0.0 … 1.0 — exclamation, caps
    laughter: bool
    word_count: int
    length_score: float    # 0.0 … 1.0 (saturates at ~20 words)
    tokens: list[str] = field(default_factory=list, repr=False)


def extract(
    text: str,
    recent_tokens: Deque[frozenset[str]] | None = None,
) -> ConversationSignals:
    """Extract conversation quality signals from a user utterance.

    Parameters
    ----------
    text:          Raw user message.
    recent_tokens: Rolling window of frozenset[tokens] from recent turns.
                   Pass a deque(maxlen=6) maintained by the caller.
                   If None, novelty defaults to 0.5.
    """
    if not text:
        return ConversationSignals(
            sentiment=0.0, self_disclosure=False, question=False,
            novelty=0.5, arousal_hint=0.0, laughter=False,
            word_count=0, length_score=0.0, tokens=[],
        )

    tokens = _tokenize(text)
    token_set = frozenset(tokens)
    text_lower = text.lower()

    # --- Sentiment ---
    pos = sum(1 for t in tokens if t in _POSITIVE)
    neg = sum(1 for t in tokens if t in _NEGATIVE)
    sentiment = float(pos - neg) / max(3, pos + neg + 1)
    sentiment = max(-1.0, min(1.0, sentiment))

    # --- Self-disclosure ---
    self_disclosure = any(w in text_lower for w in _SELF_DISCLOSURE)

    # --- Question ---
    question = "?" in text or any(q in text_lower for q in _QUESTION_WORDS)

    # --- Arousal hint (exclamation + all-caps ratio) ---
    exclaim = text.count("!")
    letters = sum(1 for c in text if c.isalpha())
    caps = sum(1 for c in text if c.isupper())
    caps_ratio = (caps / letters) if letters else 0.0
    arousal_hint = min(1.0, exclaim * 0.08 + caps_ratio * 0.4)

    # --- Laughter ---
    laughter = any(t in _LAUGHTER for t in tokens) or "xD" in text

    # --- Novelty ---
    if recent_tokens and len(recent_tokens) > 0:
        recent = frozenset().union(*recent_tokens)
        overlap = len(token_set & recent) / max(1, len(token_set)) if token_set else 0.0
        novelty = max(0.0, min(1.0, 1.0 - overlap))
    else:
        novelty = 0.5

    # --- Length ---
    word_count = len(tokens)
    length_score = min(1.0, word_count / 20.0)

    return ConversationSignals(
        sentiment=sentiment,
        self_disclosure=self_disclosure,
        question=question,
        novelty=novelty,
        arousal_hint=arousal_hint,
        laughter=laughter,
        word_count=word_count,
        length_score=length_score,
        tokens=tokens,
    )


class SignalHistory:
    """Rolling window of recent token sets for novelty computation."""

    def __init__(self, maxlen: int = 6) -> None:
        self._window: Deque[frozenset[str]] = deque(maxlen=maxlen)

    def push(self, signals: ConversationSignals) -> None:
        self._window.append(frozenset(signals.tokens))

    @property
    def recent_tokens(self) -> Deque[frozenset[str]]:
        return self._window

    def extract(self, text: str) -> ConversationSignals:
        """Extract signals using current history, then update history."""
        sig = extract(text, self._window)
        self.push(sig)
        return sig
