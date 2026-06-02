"""
Loads character bibles from data/characters/<id>/character.md and renders
the injectable sections into a system prompt block.

Format: markdown file with simple YAML-like frontmatter that lists
inject_sections, followed by sections marked as ## [SECTION_NAME].

Usage:
    from backend.ai.character_loader import load_character_prompt
    prompt = load_character_prompt("monika")  # returns str or None
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_CHARACTERS_DIR = Path(__file__).parent.parent.parent / "data" / "characters"

_SECTION_RE = re.compile(
    r"^##\s+\[([A-Z_]+)\]\s*\n(.*?)(?=^##|\Z)",
    re.MULTILINE | re.DOTALL,
)


def load_character_prompt(character_id: str = "monika") -> Optional[str]:
    """Return the rendered system prompt block for the given character.

    Returns None if the file doesn't exist or fails to parse, so the caller
    can fall back gracefully.
    """
    path = _CHARACTERS_DIR / character_id / "character.md"
    if not path.exists():
        print(f"[Character] File not found: {path}")
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        result = _render(raw)
        if result:
            print(f"[Character] Loaded '{character_id}' ({len(result)} chars)")
        return result or None
    except Exception as exc:
        print(f"[Character] Failed to load '{character_id}': {exc}")
        return None


def list_characters() -> list[str]:
    """Return IDs of all available character bibles."""
    if not _CHARACTERS_DIR.exists():
        return []
    return [
        p.parent.name
        for p in _CHARACTERS_DIR.glob("*/character.md")
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Extract simple key: value frontmatter between --- delimiters."""
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    fm_text = raw[3:end].strip()
    body = raw[end + 4:].strip()
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            fm[key] = [x.strip() for x in val[1:-1].split(",") if x.strip()]
        else:
            fm[key] = val
    return fm, body


def _render(raw: str) -> str:
    """Parse the file and join injectable sections in the declared order."""
    fm, body = _parse_frontmatter(raw)
    inject: list[str] = fm.get("inject_sections") or []
    sections = {
        m.group(1): _clean(m.group(2))
        for m in _SECTION_RE.finditer(body)
    }
    parts = [sections[key] for key in inject if key in sections]
    return "\n\n".join(parts)


def _clean(content: str) -> str:
    """Strip trailing horizontal rules and blank lines from a section."""
    lines = content.splitlines()
    while lines and lines[-1].strip() in ("---", "***", "___", ""):
        lines.pop()
    return "\n".join(lines).strip()
