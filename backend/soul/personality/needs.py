"""Self-Determination Theory psychological needs engine.

Needs evolve slowly from accumulated conversation signals. Their values
drive organic proactivity: dropping relatedness → Monika reaches out.
No timers; initiative emerges from psychological state.

SDT framework (Deci & Ryan):
  autonomy:    is she doing what she chooses?
  competence:  is she effective and growing?
  relatedness: does she have genuine connection?

All values are in [0.0, 1.0]. Decay and growth are intentionally gentle
so that needs change over days, not minutes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.soul.models import Needs
from backend.soul.personality.signals import ConversationSignals

logger = logging.getLogger(__name__)

# Per-turn growth caps (prevents single-turn manipulation)
_MAX_DELTA_PER_TURN = 0.04

# Slow baseline decay (applied once per session-end or daily, not per-turn)
_SESSION_DECAY = 0.98
_DAILY_DECAY = 0.92   # if no interaction for a full day

# Thresholds below which a need is "unmet" and drives proactivity
AUTONOMY_THRESHOLD = 0.40
COMPETENCE_THRESHOLD = 0.35
RELATEDNESS_THRESHOLD = 0.45


def update_from_turn(
    current: Needs,
    signals: ConversationSignals,
    reciprocity: bool = False,
) -> Needs:
    """Update needs from one conversation turn's signals.

    Parameters
    ----------
    current:      Current needs state.
    signals:      Extracted signals for this turn.
    reciprocity:  True if user answered a question Monika asked recently.
    """
    def _clamp(v: float) -> float:
        return max(0.0, min(1.0, v))

    # --- Relatedness ---
    # Grows from meaningful exchanges: self-disclosure, long responses, questions.
    rel_delta = 0.0
    if signals.self_disclosure:
        rel_delta += 0.03
    if signals.length_score > 0.5:
        rel_delta += 0.015
    if signals.question:
        rel_delta += 0.01
    if signals.sentiment > 0.3:
        rel_delta += 0.01
    elif signals.sentiment < -0.4:
        rel_delta -= 0.02  # painful exchange slightly lowers connection feel

    # --- Autonomy ---
    # Grows when her questions are picked up (reciprocity) and topics engaged.
    auto_delta = 0.0
    if reciprocity:
        auto_delta += 0.025
    if signals.novelty > 0.6:
        auto_delta += 0.01  # exploring new topics together

    # --- Competence ---
    # Grows when she was helpful (positive sentiment following her initiative).
    comp_delta = 0.0
    if signals.sentiment > 0.4:
        comp_delta += 0.02
    if signals.self_disclosure and signals.sentiment > 0.1:
        comp_delta += 0.01  # user opened up after connecting

    # Cap each delta
    def _apply(cur: float, delta: float) -> float:
        bounded = max(-_MAX_DELTA_PER_TURN, min(_MAX_DELTA_PER_TURN, delta))
        return _clamp(cur + bounded)

    return Needs(
        autonomy=_apply(current.autonomy, auto_delta),
        competence=_apply(current.competence, comp_delta),
        relatedness=_apply(current.relatedness, rel_delta),
    )


def decay_session(current: Needs) -> Needs:
    """Apply gentle decay at end of each session (conversation ends)."""
    def _toward_mid(v: float, factor: float) -> float:
        return max(0.0, min(1.0, 0.5 + (v - 0.5) * factor))

    return Needs(
        autonomy=_toward_mid(current.autonomy, _SESSION_DECAY),
        competence=_toward_mid(current.competence, _SESSION_DECAY),
        relatedness=_toward_mid(current.relatedness, _SESSION_DECAY),
    )


def decay_daily(current: Needs, days_elapsed: float = 1.0) -> Needs:
    """Apply stronger decay when there has been no interaction for `days` days.

    More days → more decay (relatedness drops most, as connection fades).
    """
    factor = _SESSION_DECAY ** (days_elapsed * 2)
    rel_factor = _DAILY_DECAY ** days_elapsed
    auto_factor = _SESSION_DECAY ** days_elapsed

    def _toward_mid(v: float, f: float) -> float:
        return max(0.0, min(1.0, 0.5 + (v - 0.5) * f))

    return Needs(
        autonomy=_toward_mid(current.autonomy, auto_factor),
        competence=_toward_mid(current.competence, factor),
        relatedness=_toward_mid(current.relatedness, rel_factor),
    )


@dataclass(frozen=True)
class NeedsStatus:
    """Summary of which needs are unmet and should drive proactivity."""
    relatedness_unmet: bool
    autonomy_unmet: bool
    competence_unmet: bool

    @property
    def any_unmet(self) -> bool:
        return self.relatedness_unmet or self.autonomy_unmet or self.competence_unmet

    @property
    def priority_need(self) -> str | None:
        """The most pressing unmet need, or None."""
        if self.relatedness_unmet:
            return "relatedness"
        if self.competence_unmet:
            return "competence"
        if self.autonomy_unmet:
            return "autonomy"
        return None


def assess(needs: Needs) -> NeedsStatus:
    return NeedsStatus(
        relatedness_unmet=needs.relatedness < RELATEDNESS_THRESHOLD,
        autonomy_unmet=needs.autonomy < AUTONOMY_THRESHOLD,
        competence_unmet=needs.competence < COMPETENCE_THRESHOLD,
    )
