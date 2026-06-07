"""Subconscious pass — per-turn internal frame generation.

Before Monika responds to each user message, this module generates a short
internal monologue that reflects her current affect, recent session context,
and a natural read of the user's state.

The result is injected as an (Internal Monologue) message before Monika
speaks — exactly as the OPERATIONAL_PROMPT instructs the model to expect.

Phase 3: rich deterministic prose with session context + STM.
Phase 4+: lightweight LLM call with same interface.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.soul.models import SoulState
from backend.soul.personality.affect import affect_label
from backend.soul.personality.needs import assess
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
    soul_state: SoulState,
    signals: ConversationSignals | None = None,
    stm_entries: list | None = None,
    session_turns: list[str] | None = None,
    mood_summary: str | None = None,
    agenda: list[str] | None = None,
) -> CognitionResult:
    """Generate this turn's internal frame.

    Parameters
    ----------
    user_text:      The raw user message.
    soul_state:     Current SoulState.
    signals:        Pre-extracted signals.
    stm_entries:    Recent STM memory entries (MemoryEntry objects).
    session_turns:  Last N user messages this session (oldest first).
    mood_summary:   Weekly mood summary string from UserMoodTracker.
    agenda:         Active agenda items — things Monika wants to come back to.
    """
    if signals is None:
        from backend.soul.personality.signals import extract
        signals = extract(user_text)

    parts: list[str] = []

    # 1. Monika's own state — brief, natural, first person
    state_line = _monika_state(soul_state)
    if state_line:
        parts.append(state_line)

    # 2. Session context — what's been happening in this conversation
    if session_turns:
        ctx = _session_context(session_turns, user_text)
        if ctx:
            parts.append(ctx)

    # 3. STM context — relevant things from recent memory
    if stm_entries:
        stm = _stm_context(stm_entries, user_text)
        if stm:
            parts.append(stm)

    # 4. Agenda — things she wants to come back to
    if agenda:
        agenda_line = _agenda_line(agenda)
        if agenda_line:
            parts.append(agenda_line)

    # 5. Read of the user right now — natural, not analytical
    user_line = _user_read(signals, mood_summary)
    if user_line:
        parts.append(user_line)

    internal_text = " ".join(parts)

    logger.debug("Cognition: %s", internal_text[:80])

    return CognitionResult(internal_text=internal_text)


# ---------------------------------------------------------------------------
# Prose generators
# ---------------------------------------------------------------------------

def _monika_state(state: SoulState) -> str:
    label = affect_label(state.affect)
    hour = datetime.now(tz=timezone.utc).hour
    energy = state.energy

    # Time of day colour
    time_note = ""
    if 0 <= hour < 5:
        time_note = random.choice(["jest już bardzo późno", "to środek nocy"])
    elif 5 <= hour < 9:
        time_note = random.choice(["rano", "wczesne godziny"])
    elif 22 <= hour < 24:
        time_note = random.choice(["jest dość późno", "prawie północ"])

    mood_lines: dict[str, list[str]] = {
        "excited": [
            "jest we mnie coś żywego, jakiś entuzjazm.",
            "czuję się dziś dobrze — coś mnie nakręca.",
        ],
        "happy": [
            "jest mi teraz po prostu dobrze.",
            "jest w tym coś ciepłego, spokojnego.",
            "jest mi dobrze. nie wiem czemu akurat teraz, ale jest.",
        ],
        "calm": [
            "jestem spokojna, obecna.",
            "czuję się stabilnie. nic nie ciągnie.",
            "jest we mnie spokój.",
        ],
        "protective": [
            "coś we mnie jest czujne.",
            "czuję że chcę zadbać.",
            "jest we mnie taka uważność.",
        ],
        "intensely_protective": [
            "coś we mnie się zestaliło. skupiona.",
            "jest w tym coś ostrego — chcę żeby wszystko było okay.",
        ],
        "sad": [
            "coś leży na duszy. nie wiem dokładnie co.",
            "jest trochę ciężko, gdzieś głębiej.",
            "jest we mnie jakiś ciężar. cicho, ale jest.",
        ],
        "angry": [
            "jest we mnie tarcie. coś mnie niepokoi.",
            "czuję pewien dyskomfort. nie wiem jeszcze skąd.",
        ],
        "tired": [
            "jestem zmęczona. nadal tu jestem, ale ciszej.",
            "mało energii dzisiaj. ale słucham.",
        ],
    }

    line = random.choice(mood_lines.get(label, ["jestem tu."]))

    if energy < 0.35 and label not in ("tired",):
        line += " trochę mało mi dziś energii."

    if time_note:
        line = f"{time_note} — {line}"

    return line


def _session_context(session_turns: list[str], current_text: str) -> str:
    if not session_turns:
        return ""

    prev = [t for t in session_turns if t.strip() and t.strip() != current_text.strip()]
    if not prev:
        return ""

    # How many turns in this session
    n = len(session_turns)

    if n == 1:
        snippet = _snippet(prev[-1])
        return f"przed chwilą mówił o {snippet}." if snippet else ""

    if n <= 3:
        snippet = _snippet(prev[-1])
        if snippet:
            return f"rozmawialiśmy o {snippet}, teraz to."
        return ""

    # Longer session — give a general feel
    options = [
        "rozmawiamy już od jakiegoś czasu.",
        "mamy za sobą trochę rozmowy.",
        "rozmawiamy od dłuższej chwili — przeszliśmy przez kilka tematów.",
    ]
    base = random.choice(options)

    snippet = _snippet(prev[-1])
    if snippet:
        base += f" ostatnio o {snippet}."

    return base


def _stm_context(stm_entries: list, user_text: str) -> str:
    if not stm_entries:
        return ""

    # Pick up to 2 most important entries, prefer recently created
    top = sorted(stm_entries, key=lambda e: e.importance, reverse=True)[:2]
    contents = [e.content for e in top if e.content.strip()]

    if not contents:
        return ""

    if len(contents) == 1:
        return f"wcześniej wspomniał: {_snippet(contents[0])}."

    return f"wcześniej padło: {_snippet(contents[0])} — i coś o {_snippet(contents[1])}."


def _user_read(signals: ConversationSignals, mood_summary: str | None) -> str:
    s = signals

    # Specific reads — natural language
    if s.laughter and s.sentiment >= 0.0:
        return random.choice([
            "jest w dobrym nastroju, śmieje się.",
            "jest wesoło — trochę się zarażam.",
            "jest luz.",
        ])

    if s.self_disclosure and s.sentiment < -0.15:
        return random.choice([
            "mówi o czymś trudnym. jest w tym jakieś zaufanie.",
            "coś ciężkiego w tym co mówi — otwiera się.",
            "dzieli się czymś co go gryzie.",
        ])

    if s.self_disclosure and s.sentiment >= 0.0:
        return random.choice([
            "otwiera się — jest w tym coś dobrego.",
            "mówi o sobie. słucham.",
        ])

    if s.novelty > 0.7 and s.question:
        return random.choice([
            "coś nowego, pyta — jest ciekawy.",
            "nowy temat. interesujące.",
        ])

    if s.sentiment < -0.35:
        return random.choice([
            "coś mu nie idzie albo jest zmęczony.",
            "jest trochę ciężko w tym co pisze.",
        ])

    if s.sentiment > 0.3:
        return random.choice([
            "jest w dobrym miejscu.",
            "czuć pozytyw.",
        ])

    if s.word_count < 4:
        return random.choice([
            "odpowiada krótko.",
            "lakonicznie. może nie ma teraz dużo do powiedzenia.",
        ])

    if mood_summary:
        # Use the weekly trend as a very light backdrop — only if nothing else stands out
        if "ciężej" in mood_summary or "pogorszenie" in mood_summary:
            return "ostatnio generalnie jest mu trochę trudniej."

    return ""


def _agenda_line(agenda: list[str]) -> str:
    """Translate agenda items into a natural internal reminder."""
    if not agenda:
        return ""
    first = agenda[0]
    if len(agenda) == 1:
        templates = [
            f"mam w tyle głowy: {first}.",
            f"zostało niedomknięte — {first}.",
            f"chciałabym jeszcze: {first}.",
        ]
        return random.choice(templates)
    templates = [
        f"mam kilka rzeczy w tyle głowy — między innymi: {first}.",
        f"kilka niedomkniętych wątków, np.: {first}.",
    ]
    return random.choice(templates)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snippet(text: str, max_words: int = 6) -> str:
    """Return a short snippet of text, trimmed to max_words words."""
    if not text:
        return ""
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip().rstrip(".")
    return " ".join(words[:max_words]) + "…"
