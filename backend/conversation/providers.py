"""Provider-neutral text-generation boundary."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol

from .tools import ConversationToolDefinition, ConversationToolRequest


@dataclass(frozen=True)
class TextGenerationRequest:
    model: str
    system_instruction: str
    prompt: str
    thinking_budget: int | None = None
    thinking_level: str | None = None


@dataclass(frozen=True)
class ToolPlanningRequest:
    model: str
    system_instruction: str
    prompt: str
    tools: tuple[ConversationToolDefinition, ...]


class TextModelProvider(Protocol):
    async def generate(self, request: TextGenerationRequest) -> str: ...

    async def plan_tools(
        self,
        request: ToolPlanningRequest,
    ) -> tuple[ConversationToolRequest, ...]: ...


def _gemini_model_candidates(requested_model: str) -> list[str]:
    """Try the selected model first, then configured emergency fallbacks.

    The previous implementation did the opposite for every model except two
    stale ids, so a picker choice such as ``gemini-2.5-pro`` never reached the
    Google API.  Fallbacks remain useful, but they must never outrank the
    user's explicit selection.
    """
    requested = str(requested_model or "").strip()
    candidates: list[str] = [requested] if requested else []
    configured = (
        os.getenv("MONIKAI_CONVERSATION_FALLBACK_MODEL", "gemini-3.6-flash"),
        os.getenv("MONIKAI_CONVERSATION_EMERGENCY_MODEL", "gemini-2.5-flash"),
    )
    for candidate in configured:
        candidate = str(candidate or "").strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


class GeminiTextProvider:
    """Google GenAI implementation kept outside the conversation domain."""

    def __init__(self, *, api_key: str | None = None, client=None):
        self._api_key = api_key
        self._client = client

    async def generate(self, request: TextGenerationRequest) -> str:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        thinking_config = None
        if request.thinking_level is not None:
            thinking_config = types.ThinkingConfig(
                thinking_level=request.thinking_level
            )
        elif request.thinking_budget is not None:
            thinking_config = types.ThinkingConfig(
                thinking_budget=request.thinking_budget
            )

        models_to_try = _gemini_model_candidates(request.model)

        response = None
        for model_name in models_to_try:
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=request.prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=request.system_instruction,
                        thinking_config=thinking_config,
                    ),
                )
                if response and response.text:
                    return response.text
            except Exception as exc:
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc) or "404" in str(exc):
                    continue
                break
        return response.text if response else ""

    async def plan_tools(
        self,
        request: ToolPlanningRequest,
    ) -> tuple[ConversationToolRequest, ...]:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        declarations = [
            types.FunctionDeclaration(
                name=item.name,
                description=item.description,
                parameters_json_schema=item.parameters_json_schema,
            )
            for item in request.tools
        ]

        models_to_try = _gemini_model_candidates(request.model)

        response = None
        last_exc = None
        for model_name in models_to_try:
            try:
                response = await self._client.aio.models.generate_content(
                    model=model_name,
                    contents=request.prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=request.system_instruction,
                        tools=[types.Tool(function_declarations=declarations)],
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                    ),
                )
                if response:
                    break
            except Exception as exc:
                last_exc = exc
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc) or "404" in str(exc):
                    continue
                break

        if response is None:
            if last_exc:
                print(f"[THINKER] plan_tools nie powiodło się na żadnym modelu: {last_exc}")
            return ()

        calls = []
        for call in list(getattr(response, "function_calls", None) or []):
            name = str(getattr(call, "name", "") or "").strip()
            if name:
                calls.append(
                    ConversationToolRequest(
                        name=name,
                        arguments=dict(getattr(call, "args", None) or {}),
                    )
                )
        return tuple(calls)
