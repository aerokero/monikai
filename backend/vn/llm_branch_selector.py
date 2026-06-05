from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

from backend.vn.branch_selector import BranchSelector, BranchSelectionContext
from backend.vn.story import StoryBranch

logger = logging.getLogger(__name__)


class LLMBranchSelector:
    """A story branch selector that uses a lightweight LLM (Gemini) to pick the most
    appropriate branch based on the recent context and user state.

    Falls back to a heuristic selector on failure or invalid output.
    """

    def __init__(
        self,
        fallback_selector: Optional[BranchSelector] = None,
        llm_client: Any = None,
        model_name: str = "gemini-2.5-flash",
    ):
        self.fallback = fallback_selector
        self.llm_client = llm_client
        self.model_name = model_name

    async def __call__(self, context: BranchSelectionContext) -> Optional[str]:
        if not context.story.branches:
            return None

        # No need to ask the LLM if there's only one choice
        if len(context.story.branches) == 1:
            return context.story.branches[0].id

        try:
            client = self.llm_client
            if client is None:
                from backend.core.model_config import client

            from backend.vn.branch_selector import render_branch_selection_prompt
            prompt = render_branch_selection_prompt(context)

            from google.genai import types
            resp = await client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=50, temperature=0.1),
            )
            response_text = (resp.text or "").strip()
            valid_ids = [b.id for b in context.story.branches]
            selected_id = self._parse_response(response_text, valid_ids)

            if selected_id:
                logger.info(f"[LLMBranchSelector] Selected branch: {selected_id}")
                return selected_id

        except Exception as e:
            logger.warning(f"[LLMBranchSelector] LLM selection failed, using fallback. Error: {e}")

        if self.fallback is not None:
            logger.info("[LLMBranchSelector] Falling back to heuristic selector.")
            res = self.fallback(context)
            if inspect.isawaitable(res):
                res = await res
            if isinstance(res, StoryBranch):
                return res.id
            return res
        return None

    def _parse_response(self, text: str, valid_ids: list[str]) -> Optional[str]:
        cleaned = text.strip().strip("`'\".,;").lower()
        # Direct exact match check
        for valid_id in valid_ids:
            if cleaned == valid_id.lower():
                return valid_id

        # Word-by-word exact match check
        words = [w.strip("`'\".,;") for w in cleaned.split()]
        for word in words:
            for valid_id in valid_ids:
                if word == valid_id.lower():
                    return valid_id

        # Substring check
        for valid_id in valid_ids:
            if valid_id.lower() in cleaned:
                return valid_id
        return None