import pytest

from backend.conversation.tools import ConversationToolRequest
from backend.core.smart_home_tool_executor import SmartHomeToolExecutor


class FakeSmartHomeAgent:
    def __init__(self, platform, devices, *, succeeds=True):
        self.platform = platform
        self.devices = devices
        self.succeeds = succeeds
        self.calls = []

    def serialize_devices(self):
        return list(self.devices)

    async def turn_on(self, target):
        self.calls.append(("turn_on", target))
        return self.succeeds

    async def turn_off(self, target):
        self.calls.append(("turn_off", target))
        return self.succeeds

    async def set_brightness(self, target, brightness):
        self.calls.append(("set_brightness", target, brightness))
        return self.succeeds

    async def set_color(self, target, color):
        self.calls.append(("set_color", target, color))
        return self.succeeds


@pytest.mark.asyncio
async def test_list_smart_devices_merges_platforms_and_emits_update():
    updates = []
    executor = SmartHomeToolExecutor(
        agents=[
            FakeSmartHomeAgent(
                "kasa",
                [{"id": "one", "alias": "Biurko", "type": "bulb", "is_on": True}],
            ),
            FakeSmartHomeAgent(
                "hue",
                [{"id": "two", "alias": "Salon", "type": "bulb", "is_on": False}],
            ),
        ],
        on_device_update=updates.append,
    )

    result = await executor.execute(ConversationToolRequest("list_smart_devices"))

    assert result.ok is True
    assert "Biurko" in result.result
    assert "Salon" in result.result
    assert len(updates) == 1
    assert len(updates[0]) == 2


@pytest.mark.asyncio
async def test_control_light_executes_once_per_platform_and_reports_success():
    matching = FakeSmartHomeAgent("hue", [], succeeds=True)
    missing = FakeSmartHomeAgent("kasa", [], succeeds=False)
    executor = SmartHomeToolExecutor(agents=[missing, matching])

    result = await executor.execute(
        ConversationToolRequest(
            "control_light",
            {"target": "Salon", "action": "turn_on"},
        )
    )

    assert result.ok is True
    assert missing.calls == [("turn_on", "Salon")]
    assert matching.calls == [("turn_on", "Salon")]
    assert "hue" in result.result


@pytest.mark.asyncio
async def test_set_requires_a_change_and_valid_brightness():
    agent = FakeSmartHomeAgent("hue", [])
    executor = SmartHomeToolExecutor(agents=[agent])

    empty = await executor.execute(
        ConversationToolRequest(
            "control_light",
            {"target": "Salon", "action": "set"},
        )
    )
    invalid = await executor.execute(
        ConversationToolRequest(
            "control_light",
            {"target": "Salon", "action": "set", "brightness": 101},
        )
    )

    assert empty.ok is False
    assert invalid.ok is False
    assert agent.calls == []
