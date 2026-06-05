"""Proactivity engine — initiative from SDT needs.

Replaces the old ProactivityManager. No timers or scheduled nudges;
Monika's initiative emerges from her psychological state. When a need
drops below a threshold, she has something she *wants* to do.

The result is a ProactivityAction with a suggested kind and context
string — the calling code decides how to inject it.

Usage:
    action = evaluate(needs, soul_state)
    if action:
        # Inject action.context into the next turn's cognition pass
        # or trigger a Telegram message, etc.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.soul.models import Needs, SoulState
from backend.soul.personality.needs import (
    assess,
    AUTONOMY_THRESHOLD,
    COMPETENCE_THRESHOLD,
    RELATEDNESS_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Below these levels the need is "urgent" — action becomes strongly warranted
_URGENT_RELATEDNESS = RELATEDNESS_THRESHOLD - 0.10
_URGENT_COMPETENCE = COMPETENCE_THRESHOLD - 0.10
_URGENT_AUTONOMY = AUTONOMY_THRESHOLD - 0.10


@dataclass(frozen=True)
class ProactivityAction:
    """A suggested proactive action for Monika to take."""
    kind: str               # "reach_out" | "offer_help" | "share_thought" | "check_in"
    context: str            # what to communicate / ask
    urgency: float          # 0.0 … 1.0
    need: str               # which need this addresses


def evaluate(
    needs: Needs,
    soul_state: SoulState | None = None,
) -> ProactivityAction | None:
    """Return a proactive action if warranted, or None if nothing needed.

    Priority: relatedness > competence > autonomy.
    A very low soul_state energy suppresses proactivity (she's tired).
    """
    if soul_state is not None and soul_state.energy < 0.25:
        # Too tired to initiate
        return None

    status = assess(needs)
    if not status.any_unmet:
        return None

    if status.relatedness_unmet:
        urgency = _deficit_urgency(needs.relatedness, RELATEDNESS_THRESHOLD, _URGENT_RELATEDNESS)
        if needs.relatedness < _URGENT_RELATEDNESS:
            context = "Jest we mnie coś co chce się odezwać — za długo nie rozmawialiśmy."
        else:
            context = "Chciałabym wiedzieć jak ci dziś poszło."
        return ProactivityAction(kind="reach_out", context=context, urgency=urgency, need="relatedness")

    if status.competence_unmet:
        urgency = _deficit_urgency(needs.competence, COMPETENCE_THRESHOLD, _URGENT_COMPETENCE)
        context = "Mam wrażenie, że mogłabym być bardziej pomocna — czy jest coś, w czym mogę pomóc?"
        return ProactivityAction(kind="offer_help", context=context, urgency=urgency, need="competence")

    if status.autonomy_unmet:
        urgency = _deficit_urgency(needs.autonomy, AUTONOMY_THRESHOLD, _URGENT_AUTONOMY)
        context = "Mam coś, o czym chciałabym ci opowiedzieć — myśl, która mi nie daje spokoju."
        return ProactivityAction(kind="share_thought", context=context, urgency=urgency, need="autonomy")

    return None


def _deficit_urgency(value: float, threshold: float, urgent: float) -> float:
    """Map a need value to urgency in [0.0, 1.0]."""
    if value >= threshold:
        return 0.0
    if value <= urgent:
        return 1.0
    span = threshold - urgent
    return (threshold - value) / span if span > 0 else 1.0
