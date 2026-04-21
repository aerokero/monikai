from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path


def notes_path(data_dir: Path) -> Path:
    try:
        base = data_dir / "memory" / "pages"
        base.mkdir(parents=True, exist_ok=True)
        return base / "notes.md"
    except Exception:
        return data_dir / "memory" / "pages" / "notes.md"


def read_notes_text(data_dir: Path) -> str:
    path = notes_path(data_dir)
    try:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"[ERROR] Failed to read notes: {e}"


def write_notes_text(data_dir: Path, content: str) -> Path:
    path = notes_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")
    return path


def append_notes_text(data_dir: Path, content: str) -> Path:
    path = notes_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="ignore")
    addition = content or ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_text = existing + addition + ("\n" if addition and not addition.endswith("\n") else "")
    path.write_text(new_text, encoding="utf-8")
    return path


def journal_today_path(data_dir: Path):
    date_key = datetime.now().strftime("%Y-%m-%d")
    base = data_dir / "memory" / "pages" / "journal"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{date_key}.md", date_key


def read_journal_today(data_dir: Path):
    path, date_key = journal_today_path(data_dir)
    try:
        if not path.exists():
            return "", date_key
        return path.read_text(encoding="utf-8", errors="ignore"), date_key
    except Exception:
        return "", date_key


def resolve_memory_page(data_dir: Path, path: str) -> Path:
    base = data_dir / "memory" / "pages"
    base.mkdir(parents=True, exist_ok=True)
    if not path:
        path = "notes.md"
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = (base / path).resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError("Path outside memory pages.")
    return resolved


def list_memory_pages(data_dir: Path) -> list[dict]:
    base = data_dir / "memory" / "pages"
    base.mkdir(parents=True, exist_ok=True)
    pages = []

    def _extract_title(path: Path) -> str:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for _ in range(40):
                    line = f.readline()
                    if not line:
                        break
                    text = line.strip()
                    if not text:
                        continue
                    if text.startswith("#"):
                        cleaned = text.lstrip("#").strip()
                        if cleaned:
                            return cleaned[:120]
                    return text[:120]
        except Exception:
            pass
        return path.stem

    for p in base.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(base).as_posix()
        except Exception:
            rel = str(p).replace("\\", "/")
        category = rel.split("/")[0] if "/" in rel else "root"
        pages.append(
            {
                "path": rel,
                "title": _extract_title(p),
                "category": category,
            }
        )
    pages.sort(key=lambda x: (x.get("title", "").lower(), x.get("path", "")))
    return pages


def audio_loop_mark_user_activity(loop, text: str):
    if loop is None:
        return
    for fn_name in ("mark_user_activity", "note_user_activity", "note_user_activity_ts"):
        fn = getattr(loop, fn_name, None)
        if callable(fn):
            try:
                fn(text)
                return
            except Exception:
                return
    try:
        if hasattr(loop, "_last_user_activity_ts"):
            setattr(loop, "_last_user_activity_ts", asyncio.get_event_loop().time())
    except Exception:
        pass
