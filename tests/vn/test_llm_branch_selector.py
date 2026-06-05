from __future__ import annotations

import pytest

from backend.soul.models import Affect, Needs, SoulState
from backend.vn.branch_selector import BranchSelectionContext
from backend.vn.llm_branch_selector import LLMBranchSelector
from backend.vn.story import Story, StoryBranch


class StubAioModels:

    def __init__(self, response_text: str = "", should_raise: bool = False):
        self.response_text = response_text
        self.should_raise = should_raise
        self.last_model = None
        self.last_contents = None
        self.last_config = None

    async def generate_content(self, model, contents, config=None):
        if self.should_raise:
            raise RuntimeError("LLM simulated error")
        self.last_model = model
        self.last_contents = contents
        self.last_config = config

        class StubResponse:
            text = self.response_text

        return StubResponse()


class StubAio:

    def __init__(self, response_text: str = "", should_raise: bool = False):
        self.models = StubAioModels(response_text, should_raise)


class StubClient:

    def __init__(self, response_text: str = "", should_raise: bool = False):
        self.aio = StubAio(response_text, should_raise)


def _state() -> SoulState:
    return SoulState(
        affect=Affect(pleasure=0.2, arousal=0.4, dominance=0.1),
        needs=Needs(),
        energy=0.7,
        active_register="casual",
    )


def _story(branches=None) -> Story:
    if branches is None:
        branches = [
            StoryBranch(id="if_melancholic", when="user seems heavy", context="soft"),
            StoryBranch(id="if_playful", when="easy mood", context="playful"),
        ]
    return Story(
        id="test_story",
        title="Test Story",
        unlock="always",
        opening="Opening",
        branches=branches,
    )


async def test_llm_branch_selector_success():
    stub_client = StubClient(response_text="if_playful")
    selector = LLMBranchSelector(llm_client=stub_client)

    context = BranchSelectionContext(_story(), _state(), hour=12)
    choice = await selector(context)

    assert choice == "if_playful"
    assert stub_client.aio.models.last_model == "gemini-2.5-flash"
    assert "Branches:" in stub_client.aio.models.last_contents


async def test_llm_branch_selector_success_with_text_parsing():
    stub_client = StubClient(response_text="I think branch if_playful is the best choice.")
    selector = LLMBranchSelector(llm_client=stub_client)

    context = BranchSelectionContext(_story(), _state(), hour=12)
    choice = await selector(context)

    assert choice == "if_playful"


async def test_llm_branch_selector_one_branch_early_exit():
    stub_client = StubClient(response_text="if_playful", should_raise=True)  # shouldn't call LLM
    selector = LLMBranchSelector(llm_client=stub_client)

    single_branch = [StoryBranch(id="only_one", when="always", context="only")]
    context = BranchSelectionContext(_story(single_branch), _state(), hour=12)
    choice = await selector(context)

    assert choice == "only_one"


async def test_llm_branch_selector_no_branches_returns_none():
    stub_client = StubClient(response_text="if_playful")
    selector = LLMBranchSelector(llm_client=stub_client)

    context = BranchSelectionContext(_story([]), _state(), hour=12)
    choice = await selector(context)

    assert choice is None


async def test_llm_branch_selector_fallback_on_failure():
    stub_client = StubClient(should_raise=True)

    async def fallback(ctx):
        return "if_melancholic"

    selector = LLMBranchSelector(fallback_selector=fallback, llm_client=stub_client)

    context = BranchSelectionContext(_story(), _state(), hour=12)
    choice = await selector(context)

    assert choice == "if_melancholic"


async def test_llm_branch_selector_fallback_on_invalid_output():
    stub_client = StubClient(response_text="completely_garbage_output_from_llm")

    async def fallback(ctx):
        return "if_melancholic"

    selector = LLMBranchSelector(fallback_selector=fallback, llm_client=stub_client)

    context = BranchSelectionContext(_story(), _state(), hour=12)
    choice = await selector(context)

    assert choice == "if_melancholic"
