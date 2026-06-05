"""Story loader — parses YAML story schemas into typed models.

Stories live in data/characters/monika/vn/stories/*.yaml.
Each story has an opening context, branches (conditional frames), and endings.

The branches and endings carry context blocks (natural-language instructions
for the LLM) rather than scripted dialogue. The LLM generates actual dialogue
within the frame.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_STORIES_DIR = Path(__file__).parent.parent.parent / "data" / "characters" / "monika" / "vn" / "stories"


@dataclass
class StoryBranch:
    id: str
    when: str       # human-readable condition description (for developer)
    context: str    # LLM instruction frame for this branch


@dataclass
class StoryEnding:
    id: str
    when: str
    context: str


@dataclass
class StoryScene:
    bg: str = "room_day"
    outfit: str = "casual"
    expr: str = "neutral"
    light: str = "natural"
    ambience: str = ""


@dataclass
class Story:
    id: str
    title: str
    unlock: str               # "always" | condition string
    opening: str              # opening context block
    branches: list[StoryBranch] = field(default_factory=list)
    endings: list[StoryEnding] = field(default_factory=list)
    scene: StoryScene = field(default_factory=StoryScene)
    discovery: Optional[str] = None
    preferred_time: list[str] = field(default_factory=list)
    preferred_weather: str = ""


def load_story(
    story_id: str,
    stories_dir: Path | None = None,
) -> Story | None:
    """Load a story by ID. Returns None if not found or malformed."""
    d = stories_dir or _STORIES_DIR
    path = d / f"{story_id}.yaml"
    if not path.exists():
        logger.warning("Story not found: %s", path)
        return None
    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return _parse(raw)
    except Exception as exc:
        logger.error("Failed to load story %s: %s", story_id, exc)
        return None


def list_stories(stories_dir: Path | None = None) -> list[str]:
    """Return IDs of all available stories."""
    d = stories_dir or _STORIES_DIR
    if not d.exists():
        return []
    return [p.stem for p in sorted(d.glob("*.yaml"))]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse(raw: dict) -> Story:
    scene_raw = raw.get("scene", {})
    scene = StoryScene(
        bg=scene_raw.get("bg", "room_day"),
        outfit=scene_raw.get("outfit", "casual"),
        expr=scene_raw.get("expr", "neutral"),
        light=scene_raw.get("light", "natural"),
        ambience=scene_raw.get("ambience", ""),
    )

    opening_raw = raw.get("opening", {})
    if isinstance(opening_raw, dict):
        opening = str(opening_raw.get("context", ""))
    else:
        opening = str(opening_raw)

    branches = []
    for b in raw.get("branches", []):
        branches.append(StoryBranch(
            id=b["id"],
            when=b.get("when", ""),
            context=str(b.get("context", "")),
        ))

    endings = []
    for e in raw.get("endings", []):
        endings.append(StoryEnding(
            id=e["id"],
            when=e.get("when", ""),
            context=str(e.get("context", "")),
        ))

    pt = raw.get("preferred_time", [])
    if isinstance(pt, str):
        pt = [pt]

    return Story(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        unlock=str(raw.get("unlock", "always")),
        opening=opening,
        branches=branches,
        endings=endings,
        scene=scene,
        discovery=raw.get("discovery"),
        preferred_time=pt,
        preferred_weather=str(raw.get("preferred_weather", "")),
    )
