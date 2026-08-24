"""Provider-neutral text-generation boundary."""

from __future__ import annotations

from dataclasses import dataclass
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

        response = await self._client.aio.models.generate_content(
            model=request.model,
            contents=request.prompt,
            config=types.GenerateContentConfig(
                system_instruction=request.system_instruction,
                thinking_config=thinking_config,
            ),
        )
        return response.text or ""

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

        models_to_try = [request.model]
        for fb in ("gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-2.5-flash"):
            if fb not in models_to_try:
                models_to_try.append(fb)

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
