"""Story branch selection strategies."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from backend.soul.models import SoulState
from backend.soul.personality.signals import ConversationSignals
from backend.vn.story import Story, StoryBranch

logger = logging.getLogger(__name__)

BranchSelector = Callable[["BranchSelectionContext"], str | StoryBranch | None | Awaitable[str | StoryBranch | None]]


@dataclass(frozen=True)
class BranchSelectionContext:
    story: Story
    soul_state: SoulState
    hour: int
    signals: ConversationSignals | None = None

    @property
    def hour_bucket(self) -> str:
        return time_bucket(self.hour)


async def select_branch(
    context: BranchSelectionContext,
    *,
    mode: str = "heuristic",
    selector: BranchSelector | None = None,
) -> StoryBranch | None:
    """Select a story branch.

    `heuristic` is deterministic and remains the default. `llm` uses a caller-
    supplied selector and falls back to the heuristic if the selector is absent,
    fails, or returns an unknown branch ID.
    """
    if not context.story.branches:
        return None

    normalized_mode = str(mode or "heuristic").strip().lower()
    if normalized_mode not in {"heuristic", "llm"}:
        logger.warning("Unknown branch selection mode %r; using heuristic", mode)
        normalized_mode = "heuristic"

    fallback = heuristic_select_branch(context)
    if normalized_mode != "llm":
        return fallback

    if selector is None:
        logger.debug("LLM branch selection requested without selector; using heuristic")
        return fallback

    try:
        raw_choice = selector(context)
        if inspect.isawaitable(raw_choice):
            raw_choice = await raw_choice
    except Exception as exc:
        logger.warning("LLM branch selector failed; using heuristic: %s", exc)
        return fallback

    selected = resolve_branch(context.story, raw_choice)
    if selected is None:
        logger.warning("LLM branch selector returned unknown branch %r; using heuristic", raw_choice)
        return fallback
    return selected


def heuristic_select_branch(context: BranchSelectionContext) -> StoryBranch | None:
    """Deterministic Phase 5 branch selector."""
    story = context.story
    if not story.branches:
        return None

    register = context.soul_state.active_register

    register_keywords = {
        "protective": ["melancholic", "heavy", "sad", "difficult", "tired"],
        "emotional": ["melancholic", "emotional", "heavy"],
        "intellectual": ["curious", "direct", "playful"],
        "casual": ["playful", "curious"],
    }
    keywords = register_keywords.get(register, [])

    if context.hour_bucket == "night":
        for branch in story.branches:
            if "late" in branch.id or "night" in branch.id:
                return branch

    for branch in story.branches:
        combined = f"{branch.id} {branch.when}".lower()
        if any(keyword in combined for keyword in keywords):
            return branch

    return story.branches[0]


def resolve_branch(story: Story, choice: str | StoryBranch | None) -> StoryBranch | None:
    if choice is None:
        return None
    if isinstance(choice, StoryBranch):
        return choice if any(branch.id == choice.id for branch in story.branches) else None

    wanted = str(choice).strip().lower()
    if not wanted:
        return None

    # Allow model responses like "branch: if_playful".
    for token in ("branch:", "branch=", "id:", "id="):
        if wanted.startswith(token):
            wanted = wanted[len(token):].strip()

    wanted = wanted.split()[0].strip("`'\".,;")
    for branch in story.branches:
        if branch.id.lower() == wanted:
            return branch
    return None


def render_branch_selection_prompt(context: BranchSelectionContext) -> str:
    """Build the compact prompt a lightweight model selector can use."""
    state = context.soul_state
    lines = [
        "Choose the best story branch for Monika.",
        f"Story: {context.story.id} - {context.story.title}",
        f"Time: {context.hour_bucket} ({context.hour}:00)",
        f"Register: {state.active_register}",
        f"Affect: pleasure={state.affect.pleasure:.2f}, arousal={state.affect.arousal:.2f}, dominance={state.affect.dominance:.2f}",
        "Branches:",
    ]
    for branch in context.story.branches:
        lines.append(f"- {branch.id}: {branch.when}")
    lines.append("Return only one branch id.")
    return "\n".join(lines)


def time_bucket(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"
