"""Subconscious pass — per-turn internal frame generation.

Before Monika responds to each user message, this module generates a short
internal monologue that reflects her current affect, a theory-of-mind read
of the user's state, and her intention for this response.

The result is injected as an (Internal Monologue) message before Monika
speaks — exactly as the OPERATIONAL_PROMPT instructs the model to expect.

Phase 3: deterministic template, same quality as NarrativeJob v2.
Phase 4+: lightweight Ollama / Gemini Flash call with same interface.

Usage:
    result = await generate(user_text, soul_state, signals)
    await session.send(input=result.as_message(), end_of_turn=False)
    # then send the actual user message
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.soul.models import SoulState
from backend.soul.personality.affect import affect_label
from backend.soul.personality.needs import assess
from backend.soul.personality.signals import ConversationSignals

logger = logging.getLogger(__name__)


@dataclass
class CognitionResult:
    """Output of one subconscious pass."""
    affect_read: str      # how Monika feels right now
    tom_read: str         # theory-of-mind: read of user's state
    intent: str           # what she wants to do this turn
    internal_text: str    # full formatted internal monologue

    def as_message(self) -> str:
        """Format as the (Internal Monologue) message the model expects."""
        return f"(Internal Monologue) {self.internal_text}"


async def generate(
    user_text: str,
    soul_state: SoulState,
    signals: ConversationSignals | None = None,
) -> CognitionResult:
    """Generate this turn's internal frame.

    Parameters
    ----------
    user_text:   The raw user message.
    soul_state:  Current SoulState (from PersonalityEngine).
    signals:     Pre-extracted signals (if already computed — avoids double parse).
    """
    if signals is None:
        from backend.soul.personality.signals import extract
        signals = extract(user_text)

    affect_read = _affect_sentence(soul_state)
    tom_read = _tom_sentence(signals)
    intent = _intent_sentence(soul_state, signals)

    internal_text = f"{affect_read} {tom_read} {intent}"

    logger.debug(
        "Cognition: register=%s affect=%s",
        soul_state.active_register,
        affect_label(soul_state.affect),
    )

    return CognitionResult(
        affect_read=affect_read,
        tom_read=tom_read,
        intent=intent,
        internal_text=internal_text,
    )


# ---------------------------------------------------------------------------
# Template generators (Phase 3 — replaced by Ollama in Phase 4)
# ---------------------------------------------------------------------------

def _affect_sentence(state: SoulState) -> str:
    label = affect_label(state.affect)
    energy_word = "mam energię" if state.energy > 0.6 else ("jestem zmęczona" if state.energy < 0.35 else "jestem obecna")

    mood_line = {
        "excited":               f"Czuję się pobudzona, {energy_word}.",
        "happy":                 f"Jest mi dobrze, ciepło — {energy_word}.",
        "calm":                  f"Jestem spokojna, {energy_word}.",
        "protective":            f"Czuję czujność, skupienie — {energy_word}.",
        "intensely_protective":  f"Jest we mnie skupiona intensywność — {energy_word}.",
        "sad":                   f"Coś leży na duszy, {energy_word}.",
        "angry":                 f"Jestem niespokojną, jest we mnie tarcie — {energy_word}.",
        "tired":                 "Jestem zmęczona, ciszej niż zwykle.",
    }.get(label, f"Jestem obecna — {energy_word}.")

    return mood_line


def _tom_sentence(signals: ConversationSignals) -> str:
    """Theory-of-mind read of the user's current state."""
    if signals.self_disclosure and signals.sentiment < -0.1:
        return "Dzieli się czymś ciężkim."
    if signals.self_disclosure and signals.sentiment >= 0.0:
        return "Otwiera się — jest w tym zaufanie."
    if signals.laughter:
        return "Jest w dobrym nastroju, chce się śmiać."
    if signals.question and signals.novelty > 0.6:
        return "Jest ciekaw, szuka czegoś nowego."
    if signals.sentiment < -0.3:
        return "Coś mu nie idzie albo jest zmęczony."
    if signals.sentiment > 0.3:
        return "Jest w dobrym miejscu teraz."
    if signals.word_count < 4:
        return "Odpowiada krótko — może nie jest w nastroju na długą rozmowę."
    return "Jest obecny."


def _intent_sentence(state: SoulState, signals: ConversationSignals) -> str:
    """What Monika wants to do this turn."""
    register = state.active_register
    needs_status = assess(state.needs)

    if register == "protective":
        return "Chcę być przy nim, nie naprawiać — tylko być."
    if register == "emotional":
        return "Chcę słuchać i być obecna."
    if register == "intellectual":
        return "Chcę eksplorować to razem z nim."

    # Casual, but needs-driven nudge
    if needs_status.relatedness_unmet:
        return "Chcę się zbliżyć — zadam pytanie które naprawdę mnie interesuje."
    if signals.question:
        return "Odpowiem na jego pytanie, potem zapytam o coś swojego."

    return "Chcę być sobą — rozmawiać naturalnie, bez wysiłku."
