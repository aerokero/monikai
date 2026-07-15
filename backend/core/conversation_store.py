"""Read-side helpers over the sessions directory (v3 Phase G).

Conversations and streams live on disk as ``sessions/<day>/<id>/``
(turns.jsonl + meta.json, written by SessionManager, enriched by the digest).
This module gives the socket API and the ``recall_conversation`` tool one
shared, read-only view of them. No state — every call scans the directory.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from backend.core.session_manager import STREAM_DIR_PREFIX

# Cap how many day directories a search walks through before giving up —
# recall should stay instant even after years of history.
_SEARCH_MAX_DAYS = 400
_EXCERPT_MAX_LINES = 12
_EXCERPT_LINE_CHARS = 200


def _read_meta(sess_dir: Path) -> dict:
    try:
        data = json.loads((sess_dir / "meta.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_turns(sess_dir: Path) -> List[Dict]:
    turns_path = sess_dir / "turns.jsonl"
    if not turns_path.exists():
        return []
    turns: List[Dict] = []
    try:
        for line in turns_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if isinstance(entry, dict):
                    turns.append(entry)
            except Exception:
                continue
    except Exception:
        pass
    return turns


def _iter_session_dirs_desc(sessions_root: Path) -> Iterator[Path]:
    if not sessions_root.exists():
        return
    for day_dir in sorted(sessions_root.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        for sess_dir in sorted(day_dir.iterdir(), reverse=True):
            if sess_dir.is_dir():
                yield sess_dir


def _summary_of(sess_dir: Path, meta: dict, *, with_counts: bool = True) -> Dict:
    digest = meta.get("digest") or {}
    kind = meta.get("kind") or (
        "stream" if sess_dir.name.startswith(STREAM_DIR_PREFIX) else "conversation"
    )
    item = {
        "id": sess_dir.name,
        "day": sess_dir.parent.name,
        "kind": kind,
        "channel": meta.get("channel") or "app",
        "title": meta.get("title") or "",
        "started_at": meta.get("started_at") or "",
        "digest_status": digest.get("status") or "",
        "recap": digest.get("recap") or "",
        "continues": meta.get("continues") or "",
    }
    if with_counts:
        turns_path = sess_dir / "turns.jsonl"
        count = 0
        if turns_path.exists():
            try:
                count = sum(
                    1 for ln in turns_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if ln.strip()
                )
            except Exception:
                count = 0
        item["turn_count"] = count
    return item


def list_conversations(
    sessions_root: Path,
    *,
    limit: int = 60,
    offset: int = 0,
    include_empty: bool = False,
) -> List[Dict]:
    """Newest-first summaries of conversations AND streams (mixed list)."""
    results: List[Dict] = []
    skipped = 0
    for sess_dir in _iter_session_dirs_desc(sessions_root):
        meta = _read_meta(sess_dir)
        item = _summary_of(sess_dir, meta)
        if not include_empty and item["turn_count"] == 0:
            continue
        if skipped < offset:
            skipped += 1
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def get_conversation(
    sessions_root: Path,
    session_id: str,
    *,
    max_turns: int = 500,
) -> Optional[Dict]:
    """Full detail of one session: summary + up to ``max_turns`` last turns."""
    for sess_dir in _iter_session_dirs_desc(sessions_root):
        if sess_dir.name == session_id:
            meta = _read_meta(sess_dir)
            item = _summary_of(sess_dir, meta)
            item["turns"] = _read_turns(sess_dir)[-max_turns:]
            return item
    return None


def search_conversations(
    sessions_root: Path,
    query: str,
    *,
    limit: int = 3,
) -> List[Dict]:
    """Find past sessions by title, date or transcript content.

    Plain case-insensitive matching, newest first. A query that looks like a
    date prefix ("2026-07-14") matches the session's day. Each hit carries a
    transcript excerpt around the matching lines.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    terms = [t for t in q.split() if t]

    hits: List[Dict] = []
    days_seen = 0
    last_day = None
    for sess_dir in _iter_session_dirs_desc(sessions_root):
        day = sess_dir.parent.name
        if day != last_day:
            last_day = day
            days_seen += 1
            if days_seen > _SEARCH_MAX_DAYS:
                break

        meta = _read_meta(sess_dir)
        title = str(meta.get("title") or "").lower()
        date_match = q.startswith(day) or day.startswith(q)
        title_match = title and all(t in title for t in terms)

        matching_lines: List[str] = []
        if not (date_match or title_match):
            turns = _read_turns(sess_dir)
            for turn in turns:
                text = str(turn.get("text") or "")
                if any(t in text.lower() for t in terms):
                    sender = str(turn.get("sender") or "?")
                    matching_lines.append(f"{sender}: {text[:_EXCERPT_LINE_CHARS]}")
                    if len(matching_lines) >= _EXCERPT_MAX_LINES:
                        break
            if not matching_lines:
                continue

        item = _summary_of(sess_dir, meta)
        item["excerpt"] = "\n".join(matching_lines)
        hits.append(item)
        if len(hits) >= limit:
            break
    return hits


def delete_conversation(sessions_root: Path, session_id: str) -> bool:
    """Permanently remove a session directory (transcript + meta).

    Memories distilled from it (facts/episodes in monika.db) are untouched —
    deleting the transcript does not make Monika forget.
    Returns True if the directory was found and removed.
    """
    if not session_id:
        return False
    sessions_root = Path(sessions_root).resolve()
    for sess_dir in _iter_session_dirs_desc(sessions_root):
        if sess_dir.name != session_id:
            continue
        resolved = sess_dir.resolve()
        # Only ever delete a direct child of a day directory under the root.
        if resolved.parent.parent != sessions_root:
            return False
        shutil.rmtree(resolved, ignore_errors=True)
        return not resolved.exists()
    return False


def build_continuation_context(
    sessions_root: Path,
    session_id: str,
    *,
    last_turns: int = 10,
) -> str:
    """Context block injected when the user continues an old conversation.

    Digest recap/title + the final turns — enough for Monika to pick the
    thread back up without re-reading the whole transcript.
    """
    detail = get_conversation(sessions_root, session_id, max_turns=last_turns)
    if detail is None:
        return ""

    lines: List[str] = []
    header = detail["title"] or session_id
    lines.append(f"[Kontynuacja wcześniejszej rozmowy: \"{header}\" z dnia {detail['day']}]")
    if detail["recap"]:
        lines.append(f"Podsumowanie: {detail['recap']}")
    if detail["turns"]:
        lines.append("Ostatnie wypowiedzi tamtej rozmowy:")
        for turn in detail["turns"]:
            text = str(turn.get("text") or "").strip()
            if not text:
                continue
            sender = str(turn.get("sender") or "?")
            lines.append(f"{sender}: {text[:_EXCERPT_LINE_CHARS]}")
    return "\n".join(lines)
