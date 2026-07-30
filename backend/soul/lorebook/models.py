"""Typed lorebook domain models.

Lore is deliberately separate from ``MemoryEntry``. A lore fact is true inside
a named world; personal memory is about the user or a shared experience.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


RealityMode = Literal["grounded", "crossover", "roleplay", "ambiguous"]
LorebookKind = Literal["reality", "imported_fiction", "custom", "scenario"]
LoreEntryType = Literal[
    "knowledge", "scene", "dialogue_example", "behavior_instruction"
]
LoreMatchMode = Literal["any", "all", "primary_and_secondary"]
CanonStatus = Literal["canonical", "learned", "proposed", "superseded"]


class Lorebook(BaseModel):
    id: str
    name: str
    description: str = ""
    kind: LorebookKind = "custom"
    trusted: bool = False
    editable: bool = True
    enabled: bool = True
    default_mode: RealityMode = "grounded"
    token_budget: int = Field(default=1800, gt=0)
    priority: int = 50
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean or ":" in clean:
            raise ValueError("lorebook id must be non-empty and cannot contain ':'")
        return clean


class LoreEntry(BaseModel):
    id: str
    lorebook_id: str
    title: str
    content: str
    entry_type: LoreEntryType = "knowledge"
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    match_mode: LoreMatchMode = "any"
    priority: int = 50
    constant: bool = False
    enabled: bool = True
    sticky_turns: int = Field(default=0, ge=0)
    canon_status: CanonStatus = "canonical"
    source: str = "manual"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("id", "lorebook_id")
    @classmethod
    def validate_component_id(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean or ":" in clean:
            raise ValueError("lore ids must be non-empty and cannot contain ':'")
        return clean

    @field_validator("title", "content")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("title and content must be non-empty")
        return clean

    @property
    def uid(self) -> str:
        return f"{self.lorebook_id}:{self.id}"


class WorldStack(BaseModel):
    conversation_id: str
    reality_mode: RealityMode = "grounded"
    lorebook_ids: list[str] = Field(default_factory=list)
    pinned_entries: list[str] = Field(default_factory=list)
    token_budget: int | None = Field(default=None, gt=0)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("lorebook_ids")
    @classmethod
    def unique_books(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))

    @field_validator("pinned_entries")
    @classmethod
    def valid_pins(cls, values: list[str]) -> list[str]:
        clean = list(dict.fromkeys(str(v).strip() for v in values if str(v).strip()))
        if any(":" not in value for value in clean):
            raise ValueError("pinned entries must use 'lorebook_id:entry_id'")
        return clean
