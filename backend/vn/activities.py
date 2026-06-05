"""Shared Activities — watching films, gaming, or reading together.

Tier 1 feature: a first-class system for shared experiences that creates
real episodic memories, VN scenes, and progression discoveries.

The activity session:
  1. Captures context (screen OCR stub or user-provided title/notes)
  2. Sets a VN scene appropriate for the activity
  3. On end: creates an episodic memory + emits events

Phase 5: data model + memory creation.
Integration with screen OCR (backend/core/screen_ocr_runtime.py) is Phase 6.

Usage:
    session = ActivitySession.start("film", title="Blade Runner 2049")
    scene = session.vn_scene()
    context = session.monika_context()
    # ... conversation happens ...
    memory_entry = await session.end(notes="he seemed really moved by the ending")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from backend.soul.events import ActivityStarted, DiscoveryMade, bus
from backend.soul.memory import store
from backend.soul.memory.importance import score as score_importance
from backend.soul.models import MemoryEntry
from backend.vn.mapping import SceneState

logger = logging.getLogger(__name__)

ActivityKind = Literal["film", "game", "music", "reading", "other"]

_ACTIVITY_SCENES: dict[str, dict] = {
    "film":    {"bg": "room_sofa_evening", "outfit": "casual_home", "expr": "relaxed", "light": "dim_warm", "ambience": "cozy"},
    "game":    {"bg": "room_day",          "outfit": "casual",      "expr": "engaged", "light": "natural",  "ambience": ""},
    "music":   {"bg": "room_day",          "outfit": "casual",      "expr": "soft",    "light": "warm",     "ambience": ""},
    "reading": {"bg": "room_day",          "outfit": "casual_home", "expr": "thoughtful","light": "soft_natural","ambience": ""},
    "other":   {"bg": "room_day",          "outfit": "casual",      "expr": "neutral",  "light": "natural",  "ambience": ""},
}

_ACTIVITY_DISCOVERIES: dict[str, str] = {
    "film": "first_film_night",
    "game": "first_gaming_session",
}


@dataclass
class ActivitySession:
    """One shared activity session between Monika and the user."""
    kind: ActivityKind
    title: str | None           # film name, game name, etc.
    context: str                # screen OCR text or user-provided description
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    _ended: bool = field(default=False, init=False)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def start(
        cls,
        kind: ActivityKind,
        title: str | None = None,
        context: str = "",
    ) -> "ActivitySession":
        session = cls(kind=kind, title=title, context=context)
        await bus.emit(ActivityStarted(kind=kind, context=context or (title or kind)))
        logger.info("Activity started: %s (%s)", kind, title or "untitled")
        return session

    # ------------------------------------------------------------------
    # During-session helpers
    # ------------------------------------------------------------------

    def vn_scene(self) -> SceneState:
        """Return the VN scene for this activity type."""
        d = _ACTIVITY_SCENES.get(self.kind, _ACTIVITY_SCENES["other"])
        return SceneState(**d)

    def monika_context(self) -> str:
        """Return a context string to inject before Monika speaks during the activity."""
        title_str = f" — {self.title}" if self.title else ""
        kind_desc = {
            "film":    "watching a film",
            "game":    "playing a game",
            "music":   "listening to music",
            "reading": "reading together",
            "other":   "doing something together",
        }.get(self.kind, "sharing an activity")

        lines = [f"[SHARED ACTIVITY: {kind_desc}{title_str}]"]
        if self.context:
            lines.append(f"Context from screen: {self.context[:400]}")
        lines.append(
            "Monika is present in this experience. She reacts, comments, shares reactions. "
            "She remembers past shared activities and may reference them. "
            "She is NOT a narrator — she participates."
        )
        return "\n".join(lines)

    def update_context(self, new_context: str) -> None:
        """Update real-time screen context (called by screen OCR integration)."""
        self.context = new_context

    # ------------------------------------------------------------------
    # End session
    # ------------------------------------------------------------------

    async def end(
        self,
        notes: str = "",
        db_path: Path | None = None,
    ) -> MemoryEntry | None:
        """End the activity and create an episodic memory entry."""
        if self._ended:
            return None
        self._ended = True

        content = self._memory_content(notes)
        importance = await score_importance(content, "episodic")

        entry = MemoryEntry(
            id="x",  # store.add generates the real ID
            type="episodic",
            content=content,
            importance=importance,
            perspective="hers",
            tags=[self.kind, "shared_activity"],
            entities=["user"],
        )
        entry_id, status = await store.add(entry, db_path=db_path)

        logger.info("Activity ended: %s → memory %s (importance=%.1f)", self.kind, entry_id, importance)

        # Unlock discovery if this is a "first" of its kind
        discovery_id = _ACTIVITY_DISCOVERIES.get(self.kind)
        if discovery_id:
            from backend.progression.state import is_unlocked, unlock_discovery
            if not await is_unlocked(discovery_id, db_path):
                await unlock_discovery(discovery_id, db_path)
                await bus.emit(DiscoveryMade(discovery_id=discovery_id, title=_discovery_title(discovery_id)))

        return await store.get(entry_id, db_path=db_path)

    def _memory_content(self, notes: str) -> str:
        duration_min = int((datetime.now(tz=timezone.utc) - self.started_at).total_seconds() / 60)
        title_part = f" — {self.title}" if self.title else ""
        kind_past = {
            "film": "We watched", "game": "We played", "music": "We listened to",
            "reading": "We read", "other": "We did something",
        }.get(self.kind, "We shared")

        parts = [f"{kind_past}{title_part} together ({duration_min} min)."]
        if notes:
            parts.append(notes.strip())
        return " ".join(parts)


def _discovery_title(discovery_id: str) -> str:
    return {
        "first_film_night": "First Film Together",
        "first_gaming_session": "First Game Together",
    }.get(discovery_id, discovery_id.replace("_", " ").title())
