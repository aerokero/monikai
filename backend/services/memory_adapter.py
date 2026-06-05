"""v2 Compatibility MemoryEngine Adapter.

Exposes the legacy MemoryEngine interface but reads and writes directly
to the v2 SQLite database and the local pages directory.
"""
from __future__ import annotations

import json
import re
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from backend.services.user_profile import UserProfileManager


class MemoryEngine:
    """Compatibility adapter representing the legacy MemoryEngine for v2."""

    def __init__(
        self,
        base_dir: Path,
        session_manager=None,
        emit_event=None,
        language: str = "pl",
    ):
        self.base_dir = Path(base_dir).resolve()
        self.session_manager = session_manager
        self.emit_event = emit_event
        self.language = language

        self.db_path = self.base_dir / "monika.db"
        self.pages_dir = self.base_dir / "memory" / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def get_birthday(self) -> Optional[Tuple[int, int]]:
        """Get birthday from profile.json (month, day)"""
        try:
            manager = UserProfileManager()
            profile = manager.get_profile()
            if profile and profile.birthday:
                parts = profile.birthday.split("-")
                if len(parts) == 3:
                    return int(parts[1]), int(parts[2])
        except Exception:
            pass
        return None

    def get_user_name(self) -> str:
        try:
            manager = UserProfileManager()
            profile = manager.get_profile()
            if profile:
                return profile.name or ""
        except Exception:
            pass
        return ""

    def auto_extract_from_user_text(self, text: str) -> None:
        # v2 turn processing handles memory extraction
        pass

    def add_entry(
        self,
        type: str,
        content: str,
        tags: list | None = None,
        entities: list | None = None,
        confidence: float = 0.6,
        importance_score: float = 0.5,
        **kwargs,
    ) -> Tuple[str, str]:
        if not type:
            type = "stm"
        v2_type = type
        if v2_type not in ('stm', 'episodic', 'semantic', 'world'):
            v2_type = "stm"

        tags = tags or []
        entities = entities or []

        # Calculate id based on type and content hash
        h = hashlib.sha256(f"{v2_type}|{content.strip().lower()}".encode("utf-8")).hexdigest()[:16]
        entry_id = f"mem_{h}"

        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

        conn = self._connect()
        try:
            existing = conn.execute("SELECT id FROM memory_entries WHERE id = ?", (entry_id,)).fetchone()
            if existing:
                return entry_id, "dedup"

            conn.execute(
                """
                INSERT INTO memory_entries (
                    id, type, content, importance, embedding, last_accessed, tags, entities, perspective, created_at, source_session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    v2_type,
                    content,
                    max(1.0, min(10.0, importance_score * 10.0)),
                    None,
                    now,
                    json.dumps(tags),
                    json.dumps(entities),
                    "factual",
                    now,
                    None
                )
            )
            conn.commit()
            return entry_id, "ok"
        except Exception as e:
            print(f"[MemoryAdapter] Error adding entry: {e}")
            return "", "error"
        finally:
            conn.close()

    def search(self, query: str, types: list | None = None, tags: list | None = None, limit: int = 5) -> list[dict]:
        tokens = re.findall(r"[\w\-]+", query or "", re.UNICODE)
        if not tokens:
            return []
        fts_query = " OR ".join(tokens)

        sql = (
            "SELECT e.* "
            "FROM memory_fts "
            "JOIN memory_entries e ON e.rowid = memory_fts.rowid "
            "WHERE memory_fts MATCH ?"
        )
        params = [fts_query]

        if types:
            sql += " AND e.type IN ({})".format(",".join("?" * len(types)))
            params.extend(types)

        sql += " LIMIT ?"
        params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "type": r["type"],
                    "content": r["content"],
                    "tags": json.loads(r["tags"] or "[]"),
                    "entities": json.loads(r["entities"] or "[]"),
                    "importance_score": r["importance"] / 10.0,
                    "created_at": r["created_at"]
                })
            return results
        except Exception as e:
            print(f"[MemoryAdapter] Error searching: {e}")
            return []
        finally:
            conn.close()

    def list_recent(self, limit: int = 20, types: list | None = None) -> list[dict]:
        sql = "SELECT * FROM memory_entries"
        params = []
        if types:
            sql += " WHERE type IN ({})".format(",".join("?" * len(types)))
            params.extend(types)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "type": r["type"],
                    "content": r["content"],
                    "tags": json.loads(r["tags"] or "[]"),
                    "entities": json.loads(r["entities"] or "[]"),
                    "importance_score": r["importance"] / 10.0,
                    "created_at": r["created_at"]
                })
            return results
        except Exception as e:
            print(f"[MemoryAdapter] Error listing recent: {e}")
            return []
        finally:
            conn.close()

    # Markdown pages
    def create_page(self, title: str, folder: str = "topics", tags: list | None = None) -> str:
        folder = (folder or "topics").strip().lower()
        slug = re.sub(r"[^a-z0-9\-_\s]+", "", title.strip().lower())
        slug = re.sub(r"\s+", "_", slug)[:64]

        page_dir = self.pages_dir / folder
        page_dir.mkdir(parents=True, exist_ok=True)
        path = page_dir / f"{slug}.md"

        if not path.exists():
            now = datetime.now().isoformat()
            frontmatter = [
                "---",
                f"id: page_{slug}",
                "type: topic_page",
                f"title: {title}",
                f"tags: [{', '.join(tags or [])}]",
                f"created_at: {now}",
                f"updated_at: {now}",
                "---",
                "",
                f"# {title}",
                "",
            ]
            path.write_text("\n".join(frontmatter), encoding="utf-8")
        return str(path)

    def append_page(self, path: str, content: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = (self.pages_dir / path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write("\n" + content + "\n")
        return str(p)

    def get_page(self, path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = (self.pages_dir / path).resolve()
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")

    # Journaling
    def journal_add_entry(
        self,
        content: str,
        topics: list | None = None,
        mood: str | None = None,
        session_id: str | None = None,
        tags: list | None = None,
    ) -> str:
        tags = tags or []
        if topics:
            tags.extend([f"topic:{t}" for t in topics])

        now = datetime.now()
        date_key = now.strftime("%Y-%m-%d")
        time_key = now.strftime("%H:%M")

        journal_dir = self.pages_dir / "journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        journal_path = journal_dir / f"{date_key}.md"

        block = f"## {date_key} {time_key}\n"
        if session_id:
            block += f"- session: {session_id}\n"
        if mood:
            block += f"- mood: {mood}\n"
        block += f"\n{content.strip()}\n"

        if not journal_path.exists():
            journal_path.write_text(f"# Journal ({date_key})\n\n", encoding="utf-8")
        self.append_page(str(journal_path), block)

        entry_id, _ = self.add_entry(
            type="journal",
            content=content.strip(),
            tags=tags,
            entities=["user"]
        )
        return entry_id

    def journal_finalize_session(
        self,
        summary: str,
        reflections: str | None = None,
        session_id: str | None = None,
    ) -> str:
        if self.session_manager and hasattr(self.session_manager, "flush_session"):
            try:
                self.session_manager.flush_session(session_id)
            except Exception:
                pass
        return "ok"
