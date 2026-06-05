"""Load and parse YAML progression catalogs.

Catalogs are human-editable YAML files in data/progression/catalog/.
They define the *possible* discoveries, goals, and rituals —
the progression engine manages which ones are active/unlocked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CATALOG_DIR = Path(__file__).parent.parent.parent / "data" / "progression" / "catalog"


# ---------------------------------------------------------------------------
# Pydantic-free dataclasses (catalog entries are read-only value objects)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscoveryEntry:
    id: str
    title: str
    trigger: str
    hidden: bool = True
    description: str = ""


@dataclass(frozen=True)
class GoalEntry:
    id: str
    kind: str          # "hers" | "yours" | "shared"
    title: str
    description: str = ""


@dataclass(frozen=True)
class RitualEntry:
    id: str
    kind: str
    need_trigger: str  # "relatedness" | "competence" | "autonomy"
    min_need_deficit: float = 0.5
    description: str = ""


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_yaml(filename: str) -> list[dict[str, Any]]:
    path = _CATALOG_DIR / filename
    if not path.exists():
        logger.warning("Catalog file not found: %s", path)
        return []
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def load_discoveries(catalog_dir: Path | None = None) -> list[DiscoveryEntry]:
    raw = _load_yaml("discoveries.yaml") if catalog_dir is None else _load_from_dir(catalog_dir, "discoveries.yaml")
    entries = []
    for item in raw:
        try:
            entries.append(DiscoveryEntry(
                id=item["id"],
                title=item["title"],
                trigger=item["trigger"],
                hidden=bool(item.get("hidden", True)),
                description=str(item.get("description", "")),
            ))
        except (KeyError, TypeError) as exc:
            logger.warning("Skipping malformed discovery entry: %s — %s", item, exc)
    return entries


def load_goals(catalog_dir: Path | None = None) -> list[GoalEntry]:
    raw = _load_yaml("goals.yaml") if catalog_dir is None else _load_from_dir(catalog_dir, "goals.yaml")
    entries = []
    for item in raw:
        try:
            entries.append(GoalEntry(
                id=item["id"],
                kind=item["kind"],
                title=item["title"],
                description=str(item.get("description", "")),
            ))
        except (KeyError, TypeError) as exc:
            logger.warning("Skipping malformed goal entry: %s — %s", item, exc)
    return entries


def load_rituals(catalog_dir: Path | None = None) -> list[RitualEntry]:
    raw = _load_yaml("rituals.yaml") if catalog_dir is None else _load_from_dir(catalog_dir, "rituals.yaml")
    entries = []
    for item in raw:
        try:
            entries.append(RitualEntry(
                id=item["id"],
                kind=item["kind"],
                need_trigger=item["need_trigger"],
                min_need_deficit=float(item.get("min_need_deficit", 0.5)),
                description=str(item.get("description", "")),
            ))
        except (KeyError, TypeError) as exc:
            logger.warning("Skipping malformed ritual entry: %s — %s", item, exc)
    return entries


# ---------------------------------------------------------------------------
# Trigger parsing
# ---------------------------------------------------------------------------

def parse_trigger(trigger: str) -> tuple[str, str | None]:
    """Split trigger into (event_name, condition_str | None).

    Examples:
      "TurnCompleted"              → ("TurnCompleted", None)
      "MemoryStored[importance>=9]" → ("MemoryStored", "importance>=9")
      "count:5"                    → ("count", "5")
    """
    if trigger.startswith("count:"):
        return "count", trigger[6:].strip()
    if "[" in trigger and trigger.endswith("]"):
        name, cond = trigger[:-1].split("[", 1)
        return name.strip(), cond.strip()
    return trigger.strip(), None


def check_condition(condition: str, payload: dict[str, Any]) -> bool:
    """Evaluate a simple condition string against a payload dict.

    Supports: key>=N, key<=N, key>N, key<N, key=value (string or numeric).
    """
    for op in (">=", "<=", ">", "<", "="):
        if op in condition:
            key, _, val_str = condition.partition(op)
            key = key.strip()
            val_str = val_str.strip()
            actual = payload.get(key)
            if actual is None:
                return False
            try:
                if isinstance(actual, bool):
                    expected = val_str.lower() == "true"
                    return actual == expected if op == "=" else False
                if isinstance(actual, (int, float)):
                    num_val = type(actual)(val_str)
                    if op == ">=": return actual >= num_val
                    if op == "<=": return actual <= num_val
                    if op == ">":  return actual > num_val
                    if op == "<":  return actual < num_val
                    if op == "=":  return actual == num_val
                if op == "=":
                    return str(actual) == val_str
            except (ValueError, TypeError):
                return False
    return False


def trigger_matches(trigger: str, event_name: str, payload: dict[str, Any]) -> bool:
    """Return True if this trigger fires for the given event and payload."""
    t_name, condition = parse_trigger(trigger)
    if t_name == "count":
        # count:N triggers are handled by DiscoveryEngine with a counter
        return False  # evaluated externally
    if t_name != event_name:
        return False
    if condition is None:
        return True
    return check_condition(condition, payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_from_dir(dir_: Path, filename: str) -> list[dict[str, Any]]:
    path = dir_ / filename
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []
