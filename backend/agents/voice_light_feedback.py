"""Visual voice feedback indicator using smart home lighting (Home Assistant).

Synchronizes smart bulb color and pulsing with voice interaction states:
- LISTENING: Darker, slower pulsing blue (deep cyan/blue).
- THINKING: Very bright, pulsing light blue/cyan.
- SPEAKING: Monika's emerald green pulse during audio synthesis/speech.
- IDLE: Restores previous state (color, brightness, or off state).
"""

from __future__ import annotations

import asyncio
import enum
from typing import Any, Dict, Optional, Tuple


class VoiceFeedbackState(str, enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class VoiceLightFeedbackController:
    """Controls smart light visual feedback during Monika's voice interactions."""

    def __init__(
        self,
        ha_agent: Any,
        entity_id: str = "light.kuchnia_zarowka_1_ts0505b",
        enabled: bool = True,
    ):
        self.ha_agent = ha_agent
        self.entity_id = entity_id
        self.enabled = enabled
        self.current_state = VoiceFeedbackState.IDLE
        self._saved_initial_state: Optional[Dict[str, Any]] = None
        self._pulse_task: Optional[asyncio.Task] = None
        self._state_lock = asyncio.Lock()

        # Color & Pulse profiles
        # (RGB tuple, min_brightness, max_brightness, transition_sec, step_sleep_sec)
        self._profiles = {
            VoiceFeedbackState.LISTENING: {
                "rgb": (0, 75, 230),         # Darker blue / cobalt cyan
                "min_bri": 65,
                "max_bri": 150,
                "transition": 1.1,
                "interval": 1.2,
            },
            VoiceFeedbackState.THINKING: {
                "rgb": (140, 230, 255),      # Very bright light blue / glowing cyan
                "min_bri": 170,
                "max_bri": 255,
                "transition": 0.5,
                "interval": 0.6,
            },
            VoiceFeedbackState.SPEAKING: {
                "rgb": (0, 230, 115),        # Monika's vibrant emerald green
                "min_bri": 100,
                "max_bri": 240,
                "transition": 0.6,
                "interval": 0.7,
            },
        }

    async def set_state(self, new_state: VoiceFeedbackState | str) -> None:
        """Switch visual state asynchronously."""
        if isinstance(new_state, str):
            try:
                new_state = VoiceFeedbackState(new_state.lower())
            except ValueError:
                return

        if not self.enabled or not self.ha_agent:
            return

        async with self._state_lock:
            if new_state == self.current_state:
                return

            prev_state = self.current_state
            self.current_state = new_state

            # If starting interaction from IDLE, snapshot original light state
            if prev_state == VoiceFeedbackState.IDLE:
                try:
                    self._saved_initial_state = await self.ha_agent.get_entity_raw_state(self.entity_id)
                except Exception as exc:
                    print(f"[VOICE LIGHT] Failed to snapshot initial state: {exc}")
                    self._saved_initial_state = None

            # Stop active animation loop
            if self._pulse_task and not self._pulse_task.done():
                self._pulse_task.cancel()
                try:
                    await self._pulse_task
                except asyncio.CancelledError:
                    pass
                self._pulse_task = None

            if new_state == VoiceFeedbackState.IDLE:
                # Restore original light state
                if self._saved_initial_state is not None:
                    try:
                        await self.ha_agent.restore_entity_state(
                            self.entity_id, self._saved_initial_state
                        )
                        print(f"[VOICE LIGHT] Restored {self.entity_id} to initial state.")
                    except Exception as exc:
                        print(f"[VOICE LIGHT] Error restoring state: {exc}")
                    finally:
                        self._saved_initial_state = None
            else:
                # Start pulse animation task for active state
                self._pulse_task = asyncio.create_task(
                    self._run_pulse_animation(new_state),
                    name=f"voice-light-{new_state.value}",
                )

    async def _run_pulse_animation(self, state: VoiceFeedbackState) -> None:
        """Run smooth breathing/pulsing loop for the target state."""
        profile = self._profiles.get(state)
        if not profile:
            return

        rgb = profile["rgb"]
        min_bri = profile["min_bri"]
        max_bri = profile["max_bri"]
        transition = profile["transition"]
        interval = profile["interval"]

        try:
            # Immediate initial pulse to max brightness
            await self.ha_agent.set_light_state(
                self.entity_id,
                rgb_color=rgb,
                brightness=max_bri,
                transition=transition,
            )

            toggle = False
            while True:
                await asyncio.sleep(interval)
                target_bri = min_bri if toggle else max_bri
                toggle = not toggle

                await self.ha_agent.set_light_state(
                    self.entity_id,
                    rgb_color=rgb,
                    brightness=target_bri,
                    transition=transition,
                )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[VOICE LIGHT] Pulse animation error for {state.value}: {exc}")

    def update_config(self, *, enabled: Optional[bool] = None, entity_id: Optional[str] = None) -> None:
        """Update controller settings dynamically."""
        if enabled is not None:
            self.enabled = bool(enabled)
        if entity_id:
            self.entity_id = entity_id

