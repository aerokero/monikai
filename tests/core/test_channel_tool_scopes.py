from __future__ import annotations

import pytest

from backend.conversation.tools import ConversationToolRequest
from backend.core.monikai import AudioLoop


def _channel_loop(*, scopes, require_confirmation):
    loop = object.__new__(AudioLoop)
    loop.channel_tool_scopes = set(scopes)
    loop.channel_require_confirmation = require_confirmation
    loop.permissions = {
        "list_smart_devices": False,
        "control_light": True,
        "manage_shopping_list": True,
    }
    loop.auto_allow_tools_without_confirmation = False
    loop.on_tool_confirmation = None
    return loop


@pytest.mark.asyncio
async def test_channel_profile_scopes_allow_read_only_and_block_unlisted_tools():
    loop = _channel_loop(
        scopes={"list_smart_devices"},
        require_confirmation=True,
    )

    assert await loop._authorize_conversation_tool(
        ConversationToolRequest("list_smart_devices")
    ) is True
    assert await loop._authorize_conversation_tool(
        ConversationToolRequest("control_light", {"target": "light.desk", "action": "turn_on"})
    ) is False


@pytest.mark.asyncio
async def test_channel_profile_can_explicitly_allow_mutation_without_confirmation():
    loop = _channel_loop(
        scopes={"control_light"},
        require_confirmation=False,
    )

    assert await loop._authorize_conversation_tool(
        ConversationToolRequest("control_light", {"target": "light.desk", "action": "turn_on"})
    ) is True


@pytest.mark.asyncio
async def test_channel_confirmation_cannot_be_bypassed_by_transport_auto_allow():
    loop = _channel_loop(
        scopes={"control_light"},
        require_confirmation=True,
    )
    loop.auto_allow_tools_without_confirmation = True

    assert await loop._authorize_conversation_tool(
        ConversationToolRequest("control_light", {"target": "light.desk", "action": "turn_on"})
    ) is False
