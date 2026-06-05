"""Loads character bibles from data/characters/<id>/character.md.

Renders the injectable sections into a system prompt block.

Format: markdown file with YAML-like frontmatter listing inject_sections,
followed by sections marked as ## [SECTION_NAME].

Usage:
    from backend.soul.identity.character_loader import load_character_prompt
    prompt = load_character_prompt("monika")  # returns str | None
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CHARACTERS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "characters"

_SECTION_RE = re.compile(
    r"^##\s+\[([A-Z_]+)\]\s*\n(.*?)(?=^##|\Z)",
    re.MULTILINE | re.DOTALL,
)


def load_character_prompt(character_id: str = "monika") -> str | None:
    """Return the rendered system prompt block for the given character.

    Returns None if the file doesn't exist or fails to parse, so callers
    can fall back gracefully.
    """
    path = _CHARACTERS_DIR / character_id / "character.md"
    if not path.exists():
        logger.warning("Character file not found: %s", path)
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        result = _render(raw)
        if result:
            logger.info("Loaded character '%s' (%d chars)", character_id, len(result))
        return result or None
    except Exception as exc:
        logger.error("Failed to load character '%s': %s", character_id, exc)
        return None


def list_characters() -> list[str]:
    """Return IDs of all available character bibles."""
    if not _CHARACTERS_DIR.exists():
        return []
    return [p.parent.name for p in _CHARACTERS_DIR.glob("*/character.md")]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(raw: str) -> tuple[dict, str]:
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
    fm, body = _parse_frontmatter(raw)
    inject: list[str] = fm.get("inject_sections") or []
    sections = {
        m.group(1): _clean(m.group(2))
        for m in _SECTION_RE.finditer(body)
    }
    parts = [sections[key] for key in inject if key in sections]
    return "\n\n".join(parts)


def _clean(content: str) -> str:
    lines = content.splitlines()
    while lines and lines[-1].strip() in ("---", "***", "___", ""):
        lines.pop()
    return "\n".join(lines).strip()
