"""Progression state persistence — read/write to progression_state SQLite table.

Key/value JSON store. Each key holds a JSON-serialisable value.
Typed helpers expose the semantics: unlocked_discoveries, milestones, etc.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.soul.db import get_db

logger = logging.getLogger(__name__)

_KEY_DISCOVERIES = "unlocked_discoveries"   # list[str] of discovery IDs
_KEY_MILESTONES = "milestones"              # list[{id, reached_at, effect}]
_KEY_ACTIVE_GOALS = "active_goals"          # list[{id, kind, progress}]
_KEY_ACTIVE_RITUALS = "active_rituals"      # list[{id, kind, completed_today}]
_KEY_TURN_COUNT = "turn_count"              # int
_KEY_ANNIVERSARIES = "anniversaries"        # list[{label, date}]
_KEY_BOND_STATE = "bond_state"              # {closeness, streak_days, ...}



# ---------------------------------------------------------------------------
# Raw key/value
# ---------------------------------------------------------------------------

async def get(key: str, db_path: Path | None = None) -> Any | None:
    async with get_db(db_path) as conn:
        cursor = await conn.execute(
            "SELECT value FROM progression_state WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
    return json.loads(row["value"]) if row else None


async def set_(key: str, value: Any, db_path: Path | None = None) -> None:
    serialised = json.dumps(value, ensure_ascii=False, default=str)
    now = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    async with get_db(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO progression_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, serialised, now),
        )
        await conn.commit()


# ---------------------------------------------------------------------------
# Typed helpers — Discoveries
# ---------------------------------------------------------------------------

async def get_unlocked_discoveries(db_path: Path | None = None) -> list[str]:
    return (await get(_KEY_DISCOVERIES, db_path)) or []


async def unlock_discovery(discovery_id: str, db_path: Path | None = None) -> bool:
    """Unlock a discovery. Returns True if it was newly unlocked."""
    unlocked = await get_unlocked_discoveries(db_path)
    if discovery_id in unlocked:
        return False
    unlocked.append(discovery_id)
    await set_(_KEY_DISCOVERIES, unlocked, db_path)
    return True


async def is_unlocked(discovery_id: str, db_path: Path | None = None) -> bool:
    return discovery_id in (await get_unlocked_discoveries(db_path))


# ---------------------------------------------------------------------------
# Typed helpers — Milestones
# ---------------------------------------------------------------------------

async def get_milestones(db_path: Path | None = None) -> list[dict]:
    return (await get(_KEY_MILESTONES, db_path)) or []


async def add_milestone(
    milestone_id: str,
    effect: str,
    db_path: Path | None = None,
) -> bool:
    """Add a milestone. Returns True if newly added."""
    milestones = await get_milestones(db_path)
    if any(m["id"] == milestone_id for m in milestones):
        return False
    milestones.append({
        "id": milestone_id,
        "reached_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "effect": effect,
    })
    await set_(_KEY_MILESTONES, milestones, db_path)
    return True


# ---------------------------------------------------------------------------
# Typed helpers — Turn counter
# ---------------------------------------------------------------------------

async def increment_turn_count(db_path: Path | None = None) -> int:
    count = (await get(_KEY_TURN_COUNT, db_path)) or 0
    count += 1
    await set_(_KEY_TURN_COUNT, count, db_path)
    return count


async def get_turn_count(db_path: Path | None = None) -> int:
    return (await get(_KEY_TURN_COUNT, db_path)) or 0


# ---------------------------------------------------------------------------
# Typed helpers — Goals
# ---------------------------------------------------------------------------

async def get_active_goals(db_path: Path | None = None) -> list[dict]:
    return (await get(_KEY_ACTIVE_GOALS, db_path)) or []


async def set_active_goals(goals: list[dict], db_path: Path | None = None) -> None:
    await set_(_KEY_ACTIVE_GOALS, goals, db_path)


# ---------------------------------------------------------------------------
# Typed helpers — Rituals
# ---------------------------------------------------------------------------

async def get_active_rituals(db_path: Path | None = None) -> list[dict]:
    return (await get(_KEY_ACTIVE_RITUALS, db_path)) or []


async def set_active_rituals(rituals: list[dict], db_path: Path | None = None) -> None:
    await set_(_KEY_ACTIVE_RITUALS, rituals, db_path)


# ---------------------------------------------------------------------------
# Typed helpers — Bond state (replaces relationship_metrics scalars)
# ---------------------------------------------------------------------------

async def get_bond_state(db_path: Path | None = None) -> dict:
    return (await get(_KEY_BOND_STATE, db_path)) or {
        "closeness": 0.0,
        "streak_days": 0,
        "last_interaction_day": "",
    }


async def update_bond_state(updates: dict, db_path: Path | None = None) -> dict:
    bond = await get_bond_state(db_path)
    bond.update(updates)
    await set_(_KEY_BOND_STATE, bond, db_path)
    return bond
