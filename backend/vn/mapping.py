"""VN scene state sent to the frontend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SceneState:
    """Visual state for the VN frontend."""
    bg: str = "room_day"
    outfit: str = "casual"
    expr: str = "neutral"
    light: str = "natural"
    ambience: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}
