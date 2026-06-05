"""VN Mapping Engine — SoulState + time + weather → visual scene output.

Reads mapping.yaml, evaluates rules in order (first match wins), merges
partial rule outputs into the defaults. Returns a SceneState that the
frontend uses to update Monika's appearance, background, and lighting.

Usage:
    engine = MappingEngine()
    scene = engine.compute(soul_state, hour=20, weather="rainy")
    # → SceneState(bg="room_window_rain", expr="soft", light="warm_dim", ...)
"""

from __future__ import annotations

import logging
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from backend.soul.models import SoulState

logger = logging.getLogger(__name__)

_MAPPING_PATH = Path(__file__).parent.parent.parent / "data" / "characters" / "monika" / "vn" / "mapping.yaml"

_TIME_BUCKETS = {
    "morning":   range(6, 12),
    "afternoon": range(12, 17),
    "evening":   range(17, 22),
    "night":     [*range(22, 24), *range(0, 6)],
}

_CMP_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">":  operator.gt,
    "<":  operator.lt,
    "=":  operator.eq,
}


@dataclass
class SceneState:
    """Visual state for the VN frontend."""
    bg: str = "room_day"
    outfit: str = "casual"
    expr: str = "neutral"
    light: str = "natural"
    ambience: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class MappingEngine:
    """Evaluates mapping rules and returns a SceneState."""

    def __init__(self, mapping_path: Path | None = None) -> None:
        p = mapping_path or _MAPPING_PATH
        self._defaults: dict = {}
        self._rules: list[dict] = []
        self._load(p)

    def _load(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Mapping file not found: %s — using built-in defaults", path)
            return
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._defaults = data.get("defaults", {})
        self._rules = data.get("rules", [])
        logger.debug("Loaded %d mapping rules", len(self._rules))

    def compute(
        self,
        soul_state: SoulState,
        hour: int = 12,
        weather: str = "",
    ) -> SceneState:
        """Return the scene state for the given context.

        Rules are evaluated in order; each matching rule's scene dict is
        merged (later matches override earlier ones for the same key).
        This allows additive composition rather than first-match-wins.
        """
        result = dict(self._defaults)

        for rule in self._rules:
            cond = rule.get("when", {})
            if self._matches(cond, soul_state, hour, weather):
                result.update(rule.get("scene", {}))

        return SceneState(
            bg=result.get("bg", "room_day"),
            outfit=result.get("outfit", "casual"),
            expr=result.get("expr", "neutral"),
            light=result.get("light", "natural"),
            ambience=result.get("ambience", ""),
        )

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------

    def _matches(
        self,
        condition: dict,
        soul_state: SoulState,
        hour: int,
        weather: str,
    ) -> bool:
        for key, value in condition.items():
            if not self._eval_key(key, value, soul_state, hour, weather):
                return False
        return True

    def _eval_key(self, key: str, value, soul_state: SoulState, hour: int, weather: str) -> bool:
        if key == "register":
            return soul_state.active_register == value

        if key == "time":
            return _time_bucket(hour) == value

        if key == "weather":
            return str(value).lower() in weather.lower()

        if key == "cycle_phase":
            return soul_state.cycle_phase == value

        if key == "energy":
            return _numeric_compare(soul_state.energy, str(value))

        if key.startswith("affect_"):
            dim = key[7:]  # "pleasure", "arousal", "dominance"
            actual = getattr(soul_state.affect, dim, None)
            if actual is None:
                return False
            return _numeric_compare(actual, str(value))

        logger.debug("Unknown mapping condition key: %r — ignoring", key)
        return True  # unknown keys are ignored (forward-compatible)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_bucket(hour: int) -> str:
    for name, hours in _TIME_BUCKETS.items():
        if hour in hours:
            return name
    return "morning"


def _numeric_compare(actual: float, value_str: str) -> bool:
    """Evaluate ">0.4", "<=0.5", "<-0.2", "=0.3" against actual float."""
    value_str = value_str.strip()
    for op_str, op_fn in sorted(_CMP_OPS.items(), key=lambda t: -len(t[0])):
        if value_str.startswith(op_str):
            try:
                return op_fn(actual, float(value_str[len(op_str):]))
            except ValueError:
                return False
    try:
        return actual == float(value_str)
    except ValueError:
        return False
