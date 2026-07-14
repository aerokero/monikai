"""Monika's own goals in the Minecraft world (v3 Phase D).

She decides what she wants to do in-world ("dokończyć ogród przy bazie")
and manages the list herself through the `minecraft_goals` tool. Open goals
are recalled when she joins the game, so her in-world life has continuity.

Storage: progression_state key 'minecraft_goals' (JSON list).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_KEY = "minecraft_goals"
_MAX_OPEN = 5


def _utciso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _goal_id(text: str) -> str:
    return "mcg_" + hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:12]


async def _load(db_path: Path | None) -> list[dict]:
    from backend.progression.state import get
    goals = await get(_KEY, db_path)
    return goals if isinstance(goals, list) else []


async def _save(goals: list[dict], db_path: Path | None) -> None:
    from backend.progression.state import set_
    await set_(_KEY, goals, db_path)


async def list_goals(db_path: Path | None = None, status: str = "open") -> list[dict]:
    goals = await _load(db_path)
    if status == "all":
        return goals
    return [g for g in goals if g.get("status") == status]


async def add_goal(text: str, db_path: Path | None = None) -> tuple[str, str]:
    """Add an open goal. Returns (id, "ok" | "dedup" | "full")."""
    text = text.strip()
    if not text:
        raise ValueError("empty goal text")
    goals = await _load(db_path)
    gid = _goal_id(text)
    if any(g.get("id") == gid and g.get("status") == "open" for g in goals):
        return gid, "dedup"
    if sum(1 for g in goals if g.get("status") == "open") >= _MAX_OPEN:
        return gid, "full"
    goals.append({"id": gid, "text": text, "status": "open", "created_at": _utciso()})
    await _save(goals, db_path)
    logger.info("minecraft goal added: %s", text)
    return gid, "ok"


async def complete_goal(id_or_text: str, db_path: Path | None = None) -> bool:
    """Mark a goal done by id or (sub)text match. Returns True if found."""
    goals = await _load(db_path)
    needle = id_or_text.strip().lower()
    for g in goals:
        if g.get("status") != "open":
            continue
        if g.get("id") == id_or_text or needle in str(g.get("text", "")).lower():
            g["status"] = "done"
            g["completed_at"] = _utciso()
            await _save(goals, db_path)
            logger.info("minecraft goal completed: %s", g.get("text"))
            return True
    return False


async def format_open_goals(db_path: Path | None = None) -> str:
    """Short prose list for prompt injection ('' when none)."""
    goals = await list_goals(db_path)
    if not goals:
        return ""
    items = "; ".join(str(g.get("text", "")) for g in goals)
    return f"Your own goals in this world: {items}."
