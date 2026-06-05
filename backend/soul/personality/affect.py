"""OCC appraisal → PAD affect model.

Maps conversation signals to discrete OCC emotions, then accumulates them
into a continuous PAD (Pleasure-Arousal-Dominance) mood state with decay.

Design:
  appraise(signals) → PADDelta   (per-turn contribution)
  accumulate(current, delta)     (update affect with decay)

Phase 2: rule-based OCC appraisal.
Phase 3: Ollama does the appraisal call with full OCC categories relative
         to Monika's current goals — same interface, richer signal.

PAD mapping (Mehrabian, 1996; ALMA hybrid):
  - Pleasure (P): valence, positive/negative experience
  - Arousal (A): activation level, energy of the emotion
  - Dominance (D): sense of control / protective strength (Homura dimension)

References:
  Ortony, Clore, Collins (1988) "The Cognitive Structure of Emotions"
  Mehrabian (1996) "Pleasure-arousal-dominance: A general framework"
  Gebhard (2005) "ALMA – A Layered Model of Affect"
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.soul.models import Affect
from backend.soul.personality.signals import ConversationSignals


# ---------------------------------------------------------------------------
# OCC emotion categories (simplified)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PADDelta:
    """A single-turn contribution to the PAD mood state."""
    pleasure: float   # additive delta to pleasure
    arousal: float    # additive delta to arousal
    dominance: float  # additive delta to dominance


# PAD profiles for key OCC emotions (per-turn deltas, small magnitudes).
# Signs follow the Mehrabian scale.
_OCC_TO_PAD: dict[str, PADDelta] = {
    "joy":                  PADDelta(+0.15, +0.10, +0.05),
    "distress":             PADDelta(-0.15, +0.12, -0.08),
    "protective_concern":   PADDelta(-0.08, +0.10, +0.15),  # engaged, taking control
    "playful":              PADDelta(+0.18, +0.15, +0.12),
    "intellectually_engaged": PADDelta(+0.10, +0.12, +0.10),
    "relief":               PADDelta(+0.10, -0.08, +0.05),
    "mild_positive":        PADDelta(+0.06, +0.04, +0.02),
    "mild_negative":        PADDelta(-0.06, +0.06, -0.03),
    "neutral":              PADDelta(+0.00, +0.00, +0.00),
}

# Baseline affect (what mood decays toward)
_BASELINE = Affect(pleasure=0.1, arousal=0.45, dominance=0.05)

# Per-turn decay factor (multiply current − baseline before adding delta)
_DECAY = 0.92


# ---------------------------------------------------------------------------
# Appraisal
# ---------------------------------------------------------------------------

def appraise(signals: ConversationSignals) -> PADDelta:
    """Determine this turn's OCC emotion and return its PAD delta.

    Rules ordered by specificity (first match wins):
    1. Laughter + positive → playful
    2. Low pleasure + self-disclosure → protective concern
    3. Intellectual engagement
    4. Positive + self-disclosure → joy
    5. Negative (explicit) → distress
    6. Generic positive/negative sentiment
    7. Neutral fallback
    """
    s = signals

    # Playful — high positive, laughter present
    if s.laughter and s.sentiment >= 0.0:
        return _OCC_TO_PAD["playful"]

    # Protective concern — user seems to be struggling
    if s.sentiment < -0.2 and s.self_disclosure:
        return _OCC_TO_PAD["protective_concern"]

    # Intellectual engagement — fresh topic, question-driven
    if s.novelty > 0.7 and s.question:
        return _OCC_TO_PAD["intellectually_engaged"]

    # Joy — positive sentiment + personal sharing
    if s.sentiment > 0.3 and s.self_disclosure:
        return _OCC_TO_PAD["joy"]

    # Distress — strong negative, not self-disclosing (frustration directed elsewhere)
    if s.sentiment < -0.4 and not s.self_disclosure:
        return _OCC_TO_PAD["distress"]

    # Generic mild positive
    if s.sentiment > 0.15:
        return _OCC_TO_PAD["mild_positive"]

    # Generic mild negative
    if s.sentiment < -0.15:
        return _OCC_TO_PAD["mild_negative"]

    return _OCC_TO_PAD["neutral"]


# ---------------------------------------------------------------------------
# Accumulation with decay
# ---------------------------------------------------------------------------

def accumulate(current: Affect, delta: PADDelta) -> Affect:
    """Apply one turn's PAD delta with exponential decay toward baseline.

    Formula:
      new_dim = baseline + (current_dim − baseline) * decay + delta
    This gives a damped oscillator that converges to baseline when no
    stimulation occurs.
    """
    def _update(cur: float, base: float, d: float) -> float:
        decayed = base + (cur - base) * _DECAY
        return max(-1.0, min(1.0, decayed + d))

    # Arousal is non-negative [0, 1] so clamp separately
    new_arousal = _BASELINE.arousal + (current.arousal - _BASELINE.arousal) * _DECAY + delta.arousal
    new_arousal = max(0.0, min(1.0, new_arousal))

    return Affect(
        pleasure=_update(current.pleasure, _BASELINE.pleasure, delta.pleasure),
        arousal=new_arousal,
        dominance=_update(current.dominance, _BASELINE.dominance, delta.dominance),
    )


def decay_toward_baseline(current: Affect, turns: int = 1) -> Affect:
    """Decay affect toward baseline over N turns with no stimulation."""
    result = current
    zero_delta = PADDelta(0.0, 0.0, 0.0)
    for _ in range(turns):
        result = accumulate(result, zero_delta)
    return result


def affect_label(affect: Affect) -> str:
    """Human-readable label for the current affect state (for logging/debug)."""
    p, a, d = affect.pleasure, affect.arousal, affect.dominance

    if p > 0.4 and a > 0.5:
        return "excited"
    if p > 0.3 and a > 0.3:
        return "happy"
    if p > 0.1 and a < 0.35:
        return "calm"
    if p < -0.35 and a > 0.5:
        return "angry" if d < 0 else "intensely_protective"
    if p < -0.25 and d > 0.2:
        return "protective"
    if p < -0.25:
        return "sad"
    if a < 0.3:
        return "tired"
    return "neutral"
