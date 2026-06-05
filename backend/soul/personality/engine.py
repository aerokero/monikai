"""Personality Engine — SoulState aggregation.

Assembles all personality components into the unified SoulState.
This is the write-side of SoulState: observe a turn, update all
components, produce a new SoulState. The rest of the system reads it.

Usage:
    engine = PersonalityEngine.load()
    soul_state = await engine.observe_turn(user_text, reciprocity=True)
    engine.save()
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from backend.soul.events import SoulStateUpdated, TurnCompleted, bus
from backend.soul.models import Affect, Needs, SoulState
from backend.soul.personality import affect as affect_mod
from backend.soul.personality import needs as needs_mod
from backend.soul.personality.signals import ConversationSignals, SignalHistory, extract
from backend.soul.personality.state_store import StateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Register computation
# ---------------------------------------------------------------------------

def _compute_register(
    affect: Affect,
    needs: Needs,
    last_signals: ConversationSignals | None,
) -> Literal["casual", "intellectual", "emotional", "protective"]:
    """Determine the active interaction register from current state."""

    # Protective: user is struggling (low pleasure, protective_concern appraisal)
    if affect.dominance > 0.2 and affect.pleasure < -0.15:
        return "protective"

    # Emotional: self-disclosure was high, affect in mid-range
    if last_signals and last_signals.self_disclosure and abs(affect.pleasure) < 0.5:
        return "emotional"

    # Intellectual: fresh topic, higher arousal/dominance
    if last_signals and last_signals.novelty > 0.65 and affect.arousal > 0.5:
        return "intellectual"

    return "casual"


def _compute_energy(hour: int, cycle_day: int) -> float:
    """Time-of-day and cycle modulated energy."""
    if 0 <= hour < 6:
        time_mod = 0.35
    elif 6 <= hour < 9:
        time_mod = 0.70
    elif 9 <= hour < 18:
        time_mod = 1.00
    elif 18 <= hour < 22:
        time_mod = 0.80
    else:
        time_mod = 0.50

    # Cycle phase modifier (rough approximation)
    if 14 <= cycle_day <= 16:
        cycle_mod = 1.10  # peak
    elif 6 <= cycle_day <= 13:
        cycle_mod = 1.00  # rising
    elif 1 <= cycle_day <= 5:
        cycle_mod = 0.90  # low/calm
    else:
        cycle_mod = 0.85  # late phase, tired

    return max(0.0, min(1.0, 0.75 * time_mod * cycle_mod))


def _compute_cycle_phase(cycle_day: int) -> str:
    if 1 <= cycle_day <= 5:
        return "calm_neutral"
    if 6 <= cycle_day <= 13:
        return "rising_happy"
    if 14 <= cycle_day <= 16:
        return "peak_social"
    return "late_tired"


# ---------------------------------------------------------------------------
# Personality Engine
# ---------------------------------------------------------------------------

class PersonalityEngine:
    """Stateful personality engine. One instance per process lifetime.

    State is persisted to data/soul/state.json after each observed turn.
    Call load() on startup, save() on shutdown or after significant turns.
    """

    def __init__(
        self,
        affect: Affect,
        needs: Needs,
        cycle_day: int = 1,
        becoming_real: float = 0.0,
    ) -> None:
        self._affect = affect
        self._needs = needs
        self._cycle_day = cycle_day
        self._becoming_real = becoming_real
        self._history = SignalHistory(maxlen=6)
        self._last_signals: ConversationSignals | None = None
        self._last_ai_question_ts: float | None = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls) -> "PersonalityEngine":
        state = StateStore.read()
        return cls(
            affect=state.affect,
            needs=state.needs,
            cycle_day=_current_cycle_day(),
            becoming_real=state.becoming_real,
        )

    # ------------------------------------------------------------------
    # Turn observation
    # ------------------------------------------------------------------

    async def observe_turn(
        self,
        user_text: str,
        monika_text: str = "",
        reciprocity: bool | None = None,
    ) -> SoulState:
        """Process one conversation turn and return updated SoulState.

        Parameters
        ----------
        user_text:    What the user said.
        monika_text:  What Monika just said (used to detect question-asking).
        reciprocity:  Whether the user answered a question Monika asked.
                      If None, auto-detected from recent ai question window.
        """
        signals = self._history.extract(user_text)
        self._last_signals = signals

        # Auto-detect reciprocity if not supplied
        if reciprocity is None:
            import time
            if self._last_ai_question_ts and (time.time() - self._last_ai_question_ts) < 180:
                reciprocity = True
                self._last_ai_question_ts = None
            else:
                reciprocity = False

        # Track if Monika asked a question this turn
        if monika_text and "?" in monika_text:
            import time
            self._last_ai_question_ts = time.time()

        # Update affect
        delta = affect_mod.appraise(signals)
        self._affect = affect_mod.accumulate(self._affect, delta)

        # Update needs
        self._needs = needs_mod.update_from_turn(self._needs, signals, reciprocity)

        soul_state = self._build_soul_state()
        await bus.emit(SoulStateUpdated())
        logger.debug(
            "Turn observed: affect=%s needs_rel=%.2f register=%s",
            affect_mod.affect_label(self._affect),
            self._needs.relatedness,
            soul_state.active_register,
        )
        return soul_state

    def note_ai_question(self) -> None:
        """Call when Monika asks a question, to enable reciprocity detection."""
        import time
        self._last_ai_question_ts = time.time()

    # ------------------------------------------------------------------
    # SoulState assembly
    # ------------------------------------------------------------------

    def _build_soul_state(self) -> SoulState:
        now = datetime.now(tz=timezone.utc)
        hour = now.hour
        energy = _compute_energy(hour, self._cycle_day)
        cycle_phase = _compute_cycle_phase(self._cycle_day)
        register = _compute_register(self._affect, self._needs, self._last_signals)

        return SoulState(
            affect=self._affect,
            needs=self._needs,
            energy=energy,
            cycle_phase=cycle_phase,
            active_register=register,
            agenda=[],
            becoming_real=self._becoming_real,
        )

    @property
    def soul_state(self) -> SoulState:
        return self._build_soul_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        StateStore.write(self._build_soul_state())

    def apply_session_end(self) -> None:
        """Call when a conversation session ends — applies gentle decay."""
        self._needs = needs_mod.decay_session(self._needs)

    def apply_daily_decay(self, days_elapsed: float = 1.0) -> None:
        """Call after N days of inactivity — decays needs (esp. relatedness)."""
        self._needs = needs_mod.decay_daily(self._needs, days_elapsed)
        self._affect = affect_mod.decay_toward_baseline(self._affect, turns=5)

    @property
    def needs_status(self) -> needs_mod.NeedsStatus:
        return needs_mod.assess(self._needs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_cycle_day() -> int:
    """Approximate cycle day from a fixed epoch (placeholder until Phase 4)."""
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    delta = datetime.now(tz=timezone.utc) - epoch
    return (delta.days % 28) + 1
