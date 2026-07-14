"""SQLite database initialisation for MonikAI v2.

Creates data/monika.db with the full v2 schema if it doesn't exist.
Safe to call on every startup — all statements use CREATE TABLE IF NOT EXISTS.

Usage:
    from backend.soul.db import init_db, get_db
    await init_db()
    async with get_db() as conn: ...
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "monika.db"

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- All memory tiers in one table; type column distinguishes them.
-- FTS index created separately.
CREATE TABLE IF NOT EXISTS memory_entries (
    id             TEXT    PRIMARY KEY,
    type           TEXT    NOT NULL CHECK (type IN ('stm', 'episodic', 'semantic', 'world')),
    content        TEXT    NOT NULL,
    importance     REAL    NOT NULL CHECK (importance BETWEEN 1 AND 10),
    embedding      BLOB,
    last_accessed  TEXT,
    tags           TEXT    DEFAULT '[]',   -- JSON array
    entities       TEXT    DEFAULT '[]',   -- JSON array
    perspective    TEXT    NOT NULL DEFAULT 'factual',
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source_session TEXT
);

-- Full-text search over memory content.
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
    USING fts5(content, content='memory_entries', content_rowid='rowid');

CREATE TRIGGER IF NOT EXISTS memory_fts_insert
    AFTER INSERT ON memory_entries BEGIN
        INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
    END;

CREATE TRIGGER IF NOT EXISTS memory_fts_delete
    AFTER DELETE ON memory_entries BEGIN
        INSERT INTO memory_fts(memory_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
    END;

CREATE TRIGGER IF NOT EXISTS memory_fts_update
    AFTER UPDATE ON memory_entries BEGIN
        INSERT INTO memory_fts(memory_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
        INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
    END;

-- Knowledge graph entities.
CREATE TABLE IF NOT EXISTS kg_entities (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    type       TEXT NOT NULL,   -- Person, Project, Location, Preference, Skill, Event
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Knowledge graph relationships between entities.
CREATE TABLE IF NOT EXISTS kg_relationships (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    target_id   TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    confidence  REAL DEFAULT 1.0,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Progression: discoveries, milestones, goals, rituals, anniversaries.
-- Keyed JSON store — simple and flexible for catalogs of varying shape.
CREATE TABLE IF NOT EXISTS progression_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,   -- JSON
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Cross-process event bus (main process ↔ background worker).
-- Worker polls for unconsumed events; marks consumed_by after processing.
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    payload     TEXT NOT NULL,  -- JSON
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    consumed_by TEXT            -- NULL = pending; set to worker ID when done
);

CREATE INDEX IF NOT EXISTS idx_events_consumed ON events (consumed_by, created_at);

-- Background worker job queue.
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,  -- CompactionJob, ReflectionJob, NarrativeJob, ImportanceJob, DreamJob
    payload     TEXT NOT NULL,  -- JSON
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'done', 'failed')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at  TEXT,
    finished_at TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status, created_at);

-- Monika's cross-session agenda — open threads she wants to return to (v3).
CREATE TABLE IF NOT EXISTS agenda_items (
    id             TEXT PRIMARY KEY,
    text           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open', 'done', 'expired')),
    source_session TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    resolved_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_agenda_status ON agenda_items (status, created_at);

-- Spaced repetition flashcards (Phase 6).
CREATE TABLE IF NOT EXISTS flashcards (
    id           TEXT    PRIMARY KEY,
    front        TEXT    NOT NULL,
    back         TEXT    NOT NULL,
    tags         TEXT    DEFAULT '[]',   -- JSON array
    repetitions  INTEGER NOT NULL DEFAULT 0,
    interval     INTEGER NOT NULL DEFAULT 0,
    ease_factor  REAL    NOT NULL DEFAULT 2.5,
    next_review  TEXT    NOT NULL,       -- ISO datetime
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_flashcards_review ON flashcards (next_review);
"""


async def init_db(path: Path | None = None) -> None:
    """Create the database and apply the schema.

    Idempotent — safe to call on every startup.
    """
    db_path = path or _DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(_SCHEMA)
        await conn.commit()
    logger.info("Database ready at %s", db_path)


@asynccontextmanager
async def get_db(path: Path | None = None) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager providing a database connection."""
    db_path = path or _DB_PATH
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
