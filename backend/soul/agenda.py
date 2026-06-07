"""Agenda — things Monika wants to say or ask.

Monika notices threads worth following up on. This module tracks them
across turns within a session so she can return to them naturally.

Items expire after max_turns if not acted on.
The manager caps at 3 active items — oldest dropped when full.

Usage:
    manager = AgendaManager()
    new_items = manager.extract_from_turn(user_text, signals)
    manager.add_items(new_items)
    manager.age()          # call each turn
    active = manager.active()  # list[str] — injected into Internal Monologue
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from backend.soul.personality.signals import ConversationSignals

_MAX_ITEMS = 3
_DEFAULT_TTL = 7   # turns before item expires if not acted on

# Broader personal markers than signals._SELF_DISCLOSURE — includes "mam", "miałem", etc.
_PERSONAL = frozenset({
    "mam", "miałem", "miałam", "mam", "mamy", "czuję", "czuje", "myślę", "mysle",
    "boję", "martwię", "martwi", "chcę", "chce", "potrzebuję", "potrzebuje",
    "jestem", "byłem", "byłam", "było", "jest mi", "mi się", "mnie",
    "problem", "sprawa", "kłopot", "klopot", "trouble", "issue", "worried",
    "stressed", "stres", "trudno", "ciężko", "ciezko",
})


@dataclass
class AgendaItem:
    text: str             # natural Polish phrase: "zapytać jak mu idzie z projektem"
    turns_alive: int = 0
    max_turns: int = _DEFAULT_TTL


class AgendaManager:
    """Manages Monika's in-session agenda — things she wants to come back to."""

    def __init__(self) -> None:
        self._items: list[AgendaItem] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def active(self) -> list[str]:
        """Return texts of all active (non-expired) agenda items."""
        return [i.text for i in self._items]

    def age(self) -> None:
        """Increment turn counter, remove expired items. Call once per turn."""
        self._items = [
            item for item in self._items
            if item.turns_alive < item.max_turns
        ]
        for item in self._items:
            item.turns_alive += 1

    def add_items(self, texts: list[str]) -> None:
        """Add new agenda items. Silently drops duplicates and overflow."""
        existing = {i.text for i in self._items}
        for text in texts:
            if text in existing:
                continue
            if len(self._items) >= _MAX_ITEMS:
                self._items.pop(0)   # drop oldest
            self._items.append(AgendaItem(text=text))
            existing.add(text)

    def extract_from_turn(
        self,
        user_text: str,
        signals: ConversationSignals,
    ) -> list[str]:
        """Decide what new agenda items this turn should generate, if any.

        Returns a list of natural Polish strings (may be empty).
        """
        new_items: list[str] = []
        text_lower = user_text.lower()
        is_personal = signals.self_disclosure or any(w in text_lower for w in _PERSONAL)

        # Personal + negative: emotional thread worth following up
        if is_personal and signals.sentiment < -0.1:
            item = _make_followup(user_text, kind="emotional")
            if item:
                new_items.append(item)

        # Personal + brief: mentioned something without elaborating
        elif is_personal and signals.word_count <= 14:
            item = _make_followup(user_text, kind="brief")
            if item:
                new_items.append(item)

        # High novelty + question: new interesting topic to explore
        elif signals.novelty > 0.7 and signals.question and signals.word_count > 5:
            item = _make_followup(user_text, kind="curious")
            if item:
                new_items.append(item)

        return new_items


# ---------------------------------------------------------------------------
# Item generators
# ---------------------------------------------------------------------------

def _make_followup(user_text: str, kind: str) -> str | None:
    snippet = _topic_snippet(user_text)
    if not snippet:
        return None

    if kind == "emotional":
        templates = [
            f"wrócić do tego co powiedział o {snippet}",
            f"zapytać jak teraz z tym {snippet}",
            f"sprawdzić czy jest OK z {snippet}",
        ]
    elif kind == "brief":
        templates = [
            f"zapytać więcej o {snippet}",
            f"wrócić do {snippet} — powiedział krótko",
            f"drążyć temat {snippet}",
        ]
    else:  # curious
        templates = [
            f"wrócić do pytania o {snippet}",
            f"pociągnąć temat {snippet}",
        ]

    return random.choice(templates)


def _topic_snippet(text: str, max_words: int = 4) -> str:
    """Extract a short topical snippet from user text for the agenda item."""
    if not text:
        return ""
    stop = {
        "że", "to", "się", "jest", "nie", "jak", "i", "a", "w", "na",
        "do", "z", "po", "ale", "czy", "bo", "już", "tak", "co", "ten",
        "tej", "tego", "tym", "taki", "takie", "taka", "ale", "oraz",
        "teraz", "wcześniej", "potem", "później", "dzisiaj", "dziś", "jutro",
        "bardzo", "trochę", "troche", "jakiś", "jakis", "jakieś", "właśnie",
        "mam", "masz", "mamy", "mają", "miałem", "miałam", "było", "będę",
        "the", "is", "it", "and", "or", "an", "that", "this", "was", "but",
    }
    words = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+", text)
    content = [w.lower() for w in words if w.lower() not in stop and len(w) > 2]
    if not content:
        return ""
    return " ".join(content[:max_words])
