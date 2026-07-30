"""Smart-home execution isolated from Live transport and response authorship."""

from __future__ import annotations

from backend.conversation.tools import (
    ConversationToolRequest,
    ConversationToolResult,
)


class SmartHomeToolExecutor:
    def __init__(
        self,
        *,
        agents,
        on_device_update=None,
        on_error=None,
    ):
        self._agents = [agent for agent in agents if agent is not None]
        self._on_device_update = on_device_update
        self._on_error = on_error

    async def execute(
        self,
        request: ConversationToolRequest,
    ) -> ConversationToolResult:
        try:
            if request.name == "list_smart_devices":
                devices = self._serialize_all()
                if self._on_device_update:
                    self._on_device_update(devices)
                rendered = (
                    "No smart-home devices found in cache."
                    if not devices
                    else "Smart-home devices:\n"
                    + "\n".join(
                        f"{item.get('id') or item.get('ip')} | "
                        f"{item.get('alias')} | {item.get('type')} | "
                        f"{'ON' if item.get('is_on') else 'OFF'}"
                        for item in devices
                    )
                )
                return ConversationToolResult(request.name, rendered)

            if request.name != "control_light":
                return ConversationToolResult(
                    request.name,
                    "Unsupported smart-home tool.",
                    ok=False,
                )

            args = request.arguments
            target = str(args.get("target") or "").strip()
            action = str(args.get("action") or "").strip()
            brightness = args.get("brightness")
            color = args.get("color")
            if not target:
                raise ValueError("Device target is required.")
            if action not in {"turn_on", "turn_off", "set"}:
                raise ValueError("Unsupported light action.")
            if action == "set" and brightness is None and color is None:
                raise ValueError("Set action requires brightness or color.")
            if brightness is not None:
                brightness = int(brightness)
                if not 0 <= brightness <= 100:
                    raise ValueError("Brightness must be between 0 and 100.")
            if color is not None:
                color = str(color).strip()[:40]
                if not color:
                    raise ValueError("Color cannot be empty.")

            successes = []
            for agent in self._agents:
                result = await self._execute_on_agent(
                    agent,
                    target=target,
                    action=action,
                    brightness=brightness,
                    color=color,
                )
                if result:
                    successes.append(
                        f"{result} ({getattr(agent, 'platform', 'unknown')})"
                    )

            if not successes:
                rendered = (
                    f"Device '{target}' was not found or could not be updated."
                )
                if self._on_error:
                    self._on_error(rendered)
                return ConversationToolResult(
                    request.name,
                    rendered,
                    ok=False,
                )

            if self._on_device_update:
                self._on_device_update(self._serialize_all())
            return ConversationToolResult(
                request.name,
                "Updated: " + "; ".join(successes),
            )
        except Exception as exc:
            return ConversationToolResult(
                request.name,
                str(exc),
                ok=False,
            )

    def _serialize_all(self) -> list[dict]:
        devices = []
        for agent in self._agents:
            try:
                devices.extend(agent.serialize_devices() or [])
            except Exception:
                continue
        return devices

    @staticmethod
    async def _execute_on_agent(
        agent,
        *,
        target: str,
        action: str,
        brightness: int | None,
        color: str | None,
    ) -> str | None:
        if action == "turn_on":
            return f"Turned ON '{target}'." if await agent.turn_on(target) else None
        if action == "turn_off":
            return f"Turned OFF '{target}'." if await agent.turn_off(target) else None

        changes = []
        if brightness is not None and await agent.set_brightness(
            target,
            brightness,
        ):
            changes.append(f"brightness={brightness}%")
        if color is not None and await agent.set_color(target, color):
            changes.append(f"color={color}")
        return f"Updated '{target}': {', '.join(changes)}." if changes else None

