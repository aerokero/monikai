from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(ODY_ROOT))

from src.builtin_actions import action_home_assistant_control  # noqa: E402
from src.home_assistant_runtime import set_home_assistant_agent  # noqa: E402
from src.tools.smart_home import do_home_assistant_control  # noqa: E402
from backend.agents.home_assistant_agent import HomeAssistantAgent  # noqa: E402


class FakeHomeAssistant:
    ha_url = "http://ha.test:8123"
    ha_token = "secret"

    def __init__(self):
        self.calls = []
        self.entities = {
            "light.desk": {"state": "off"},
            "light.wszystkie_swiatla": {"state": "on"},
            "scene.tryb_nocny": {"state": "scening"},
        }

    async def _resolve_entity_id(self, target):
        aliases = {
            "tryb nocny": "scene.tryb_nocny",
            "all lights": "light.wszystkie_swiatla",
        }
        entity_id = aliases.get(target.casefold(), target)
        return entity_id if entity_id in self.entities else None

    async def turn_on(self, target):
        self.calls.append(("turn_on", target))
        return True

    async def turn_off(self, target):
        self.calls.append(("turn_off", target))
        return True

    async def toggle(self, target):
        self.calls.append(("toggle", target))
        return True

    async def set_brightness(self, target, brightness):
        self.calls.append(("set_brightness", target, brightness))
        return True

    async def set_color(self, target, color):
        self.calls.append(("set_color", target, color))
        return True


@pytest.mark.asyncio
async def test_home_assistant_task_controls_only_resolved_entity():
    agent = FakeHomeAssistant()

    result = await action_home_assistant_control(
        owner="owner",
        home_assistant_agent=agent,
        prompt=json.dumps({"target": "light.desk", "action": "toggle"}),
    )

    assert result == ("Toggled light.desk.", True)
    assert agent.calls == [("toggle", "light.desk")]


@pytest.mark.asyncio
async def test_home_assistant_task_allows_interactive_broad_target_but_not_scheduled():
    agent = FakeHomeAssistant()

    broad = await action_home_assistant_control(
        owner="owner",
        home_assistant_agent=agent,
        prompt=json.dumps({"target": "all lights", "action": "turn_off"}),
        allow_broad_targets=True,
    )
    scheduled_broad = await action_home_assistant_control(
        owner="owner",
        home_assistant_agent=agent,
        prompt=json.dumps({"target": "all lights", "action": "turn_off"}),
    )
    unknown = await action_home_assistant_control(
        owner="owner",
        home_assistant_agent=agent,
        prompt=json.dumps({"target": "switch.secret", "action": "turn_on"}),
    )

    assert broad == ("Turned off all lights.", True)
    assert scheduled_broad[1] is False
    assert "one explicit" in scheduled_broad[0]
    assert unknown[1] is False
    assert "not found" in unknown[0]
    assert agent.calls == [("turn_off", "all lights")]


@pytest.mark.asyncio
async def test_interactive_broad_target_reaches_ha_all_service_without_alias():
    agent = FakeHomeAssistant()
    result = await action_home_assistant_control(
        owner="owner",
        home_assistant_agent=agent,
        prompt=json.dumps({"target": "all lights", "action": "turn_off"}),
        allow_broad_targets=True,
    )

    assert result == ("Turned off all lights.", True)
    assert agent.calls == [("turn_off", "all lights")]


@pytest.mark.asyncio
async def test_home_assistant_agent_uses_light_all_service_and_reports_failure():
    agent = HomeAssistantAgent(
        ha_url="http://ha.test:8123",
        ha_token="secret",
    )
    agent.entities = {"light.desk": {"state": "on"}}
    agent._post = AsyncMock(return_value=True)

    assert await agent.turn_off("wszystko dosłownie") is True
    agent._post.assert_awaited_once_with(
        "/services/light/turn_off",
        {"entity_id": "all"},
    )
    assert agent.entities["light.desk"]["state"] == "off"

    agent._post.reset_mock()
    agent._post.return_value = False
    assert await agent.turn_on("all lights") is False
    agent._post.assert_awaited_once_with(
        "/services/light/turn_on",
        {"entity_id": "all"},
    )


@pytest.mark.asyncio
async def test_home_assistant_task_supports_brightness_and_color():
    agent = FakeHomeAssistant()

    result = await action_home_assistant_control(
        owner="owner",
        home_assistant_agent=agent,
        prompt=json.dumps({
            "target": "light.desk",
            "action": "set",
            "brightness": 65,
            "color": "warm",
        }),
    )

    assert result == ("Updated light.desk: brightness=65%, color=warm.", True)
    assert agent.calls == [
        ("set_brightness", "light.desk", 65),
        ("set_color", "light.desk", "warm"),
    ]


@pytest.mark.asyncio
async def test_native_home_assistant_tool_uses_shared_runtime_for_named_scene():
    agent = FakeHomeAssistant()
    set_home_assistant_agent(agent)
    try:
        result = await do_home_assistant_control(
            json.dumps({"target": "tryb nocny", "action": "turn_on"}),
            owner="owner",
        )
    finally:
        set_home_assistant_agent(None)

    assert result == {"output": "Turned on scene.tryb_nocny.", "exit_code": 0}
    assert agent.calls == [("turn_on", "scene.tryb_nocny")]


@pytest.mark.asyncio
async def test_native_home_assistant_tool_allows_explicit_all_lights_request():
    agent = FakeHomeAssistant()
    set_home_assistant_agent(agent)
    try:
        result = await do_home_assistant_control(
            json.dumps({"target": "all lights", "action": "turn_off"}),
            owner="owner",
        )
    finally:
        set_home_assistant_agent(None)

    assert result == {
        "output": "Turned off all lights.",
        "exit_code": 0,
    }
    assert agent.calls == [("turn_off", "all lights")]
