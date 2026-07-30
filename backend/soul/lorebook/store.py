"""SQLite persistence for lorebooks, entries, world stacks, and diagnostics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.soul.db import get_db

from .models import LoreEntry, Lorebook, WorldStack


def _iso(value: datetime | None = None) -> str:
    dt = value or datetime.now(tz=timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _dt(value: str | None) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.now(tz=timezone.utc)


def _row_to_book(row) -> Lorebook:
    return Lorebook(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        kind=row["kind"],
        trusted=bool(row["trusted"]),
        editable=bool(row["editable"]),
        enabled=bool(row["enabled"]),
        default_mode=row["default_mode"],
        token_budget=row["token_budget"],
        priority=row["priority"],
        metadata=json.loads(row["metadata"] or "{}"),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _row_to_entry(row) -> LoreEntry:
    return LoreEntry(
        id=row["entry_id"],
        lorebook_id=row["lorebook_id"],
        title=row["title"],
        content=row["content"],
        entry_type=row["entry_type"],
        keys=json.loads(row["keys"] or "[]"),
        secondary_keys=json.loads(row["secondary_keys"] or "[]"),
        entities=json.loads(row["entities"] or "[]"),
        relations=json.loads(row["relations"] or "[]"),
        match_mode=row["match_mode"],
        priority=row["priority"],
        constant=bool(row["constant"]),
        enabled=bool(row["enabled"]),
        sticky_turns=row["sticky_turns"],
        canon_status=row["canon_status"],
        source=row["source"],
        confidence=row["confidence"],
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


async def upsert_lorebook(book: Lorebook, db_path: Path | None = None) -> None:
    async with get_db(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO lorebooks
                (id, name, description, kind, trusted, editable, enabled,
                 default_mode, token_budget, priority, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                kind=excluded.kind,
                trusted=excluded.trusted,
                editable=excluded.editable,
                enabled=excluded.enabled,
                default_mode=excluded.default_mode,
                token_budget=excluded.token_budget,
                priority=excluded.priority,
                metadata=excluded.metadata,
                updated_at=excluded.updated_at
            """,
            (
                book.id, book.name, book.description, book.kind, int(book.trusted),
                int(book.editable), int(book.enabled), book.default_mode,
                book.token_budget, book.priority, _json(book.metadata),
                _iso(book.created_at), _iso(),
            ),
        )
        await conn.commit()


async def get_lorebook(book_id: str, db_path: Path | None = None) -> Lorebook | None:
    async with get_db(db_path) as conn:
        cursor = await conn.execute("SELECT * FROM lorebooks WHERE id = ?", (book_id,))
        row = await cursor.fetchone()
    return _row_to_book(row) if row else None


async def list_lorebooks(
    *, enabled_only: bool = False, db_path: Path | None = None
) -> list[Lorebook]:
    sql = "SELECT * FROM lorebooks"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY priority DESC, name COLLATE NOCASE"
    async with get_db(db_path) as conn:
        cursor = await conn.execute(sql)
        rows = await cursor.fetchall()
    return [_row_to_book(row) for row in rows]


async def upsert_entry(entry: LoreEntry, db_path: Path | None = None) -> None:
    async with get_db(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO lore_entries
                (uid, lorebook_id, entry_id, title, content, entry_type, keys,
                 secondary_keys, entities, relations, match_mode, priority,
                 constant, enabled, sticky_turns, canon_status, source,
                 confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lorebook_id, entry_id) DO UPDATE SET
                title=excluded.title,
                content=excluded.content,
                entry_type=excluded.entry_type,
                keys=excluded.keys,
                secondary_keys=excluded.secondary_keys,
                entities=excluded.entities,
                relations=excluded.relations,
                match_mode=excluded.match_mode,
                priority=excluded.priority,
                constant=excluded.constant,
                enabled=excluded.enabled,
                sticky_turns=excluded.sticky_turns,
                canon_status=excluded.canon_status,
                source=excluded.source,
                confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (
                entry.uid, entry.lorebook_id, entry.id, entry.title, entry.content,
                entry.entry_type, _json(entry.keys), _json(entry.secondary_keys),
                _json(entry.entities), _json(entry.relations), entry.match_mode,
                entry.priority, int(entry.constant), int(entry.enabled),
                entry.sticky_turns, entry.canon_status, entry.source,
                entry.confidence, _iso(entry.created_at), _iso(),
            ),
        )
        await conn.commit()


async def get_entry(
    lorebook_id: str, entry_id: str, db_path: Path | None = None
) -> LoreEntry | None:
    async with get_db(db_path) as conn:
        cursor = await conn.execute(
            "SELECT * FROM lore_entries WHERE lorebook_id = ? AND entry_id = ?",
            (lorebook_id, entry_id),
        )
        row = await cursor.fetchone()
    return _row_to_entry(row) if row else None


async def list_entries(
    lorebook_ids: list[str],
    *,
    enabled_only: bool = True,
    db_path: Path | None = None,
) -> list[LoreEntry]:
    if not lorebook_ids:
        return []
    placeholders = ",".join("?" for _ in lorebook_ids)
    sql = f"SELECT * FROM lore_entries WHERE lorebook_id IN ({placeholders})"
    params: list = list(lorebook_ids)
    if enabled_only:
        sql += " AND enabled = 1"
    sql += " ORDER BY priority DESC, title COLLATE NOCASE"
    async with get_db(db_path) as conn:
        cursor = await conn.execute(sql, params)
        rows = await cursor.fetchall()
    return [_row_to_entry(row) for row in rows]


async def set_world_stack(stack: WorldStack, db_path: Path | None = None) -> None:
    async with get_db(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO conversation_world_stacks
                (conversation_id, reality_mode, lorebook_ids, pinned_entries,
                 token_budget, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                reality_mode=excluded.reality_mode,
                lorebook_ids=excluded.lorebook_ids,
                pinned_entries=excluded.pinned_entries,
                token_budget=excluded.token_budget,
                updated_at=excluded.updated_at
            """,
            (
                stack.conversation_id, stack.reality_mode, _json(stack.lorebook_ids),
                _json(stack.pinned_entries), stack.token_budget, _iso(),
            ),
        )
        await conn.commit()


async def get_world_stack(
    conversation_id: str, db_path: Path | None = None
) -> WorldStack:
    async with get_db(db_path) as conn:
        cursor = await conn.execute(
            "SELECT * FROM conversation_world_stacks WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return WorldStack(conversation_id=conversation_id)
    return WorldStack(
        conversation_id=row["conversation_id"],
        reality_mode=row["reality_mode"],
        lorebook_ids=json.loads(row["lorebook_ids"] or "[]"),
        pinned_entries=json.loads(row["pinned_entries"] or "[]"),
        token_budget=row["token_budget"],
        updated_at=_dt(row["updated_at"]),
    )


async def consume_sticky_entries(
    conversation_id: str, db_path: Path | None = None
) -> set[str]:
    """Return current sticky UIDs and decrement their future-turn counters."""
    async with get_db(db_path) as conn:
        cursor = await conn.execute(
            """
            SELECT lorebook_id, entry_id, remaining_turns
            FROM lore_sticky_activations
            WHERE conversation_id = ? AND remaining_turns > 0
            """,
            (conversation_id,),
        )
        rows = await cursor.fetchall()
        await conn.execute(
            """
            UPDATE lore_sticky_activations
            SET remaining_turns = remaining_turns - 1
            WHERE conversation_id = ? AND remaining_turns > 0
            """,
            (conversation_id,),
        )
        await conn.execute(
            "DELETE FROM lore_sticky_activations WHERE conversation_id = ? AND remaining_turns <= 0",
            (conversation_id,),
        )
        await conn.commit()
    return {f"{row['lorebook_id']}:{row['entry_id']}" for row in rows}


async def set_sticky(
    conversation_id: str,
    entry: LoreEntry,
    db_path: Path | None = None,
) -> None:
    if entry.sticky_turns <= 0:
        return
    async with get_db(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO lore_sticky_activations
                (conversation_id, lorebook_id, entry_id, remaining_turns)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(conversation_id, lorebook_id, entry_id) DO UPDATE SET
                remaining_turns = MAX(remaining_turns, excluded.remaining_turns)
            """,
            (conversation_id, entry.lorebook_id, entry.id, entry.sticky_turns),
        )
        await conn.commit()


async def log_activation(
    *,
    conversation_id: str,
    turn_id: str | None,
    entry: LoreEntry,
    reason: str,
    score: float,
    included: bool,
    db_path: Path | None = None,
) -> None:
    async with get_db(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO lore_activation_log
                (conversation_id, turn_id, lorebook_id, entry_id, reason, score, included)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id, turn_id, entry.lorebook_id, entry.id,
                reason, float(score), int(included),
            ),
        )
        await conn.commit()
