"""Contracts shared by context compilation and text-model providers."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.soul.lorebook.activation import ActivatedLore


@dataclass(frozen=True)
class CompiledConversationContext:
    conversation_id: str
    turn_id: str | None
    system_instruction: str
    user_prompt: str
    activated_lore: list[ActivatedLore] = field(default_factory=list)
    reality_mode: str = "grounded"
