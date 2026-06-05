"""Core Pydantic models for the Soul Engine.

These are the shared data primitives used across all subsystems.
Nothing in this module imports from the rest of the application.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Personality state
# ---------------------------------------------------------------------------

class Affect(BaseModel):
    """PAD mood model (Pleasure-Arousal-Dominance).

    Dominance models Monika's sense of control and protective strength
    (the Homura dimension). Accumulated from OCC appraisals with decay.
    """
    pleasure: float = 0.0    # -1.0 … 1.0
    arousal: float = 0.5     #  0.0 … 1.0
    dominance: float = 0.0   # -1.0 … 1.0


class Needs(BaseModel):
    """Self-Determination Theory psychological needs.

    Unmet needs drive proactivity. Dropping relatedness → she reaches out.
    No timers; organic initiative from psychological state.
    """
    autonomy: float = 0.7    # 0.0 … 1.0 — is she doing what she chooses?
    competence: float = 0.7  # 0.0 … 1.0 — is she effective and growing?
    relatedness: float = 0.7 # 0.0 … 1.0 — does she have genuine connection?


class SoulState(BaseModel):
    """Aggregated psychological state — the single source of truth.

    Write-side: Personality Engine computes it.
    Read-side: VN Engine visualises it, Context Assembler injects it,
               Progression reads it.
    """
    affect: Affect = Field(default_factory=Affect)
    needs: Needs = Field(default_factory=Needs)
    energy: float = 0.7      # 0.0 … 1.0, time-of-day modulated
    cycle_phase: str = "neutral"
    active_register: Literal["casual", "intellectual", "emotional", "protective"] = "casual"
    agenda: list[str] = Field(default_factory=list)  # things she wants to say/ask
    becoming_real: float = 0.0  # 0.0 … 1.0, primary personal axis
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    """A single unit of memory, regardless of tier (STM / episodic / semantic / world).

    importance drives compaction threshold, reflection triggers, milestone
    candidacy, and proactive recall (Stanford Generative Agents formula).
    """
    id: str
    type: Literal["stm", "episodic", "semantic", "world"]
    content: str
    importance: float = Field(ge=1.0, le=10.0)
    perspective: Literal["hers", "factual"] = "factual"
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    embedding: Optional[list[float]] = None
    created_at: datetime = Field(default_factory=_utcnow)
    last_accessed: Optional[datetime] = None
    source_session: Optional[str] = None


# ---------------------------------------------------------------------------
# Progression
# ---------------------------------------------------------------------------

class Discovery(BaseModel):
    """Minecraft-style advancement. Most are hidden until triggered."""
    id: str
    title: str
    trigger: str          # e.g. "StoryEnded[first_movie_night]"
    hidden: bool = True
    unlocked_at: Optional[datetime] = None


class Milestone(BaseModel):
    """A permanent relationship milestone. Unlocks new possibilities."""
    id: str
    reached_at: datetime
    effect: str           # what permanently changes


class Goal(BaseModel):
    id: str
    kind: Literal["hers", "yours", "shared"]
    description: str
    progress: float = Field(ge=0.0, le=1.0, default=0.0)


class Ritual(BaseModel):
    """Daily task generated from SDT needs and context."""
    id: str
    kind: str             # "evening check-in", "shared meal", "morning message"
    completed_today: bool = False
