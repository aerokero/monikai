"""SoulState persistence to data/soul/state.json.

Thin read/write layer — no validation logic here. The engine owns state,
this file owns the disk I/O.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.soul.models import Affect, Needs, SoulState

logger = logging.getLogger(__name__)

_STATE_PATH = Path(__file__).parent.parent.parent.parent / "data" / "soul" / "state.json"


class StateStore:
    """Synchronous JSON read/write for SoulState runtime data.

    JSON only (no SQLite) — small file, frequent writes, easy to inspect.
    """

    @staticmethod
    def read(path: Path | None = None) -> SoulState:
        p = path or _STATE_PATH
        if not p.exists():
            logger.info("No soul state file found at %s — using defaults", p)
            return SoulState()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return SoulState.model_validate(raw)
        except Exception as exc:
            logger.warning("Failed to read soul state: %s — using defaults", exc)
            return SoulState()

    @staticmethod
    def write(state: SoulState, path: Path | None = None) -> None:
        p = path or _STATE_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(
                json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to write soul state: %s", exc)
