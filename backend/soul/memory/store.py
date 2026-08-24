"""Async CRUD layer over the memory_entries table in monika.db.

The store is the only place that reads/writes memory_entries.
Callers use MemoryEntry (Pydantic) and never touch raw SQL.

Deduplication: entries with the same (type, content_hash) are silently
dropped — returns ("id", "dedup") so callers can react if needed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from backend.soul.db import get_db
from backend.soul.models import MemoryEntry

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _content_hash(type_: str, content: str) -> str:
    key = f"{type_}|{content.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _entry_id(type_: str, content: str) -> str:
    h = _content_hash(type_, content)[:16]
    return f"mem_{h}"


def _row_to_entry(row) -> MemoryEntry:
    return MemoryEntry(
        id=row["id"],
        type=row["type"],
        content=row["content"],
        importance=row["importance"],
        embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        last_accessed=(
            datetime.fromisoformat(row["last_accessed"])
            if row["last_accessed"]
            else None
        ),
        tags=json.loads(row["tags"] or "[]"),
        entities=json.loads(row["entities"] or "[]"),
        perspective=row["perspective"] or "factual",
        created_at=datetime.fromisoformat(row["created_at"]),
        source_session=row["source_session"],
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

async def add(
    entry: MemoryEntry,
    db_path: Path | None = None,
) -> tuple[str, Literal["ok", "dedup"]]:
    """Insert a memory entry. Returns (id, "dedup") if a duplicate exists."""
    content_hash = _content_hash(entry.type, entry.content)
    entry_id = _entry_id(entry.type, entry.content)

    async with get_db(db_path) as conn:
        existing = await conn.execute(
            "SELECT id FROM memory_entries WHERE id = ?",
            (entry_id,),
        )
        row = await existing.fetchone()
        if row:
            logger.debug("Dedup: %s", entry_id)
            return entry_id, "dedup"

        await conn.execute(
            """
            INSERT INTO memory_entries
                (id, type, content, importance, embedding,
                 last_accessed, tags, entities, perspective,
                 created_at, source_session)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                entry.type,
                entry.content,
                entry.importance,
                json.dumps(entry.embedding) if entry.embedding else None,
                _iso(entry.last_accessed) if entry.last_accessed else None,
                json.dumps(entry.tags),
                json.dumps(entry.entities),
                entry.perspective,
                _iso(entry.created_at),
                entry.source_session,
            ),
        )
        await conn.commit()

    logger.debug("Stored %s (%s, importance=%.1f)", entry_id, entry.type, entry.importance)
    return entry_id, "ok"


async def update_importance(
    entry_id: str,
    importance: float,
    db_path: Path | None = None,
) -> None:
    async with get_db(db_path) as conn:
        await conn.execute(
            "UPDATE memory_entries SET importance = ? WHERE id = ?",
            (importance, entry_id),
        )
        await conn.commit()


async def touch(entry_id: str, db_path: Path | None = None) -> None:
    """Update last_accessed to now (call after a retrieval hit)."""
    async with get_db(db_path) as conn:
        await conn.execute(
            "UPDATE memory_entries SET last_accessed = ? WHERE id = ?",
            (_iso(_utcnow()), entry_id),
        )
        await conn.commit()


async def promote(
    entry_id: str,
    new_type: Literal["episodic", "semantic", "world"],
    db_path: Path | None = None,
) -> None:
    """Promote an STM entry to a long-term tier (changes type in place)."""
    async with get_db(db_path) as conn:
        await conn.execute(
            "UPDATE memory_entries SET type = ? WHERE id = ?",
            (new_type, entry_id),
        )
        await conn.commit()
    logger.debug("Promoted %s → %s", entry_id, new_type)


async def delete_batch(
    ids: list[str],
    db_path: Path | None = None,
) -> int:
    """Delete multiple entries. Returns count deleted."""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    async with get_db(db_path) as conn:
        cursor = await conn.execute(
            f"DELETE FROM memory_entries WHERE id IN ({placeholders})",
            ids,
        )
        await conn.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def get(entry_id: str, db_path: Path | None = None) -> MemoryEntry | None:
    async with get_db(db_path) as conn:
        cursor = await conn.execute(
            "SELECT * FROM memory_entries WHERE id = ?", (entry_id,)
        )
        row = await cursor.fetchone()
    return _row_to_entry(row) if row else None


async def list_recent(
    limit: int = 20,
    types: list[str] | None = None,
    db_path: Path | None = None,
) -> list[MemoryEntry]:
    """Return most recently created entries, optionally filtered by type."""
    sql = "SELECT * FROM memory_entries"
    params: list = []
    if types:
        sql += " WHERE type IN ({})".format(",".join("?" * len(types)))
        params.extend(types)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    async with get_db(db_path) as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
    return [_row_to_entry(r) for r in rows]


async def get_stm(
    older_than: datetime | None = None,
    db_path: Path | None = None,
) -> list[MemoryEntry]:
    """Return all STM entries, optionally only those created before a cutoff."""
    sql = "SELECT * FROM memory_entries WHERE type = 'stm'"
    params: list = []
    if older_than:
        sql += " AND created_at < ?"
        params.append(_iso(older_than))
    sql += " ORDER BY created_at ASC"

    async with get_db(db_path) as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
    return [_row_to_entry(r) for r in rows]


def _fts_query(query: str) -> str:
    """Quote plain search terms for SQLite FTS syntax safety."""
    """Quote plain search terms for SQLite FTS syntax safety with prefix matching."""
    import re

    raw_tokens = re.findall(r"[\w\-]+", query or "", re.UNICODE)
    return " OR ".join(f'"{token}"' for token in raw_tokens)
    raw_tokens = [t for t in re.findall(r"[\w\-]+", query or "", re.UNICODE) if len(t) >= 2]
    if not raw_tokens:
        return ""
    return " OR ".join(f'{token}*' for token in raw_tokens)



async def search_fts(
    query: str,
    types: list[str] | None = None,
    limit: int = 10,
    db_path: Path | None = None,
) -> list[tuple[MemoryEntry, float]]:
    """FTS5 keyword search. Returns (entry, bm25_abs) pairs, best first.

    bm25_abs is |bm25()|, higher = better match. Used by retrieval.py to
    compute the relevance component of the Stanford score.
    """
    if not query.strip():
        return []

    fts_query = _fts_query(query)
    if not fts_query:
        return []

    sql = (
        "SELECT e.*, (-bm25(memory_fts)) AS bm25_abs "
        "FROM memory_fts "
        "JOIN memory_entries e ON e.rowid = memory_fts.rowid "
        "WHERE memory_fts MATCH ?"
    )
    params: list = [fts_query]
    if types:
        sql += " AND e.type IN ({})".format(",".join("?" * len(types)))
        params.extend(types)
    sql += " ORDER BY bm25_abs DESC LIMIT ?"
    params.append(limit)

    async with get_db(db_path) as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()

    return [(_row_to_entry(r), float(r["bm25_abs"])) for r in rows]
