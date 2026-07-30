"""Provider boundary tests without network calls."""

from __future__ import annotations

from types import SimpleNamespace

from backend.conversation.providers import (
    GeminiTextProvider,
    TextGenerationRequest,
    ToolPlanningRequest,
)
from backend.conversation.tools import CONVERSATION_TOOL_DEFINITIONS


async def test_gemini_provider_translates_neutral_request():
    calls = []

    class Models:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="<analysis>ok</analysis><reply>hej</reply>")

    client = SimpleNamespace(aio=SimpleNamespace(models=Models()))
    provider = GeminiTextProvider(client=client)

    result = await provider.generate(
        TextGenerationRequest(
            model="gemini-test",
            system_instruction="SYSTEM",
            prompt="PROMPT",
            thinking_budget=0,
        )
    )

    assert result.endswith("<reply>hej</reply>")
    assert calls[0]["model"] == "gemini-test"
    assert calls[0]["contents"] == "PROMPT"
    assert calls[0]["config"].system_instruction == "SYSTEM"
    assert calls[0]["config"].thinking_config.thinking_budget == 0


async def test_gemini_provider_returns_structured_tool_calls():
    calls = []

    class Models:
        async def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                function_calls=[
                    SimpleNamespace(
                        name="create_reminder",
                        args={"message": "raport", "in_minutes": 10},
                    )
                ]
            )

    client = SimpleNamespace(aio=SimpleNamespace(models=Models()))
    provider = GeminiTextProvider(client=client)

    planned = await provider.plan_tools(
        ToolPlanningRequest(
            model="gemini-test",
            system_instruction="Choose a tool only for explicit requests.",
            prompt="Przypomnij mi o raporcie za 10 minut.",
            tools=CONVERSATION_TOOL_DEFINITIONS,
        )
    )

    assert planned[0].name == "create_reminder"
    assert planned[0].arguments == {"message": "raport", "in_minutes": 10}
    config = calls[0]["config"]
    assert config.automatic_function_calling.disable is True
    assert {item.name for item in config.tools[0].function_declarations} >= {
        "create_reminder",
        "cancel_reminder",
    }
