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
    kind        TEXT NOT NULL,  -- CompactionJob, ReflectionJob, ImportanceJob, DreamJob
    payload     TEXT NOT NULL,  -- JSON
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'done', 'failed')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at  TEXT,
    finished_at TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status, created_at);

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

-- Lorebooks are world-scoped knowledge sources. They intentionally remain
-- separate from personal and episodic memory.
CREATE TABLE IF NOT EXISTS lorebooks (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL
                      CHECK (kind IN ('reality', 'imported_fiction', 'custom', 'scenario')),
    trusted       INTEGER NOT NULL DEFAULT 0 CHECK (trusted IN (0, 1)),
    editable      INTEGER NOT NULL DEFAULT 1 CHECK (editable IN (0, 1)),
    enabled       INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    default_mode  TEXT NOT NULL DEFAULT 'grounded'
                      CHECK (default_mode IN ('grounded', 'crossover', 'roleplay', 'ambiguous')),
    token_budget  INTEGER NOT NULL DEFAULT 1800 CHECK (token_budget > 0),
    priority      INTEGER NOT NULL DEFAULT 50,
    metadata      TEXT NOT NULL DEFAULT '{}', -- JSON object
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS lore_entries (
    uid             TEXT PRIMARY KEY,
    lorebook_id     TEXT NOT NULL REFERENCES lorebooks(id) ON DELETE CASCADE,
    entry_id        TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    entry_type      TEXT NOT NULL DEFAULT 'knowledge'
                         CHECK (entry_type IN ('knowledge', 'scene', 'dialogue_example', 'behavior_instruction')),
    keys            TEXT NOT NULL DEFAULT '[]', -- JSON array
    secondary_keys  TEXT NOT NULL DEFAULT '[]', -- JSON array
    entities        TEXT NOT NULL DEFAULT '[]', -- JSON array
    relations       TEXT NOT NULL DEFAULT '[]', -- JSON array
    match_mode      TEXT NOT NULL DEFAULT 'any'
                         CHECK (match_mode IN ('any', 'all', 'primary_and_secondary')),
    priority        INTEGER NOT NULL DEFAULT 50,
    constant        INTEGER NOT NULL DEFAULT 0 CHECK (constant IN (0, 1)),
    enabled         INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    sticky_turns    INTEGER NOT NULL DEFAULT 0 CHECK (sticky_turns >= 0),
    canon_status    TEXT NOT NULL DEFAULT 'canonical'
                         CHECK (canon_status IN ('canonical', 'learned', 'proposed', 'superseded')),
    source          TEXT NOT NULL DEFAULT 'manual',
    confidence      REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (lorebook_id, entry_id)
);

CREATE INDEX IF NOT EXISTS idx_lore_entries_book
    ON lore_entries (lorebook_id, enabled, priority DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS lore_fts
    USING fts5(title, content, keys, content='lore_entries', content_rowid='rowid');

CREATE TRIGGER IF NOT EXISTS lore_fts_insert
    AFTER INSERT ON lore_entries BEGIN
        INSERT INTO lore_fts(rowid, title, content, keys)
        VALUES (new.rowid, new.title, new.content, new.keys);
    END;

CREATE TRIGGER IF NOT EXISTS lore_fts_delete
    AFTER DELETE ON lore_entries BEGIN
        INSERT INTO lore_fts(lore_fts, rowid, title, content, keys)
        VALUES ('delete', old.rowid, old.title, old.content, old.keys);
    END;

CREATE TRIGGER IF NOT EXISTS lore_fts_update
    AFTER UPDATE ON lore_entries BEGIN
        INSERT INTO lore_fts(lore_fts, rowid, title, content, keys)
        VALUES ('delete', old.rowid, old.title, old.content, old.keys);
        INSERT INTO lore_fts(rowid, title, content, keys)
        VALUES (new.rowid, new.title, new.content, new.keys);
    END;

CREATE TABLE IF NOT EXISTS conversation_world_stacks (
    conversation_id  TEXT PRIMARY KEY,
    reality_mode     TEXT NOT NULL DEFAULT 'grounded'
                         CHECK (reality_mode IN ('grounded', 'crossover', 'roleplay', 'ambiguous')),
    lorebook_ids     TEXT NOT NULL DEFAULT '[]', -- ordered JSON array
    pinned_entries   TEXT NOT NULL DEFAULT '[]', -- "lorebook_id:entry_id"
    token_budget     INTEGER,
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS lore_sticky_activations (
    conversation_id  TEXT NOT NULL,
    lorebook_id      TEXT NOT NULL,
    entry_id         TEXT NOT NULL,
    remaining_turns  INTEGER NOT NULL CHECK (remaining_turns >= 0),
    PRIMARY KEY (conversation_id, lorebook_id, entry_id),
    FOREIGN KEY (lorebook_id, entry_id)
        REFERENCES lore_entries(lorebook_id, entry_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lore_activation_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL,
    turn_id          TEXT,
    lorebook_id      TEXT NOT NULL,
    entry_id         TEXT NOT NULL,
    reason           TEXT NOT NULL,
    score            REAL NOT NULL,
    included         INTEGER NOT NULL DEFAULT 1 CHECK (included IN (0, 1)),
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_lore_activation_turn
    ON lore_activation_log (conversation_id, turn_id, created_at);
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
