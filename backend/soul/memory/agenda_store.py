"""Persistent agenda — open threads Monika wants to return to (v3).

Items come from session digests (LLM-extracted, natural Polish phrases).
They survive across sessions: the Context Assembler injects open items at
reconnect, and they are resolved or expired over time.

Lifecycle: open → done (she followed up) / expired (too old to matter).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.soul.db import get_db

logger = logging.getLogger(__name__)

# An open thread older than this no longer feels natural to bring up.
_DEFAULT_TTL_DAYS = 10

# Cap injected items so the prompt stays focused.
_MAX_OPEN = 5


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _item_id(text: str) -> str:
    return "ag_" + hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]


_ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agenda_items (
    id             TEXT PRIMARY KEY,
    text           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open', 'done', 'expired')),
    source_session TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    resolved_at    TEXT
)
"""


async def add_items(
    texts: list[str],
    source_session: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert new open agenda items (dedup by normalized text). Returns count added."""
    added = 0
    async with get_db(db_path) as conn:
        await conn.execute(_ENSURE_TABLE_SQL)
        for text in texts:
            text = text.strip()
            if not text:
                continue
            item_id = _item_id(text)
            cursor = await conn.execute(
                """
                INSERT OR IGNORE INTO agenda_items (id, text, source_session, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (item_id, text, source_session, _iso(_utcnow())),
            )
            added += cursor.rowcount
        await conn.commit()
    if added:
        logger.info("agenda: %d new item(s)", added)
    return added


async def open_items(
    limit: int = _MAX_OPEN,
    db_path: Path | None = None,
) -> list[dict]:
    """Return open items (newest first), expiring stale ones on the way."""
    cutoff = _iso(_utcnow() - timedelta(days=_DEFAULT_TTL_DAYS))
    async with get_db(db_path) as conn:
        await conn.execute(_ENSURE_TABLE_SQL)
        await conn.execute(
            "UPDATE agenda_items SET status = 'expired', resolved_at = ? "
            "WHERE status = 'open' AND created_at < ?",
            (_iso(_utcnow()), cutoff),
        )
        await conn.commit()

        cursor = await conn.execute(
            "SELECT id, text, source_session, created_at FROM agenda_items "
            "WHERE status = 'open' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def resolve(
    item_id: str,
    status: str = "done",
    db_path: Path | None = None,
) -> None:
    if status not in ("done", "expired"):
        raise ValueError(f"invalid agenda status: {status}")
    async with get_db(db_path) as conn:
        await conn.execute(
            "UPDATE agenda_items SET status = ?, resolved_at = ? WHERE id = ?",
            (status, _iso(_utcnow()), item_id),
        )
        await conn.commit()
