from __future__ import annotations

from backend.soul.models import Affect, Needs, SoulState
from backend.vn.branch_selector import (
    BranchSelectionContext,
    render_branch_selection_prompt,
    resolve_branch,
    select_branch,
)
from backend.vn.story import Story, StoryBranch


def _state(register: str = "casual") -> SoulState:
    return SoulState(
        affect=Affect(pleasure=0.2, arousal=0.4, dominance=0.1),
        needs=Needs(),
        energy=0.7,
        active_register=register,
    )


def _story() -> Story:
    return Story(
        id="test_story",
        title="Test Story",
        unlock="always",
        opening="Opening",
        branches=[
            StoryBranch(id="if_melancholic", when="user seems heavy", context="soft"),
            StoryBranch(id="if_playful", when="easy mood", context="playful"),
            StoryBranch(id="if_late", when="late hour", context="quiet"),
        ],
    )


async def test_select_branch_heuristic_default():
    context = BranchSelectionContext(_story(), _state(register="protective"), hour=13)

    branch = await select_branch(context)

    assert branch is not None
    assert branch.id == "if_melancholic"


async def test_select_branch_llm_mode_uses_selector():
    async def selector(context: BranchSelectionContext):
        return "if_playful"

    context = BranchSelectionContext(_story(), _state(register="protective"), hour=13)

    branch = await select_branch(context, mode="llm", selector=selector)

    assert branch is not None
    assert branch.id == "if_playful"


async def test_select_branch_llm_mode_falls_back_on_unknown_id():
    async def selector(context: BranchSelectionContext):
        return "missing_branch"

    context = BranchSelectionContext(_story(), _state(register="protective"), hour=13)

    branch = await select_branch(context, mode="llm", selector=selector)

    assert branch is not None
    assert branch.id == "if_melancholic"


def test_resolve_branch_accepts_prefixed_model_text():
    story = _story()

    branch = resolve_branch(story, "branch: if_playful")

    assert branch is not None
    assert branch.id == "if_playful"


def test_render_branch_selection_prompt_lists_branch_ids():
    context = BranchSelectionContext(_story(), _state(register="intellectual"), hour=22)

    prompt = render_branch_selection_prompt(context)

    assert "Test Story" in prompt
    assert "if_melancholic" in prompt
    assert "if_playful" in prompt
    assert "night" in prompt
