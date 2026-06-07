"""Subconscious pass — per-turn internal frame generation.

Before Monika responds to each user message, this module generates a short
internal monologue that reflects her current state, recent session context,
and a natural read of the user's state.

The result is injected as an (Internal Monologue) message before Monika speaks.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.soul.personality.signals import ConversationSignals

logger = logging.getLogger(__name__)


@dataclass
class CognitionResult:
    """Output of one subconscious pass."""
    internal_text: str

    def as_message(self) -> str:
        return f"(Internal Monologue) {self.internal_text}"


async def generate(
    user_text: str,
    signals: ConversationSignals | None = None,
    stm_entries: list | None = None,
    session_turns: list[str] | None = None,
    agenda: list[str] | None = None,
) -> CognitionResult:
    """Generate this turn's internal frame."""
    if signals is None:
        from backend.soul.personality.signals import extract
        signals = extract(user_text)

    parts: list[str] = []

    # 1. Time-of-day colour
    state_line = _time_state()
    if state_line:
        parts.append(state_line)

    # 2. Session context — what's been happening in this conversation
    if session_turns:
        ctx = _session_context(session_turns, user_text)
        if ctx:
            parts.append(ctx)

    # 3. STM context — relevant things from recent memory
    if stm_entries:
        stm = _stm_context(stm_entries)
        if stm:
            parts.append(stm)

    # 4. Agenda — things she wants to come back to
    if agenda:
        agenda_line = _agenda_line(agenda)
        if agenda_line:
            parts.append(agenda_line)

    # 5. Read of the user right now
    user_line = _user_read(signals)
    if user_line:
        parts.append(user_line)

    internal_text = " ".join(parts)
    logger.debug("Cognition: %s", internal_text[:80])
    return CognitionResult(internal_text=internal_text)


# ---------------------------------------------------------------------------
# Prose generators
# ---------------------------------------------------------------------------

def _time_state() -> str:
    hour = datetime.now(tz=timezone.utc).hour
    if 0 <= hour < 5:
        return random.choice(["jest już bardzo późno.", "to środek nocy."])
    if 5 <= hour < 9:
        return random.choice(["rano.", "wczesne godziny."])
    if 22 <= hour < 24:
        return random.choice(["jest dość późno.", "prawie północ."])
    return ""


def _session_context(session_turns: list[str], current_text: str) -> str:
    prev = [t for t in session_turns if t.strip() and t.strip() != current_text.strip()]
    if not prev:
        return ""

    n = len(session_turns)
    if n == 1:
        snippet = _snippet(prev[-1])
        return f"przed chwilą mówił o {snippet}." if snippet else ""
    if n <= 3:
        snippet = _snippet(prev[-1])
        return f"rozmawialiśmy o {snippet}, teraz to." if snippet else ""

    base = random.choice([
        "rozmawiamy już od jakiegoś czasu.",
        "mamy za sobą trochę rozmowy.",
        "przeszliśmy przez kilka tematów.",
    ])
    snippet = _snippet(prev[-1])
    if snippet:
        base += f" ostatnio o {snippet}."
    return base


def _stm_context(stm_entries: list) -> str:
    top = sorted(stm_entries, key=lambda e: e.importance, reverse=True)[:2]
    contents = [e.content for e in top if e.content.strip()]
    if not contents:
        return ""
    if len(contents) == 1:
        return f"wcześniej wspomniał: {_snippet(contents[0])}."
    return f"wcześniej padło: {_snippet(contents[0])} — i coś o {_snippet(contents[1])}."


def _user_read(signals: ConversationSignals) -> str:
    s = signals

    if s.laughter and s.sentiment >= 0.0:
        return random.choice(["jest w dobrym nastroju.", "jest luz.", "jest wesoło."])

    if s.self_disclosure and s.sentiment < -0.15:
        return random.choice([
            "mówi o czymś trudnym. jest w tym jakieś zaufanie.",
            "coś ciężkiego w tym co mówi — otwiera się.",
        ])

    if s.self_disclosure and s.sentiment >= 0.0:
        return random.choice(["otwiera się — jest w tym coś dobrego.", "mówi o sobie. słucham."])

    if s.novelty > 0.7 and s.question:
        return random.choice(["coś nowego, pyta — jest ciekawy.", "nowy temat."])

    if s.sentiment < -0.35:
        return random.choice(["coś mu nie idzie albo jest zmęczony.", "jest trochę ciężko w tym co pisze."])

    if s.sentiment > 0.3:
        return random.choice(["jest w dobrym miejscu.", "czuć pozytyw."])

    if s.word_count < 4:
        return random.choice(["odpowiada krótko.", "lakonicznie."])

    return ""


def _agenda_line(agenda: list[str]) -> str:
    if not agenda:
        return ""
    first = agenda[0]
    if len(agenda) == 1:
        return random.choice([
            f"mam w tyle głowy: {first}.",
            f"zostało niedomknięte — {first}.",
            f"chciałabym jeszcze: {first}.",
        ])
    return random.choice([
        f"mam kilka rzeczy w tyle głowy — między innymi: {first}.",
        f"kilka niedomkniętych wątków, np.: {first}.",
    ])


def _snippet(text: str, max_words: int = 6) -> str:
    if not text:
        return ""
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip().rstrip(".")
    return " ".join(words[:max_words]) + "…"
