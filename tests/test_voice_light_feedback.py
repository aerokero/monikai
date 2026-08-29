import unittest
import asyncio
from unittest.mock import AsyncMock
from backend.agents.voice_light_feedback import VoiceLightFeedbackController, VoiceFeedbackState
from backend.agents.home_assistant_agent import HomeAssistantAgent


class TestVoiceLightFeedback(unittest.IsolatedAsyncioTestCase):

    async def test_voice_light_feedback_lifecycle_when_bulb_was_off(self):
        mock_ha = AsyncMock()
        mock_ha.get_entity_raw_state.return_value = {
            "entity_id": "light.kuchnia_zarowka_1_ts0505b",
            "state": "off",
            "attributes": {},
        }

        controller = VoiceLightFeedbackController(
            ha_agent=mock_ha,
            entity_id="light.kuchnia_zarowka_1_ts0505b",
            enabled=True,
        )

        self.assertEqual(controller.current_state, VoiceFeedbackState.IDLE)

        # 1. Enter LISTENING
        await controller.set_state(VoiceFeedbackState.LISTENING)
        await asyncio.sleep(0.05)
        self.assertEqual(controller.current_state, VoiceFeedbackState.LISTENING)
        mock_ha.get_entity_raw_state.assert_awaited_once_with("light.kuchnia_zarowka_1_ts0505b")
        mock_ha.set_light_state.assert_awaited()
        args, kwargs = mock_ha.set_light_state.call_args
        self.assertEqual(kwargs.get("rgb_color"), (0, 75, 230))

        # 2. Enter THINKING
        await controller.set_state(VoiceFeedbackState.THINKING)
        await asyncio.sleep(0.05)
        self.assertEqual(controller.current_state, VoiceFeedbackState.THINKING)
        args, kwargs = mock_ha.set_light_state.call_args
        self.assertEqual(kwargs.get("rgb_color"), (140, 230, 255))

        # 3. Enter SPEAKING
        await controller.set_state(VoiceFeedbackState.SPEAKING)
        await asyncio.sleep(0.05)
        self.assertEqual(controller.current_state, VoiceFeedbackState.SPEAKING)
        args, kwargs = mock_ha.set_light_state.call_args
        self.assertEqual(kwargs.get("rgb_color"), (0, 230, 115))

        # 4. Enter IDLE (restore initial state)
        await controller.set_state(VoiceFeedbackState.IDLE)
        self.assertEqual(controller.current_state, VoiceFeedbackState.IDLE)
        mock_ha.restore_entity_state.assert_awaited_once_with(
            "light.kuchnia_zarowka_1_ts0505b",
            {"entity_id": "light.kuchnia_zarowka_1_ts0505b", "state": "off", "attributes": {}},
        )

    async def test_voice_light_feedback_lifecycle_when_bulb_was_on(self):
        mock_ha = AsyncMock()
        initial_state = {
            "entity_id": "light.kuchnia_zarowka_1_ts0505b",
            "state": "on",
            "attributes": {
                "brightness": 200,
                "color_temp_kelvin": 2700,
            },
        }
        mock_ha.get_entity_raw_state.return_value = initial_state

        controller = VoiceLightFeedbackController(
            ha_agent=mock_ha,
            entity_id="light.kuchnia_zarowka_1_ts0505b",
            enabled=True,
        )

        await controller.set_state(VoiceFeedbackState.LISTENING)
        await asyncio.sleep(0.05)
        await controller.set_state(VoiceFeedbackState.SPEAKING)
        await asyncio.sleep(0.05)
        await controller.set_state(VoiceFeedbackState.IDLE)

        mock_ha.restore_entity_state.assert_awaited_once_with(
            "light.kuchnia_zarowka_1_ts0505b",
            initial_state,
        )

    async def test_ha_agent_restore_state_methods(self):
        agent = HomeAssistantAgent(ha_url="http://fake-ha:8123", ha_token="test-token")
        agent._post = AsyncMock(return_value=True)
        agent.entities = {"light.kuchnia_zarowka_1_ts0505b": {}}

        # Test restoring an "off" light
        await agent.restore_entity_state("light.kuchnia_zarowka_1_ts0505b", {"state": "off", "attributes": {}})
        agent._post.assert_awaited_with(
            "/services/light/turn_off",
            {"entity_id": "light.kuchnia_zarowka_1_ts0505b", "transition": 1.0},
        )

        # Test restoring an "on" light with brightness and color temp
        await agent.restore_entity_state(
            "light.kuchnia_zarowka_1_ts0505b",
            {"state": "on", "attributes": {"brightness": 180, "color_temp_kelvin": 3000}},
        )
        agent._post.assert_awaited_with(
            "/services/light/turn_on",
            {"entity_id": "light.kuchnia_zarowka_1_ts0505b", "transition": 1.0, "brightness": 180, "color_temp_kelvin": 3000},
        )


if __name__ == "__main__":
    unittest.main()

