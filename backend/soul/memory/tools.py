"""Self-editing memory tools (Letta/MemGPT-inspired).

These are callable by Monika via function-calling to manage her own memory.
They wrap store.py operations with higher-level semantics.

Tools:
  memory_revise(entry_id, new_content)  — edit the content of an entry
  memory_promote(entry_id)              — force STM → LTM promotion
  memory_rethink(entry_id)             — re-score importance heuristically
  memory_pin(entry_id)                 — pin entry (importance=10, never discarded)

Phase 3: memory_rethink will call Ollama for re-scoring.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.soul.memory import store
from backend.soul.memory.importance import score as score_importance

logger = logging.getLogger(__name__)


async def memory_revise(
    entry_id: str,
    new_content: str,
    db_path: Path | None = None,
) -> bool:
    """Replace the content of a memory entry and re-score its importance.

    Returns True if the entry was found and updated, False otherwise.
    """
    entry = await store.get(entry_id, db_path=db_path)
    if entry is None:
        logger.warning("memory_revise: entry %s not found", entry_id)
        return False

    new_importance = await score_importance(
        content=new_content,
        type_=entry.type,
        entities=entry.entities,
        tags=entry.tags,
    )

    async with __import__("backend.soul.db", fromlist=["get_db"]).get_db(db_path) as conn:
        await conn.execute(
            "UPDATE memory_entries SET content = ?, importance = ? WHERE id = ?",
            (new_content, new_importance, entry_id),
        )
        await conn.commit()

    logger.info("memory_revise: updated %s (importance %.1f → %.1f)", entry_id, entry.importance, new_importance)
    return True


async def memory_promote(
    entry_id: str,
    db_path: Path | None = None,
) -> str | None:
    """Force promote an STM entry to LTM.

    Returns the new type ('episodic' or 'semantic'), or None if not found.
    """
    from backend.soul.memory.compaction import _classify_entry

    entry = await store.get(entry_id, db_path=db_path)
    if entry is None:
        logger.warning("memory_promote: entry %s not found", entry_id)
        return None

    if entry.type != "stm":
        logger.debug("memory_promote: %s is already %s", entry_id, entry.type)
        return entry.type

    new_type = _classify_entry(entry)
    await store.promote(entry_id, new_type, db_path=db_path)
    logger.info("memory_promote: %s → %s", entry_id, new_type)
    return new_type


async def memory_rethink(
    entry_id: str,
    db_path: Path | None = None,
) -> float | None:
    """Re-score an entry's importance and update it in the store.

    Returns the new importance score, or None if entry not found.
    Phase 3: replaces heuristic with Ollama call.
    """
    entry = await store.get(entry_id, db_path=db_path)
    if entry is None:
        logger.warning("memory_rethink: entry %s not found", entry_id)
        return None

    new_importance = await score_importance(
        content=entry.content,
        type_=entry.type,
        entities=entry.entities,
        tags=entry.tags,
    )
    await store.update_importance(entry_id, new_importance, db_path=db_path)
    logger.info("memory_rethink: %s %.1f → %.1f", entry_id, entry.importance, new_importance)
    return new_importance


async def memory_pin(
    entry_id: str,
    db_path: Path | None = None,
) -> bool:
    """Pin an entry — set importance to 10.0 and promote to LTM if needed.

    Pinned entries always score high in retrieval and survive compaction.
    Returns True if found and pinned.
    """
    entry = await store.get(entry_id, db_path=db_path)
    if entry is None:
        logger.warning("memory_pin: entry %s not found", entry_id)
        return False

    await store.update_importance(entry_id, 10.0, db_path=db_path)

    if entry.type == "stm":
        await store.promote(entry_id, "episodic", db_path=db_path)

    logger.info("memory_pin: pinned %s", entry_id)
    return True
