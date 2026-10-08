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
