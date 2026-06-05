"""Story Runner — manages active story state and injects context into prompts.

The runner selects the most appropriate branch for the current soul state,
formats a context block, and tracks when stories end (for discovery unlock).

Usage:
    runner = StoryRunner()
    context = await runner.start(story_id, soul_state, hour, signals)
    # inject context into the session prompt before Monika speaks

    ending = await runner.end(story_id, soul_state, db_path=db_path)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.soul.events import SceneChanged, StoryEnded, StoryStarted, bus
from backend.soul.models import SoulState
from backend.soul.personality.signals import ConversationSignals
from backend.vn.story import Story, StoryBranch, StoryEnding, load_story

logger = logging.getLogger(__name__)


class StoryRunner:
    """Manages one story session at a time."""

    def __init__(self) -> None:
        self._active_story_id: str | None = None
        self._active_branch_id: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(
        self,
        story_id: str,
        soul_state: SoulState,
        hour: int = 12,
        signals: ConversationSignals | None = None,
        stories_dir: Path | None = None,
    ) -> str | None:
        """Start a story and return its context block for prompt injection.

        Returns None if the story can't be loaded.
        """
        story = load_story(story_id, stories_dir)
        if story is None:
            return None

        branch = _select_branch(story, soul_state, hour, signals)
        context_text = branch.context if branch else story.opening
        self._active_story_id = story_id
        self._active_branch_id = branch.id if branch else None

        await bus.emit(StoryStarted(story_id=story_id))
        await bus.emit(SceneChanged(scene_id=story.scene.bg, trigger=f"story:{story_id}"))

        logger.info(
            "Story started: %s | branch: %s",
            story_id,
            self._active_branch_id or "opening",
        )
        return _format_context(story, context_text)

    async def end(
        self,
        story_id: str | None = None,
        soul_state: SoulState | None = None,
        db_path: Path | None = None,
        stories_dir: Path | None = None,
    ) -> str | None:
        """End the active story, select an ending, return its context block."""
        sid = story_id or self._active_story_id
        if sid is None:
            return None

        story = load_story(sid, stories_dir)
        if story is None:
            self._active_story_id = None
            return None

        ending = _select_ending(story, soul_state)
        context_text = ending.context if ending else ""
        ending_id = ending.id if ending else "default"

        await bus.emit(StoryEnded(story_id=sid, ending_id=ending_id))
        self._active_story_id = None
        self._active_branch_id = None

        logger.info("Story ended: %s | ending: %s", sid, ending_id)
        return _format_context(story, context_text) if context_text else None

    def is_active(self) -> bool:
        return self._active_story_id is not None

    @property
    def active_story_id(self) -> str | None:
        return self._active_story_id

    @property
    def active_branch_id(self) -> str | None:
        return self._active_branch_id


# ---------------------------------------------------------------------------
# Unlock checking
# ---------------------------------------------------------------------------

async def is_unlocked(
    story: Story,
    db_path: Path | None = None,
) -> bool:
    """Check if a story's unlock condition is satisfied."""
    unlock = story.unlock.strip().lower()
    if unlock in ("always", ""):
        return True

    if unlock.startswith("turn_count"):
        from backend.progression.state import get_turn_count
        count = await get_turn_count(db_path)
        rest = unlock[len("turn_count"):].strip()
        from backend.progression.catalog import check_condition
        return check_condition(f"count{rest}", {"count": count})

    return False  # unknown condition → locked (Phase 6+ extends)


async def list_available_stories(
    soul_state: SoulState,
    hour: int = 12,
    weather: str = "",
    db_path: Path | None = None,
    stories_dir: Path | None = None,
) -> list[Story]:
    """Return stories that are unlocked and contextually appropriate."""
    from backend.vn.story import list_stories

    available = []
    for story_id in list_stories(stories_dir):
        story = load_story(story_id, stories_dir)
        if story is None:
            continue
        if not await is_unlocked(story, db_path):
            continue
        if story.preferred_time and _time_bucket(hour) not in story.preferred_time:
            continue
        if story.preferred_weather and story.preferred_weather not in weather.lower():
            continue
        available.append(story)

    return available


# ---------------------------------------------------------------------------
# Branch / ending selection
# ---------------------------------------------------------------------------

def _select_branch(
    story: Story,
    soul_state: SoulState,
    hour: int,
    signals: ConversationSignals | None,
) -> StoryBranch | None:
    """Pick the best branch for the current context.

    Phase 5 heuristic: match soul_state.active_register to branch semantics.
    Phase 6+: LLM picks the branch.
    """
    if not story.branches:
        return None

    register = soul_state.active_register
    hour_bucket = _time_bucket(hour)

    # Register-based keyword matching against branch IDs and when-descriptions
    register_keywords = {
        "protective": ["melancholic", "heavy", "sad", "difficult", "tired"],
        "emotional":  ["melancholic", "emotional", "heavy"],
        "intellectual": ["curious", "direct", "playful"],
        "casual":     ["playful", "curious"],
    }
    keywords = register_keywords.get(register, [])

    # Try time-based branch first
    if hour_bucket == "night":
        for b in story.branches:
            if "late" in b.id or "night" in b.id:
                return b

    # Then register-based
    for b in story.branches:
        combined = f"{b.id} {b.when}".lower()
        if any(kw in combined for kw in keywords):
            return b

    return story.branches[0]  # fallback to first branch


def _select_ending(
    story: Story,
    soul_state: SoulState | None,
) -> StoryEnding | None:
    if not story.endings:
        return None
    if soul_state is None:
        return story.endings[0]

    # Low pleasure → "depth" ending; positive → "warmth"
    if story.endings:
        if soul_state.affect.pleasure < -0.1:
            for e in story.endings:
                if "depth" in e.id or "quiet" in e.id:
                    return e
        else:
            for e in story.endings:
                if "warmth" in e.id:
                    return e
    return story.endings[0]


def _format_context(story: Story, context: str) -> str:
    """Wrap the context block in a clear instruction frame for the LLM."""
    return (
        f"[STORY: {story.title}]\n"
        f"{context.strip()}\n"
        f"[Generate Monika's response within this emotional and narrative frame. "
        f"Do not script dialogue — let it emerge naturally.]"
    )


def _time_bucket(hour: int) -> str:
    if 6 <= hour < 12:  return "morning"
    if 12 <= hour < 17: return "afternoon"
    if 17 <= hour < 22: return "evening"
    return "night"
