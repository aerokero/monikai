"""Service for managing centralized savings ledger persistence."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("monikai.savings_service")

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_LEDGER_FILE = _DATA_DIR / "savings_ledger.json"


class SavingsService:
    def __init__(self, ledger_file: Optional[Path] = None):
        self._file = ledger_file or _LEDGER_FILE

    def get_ledger(self) -> Dict[str, Any]:
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {"initialized": True, "ledger": data}
            except Exception as e:
                logger.warning("Failed to read %s: %s", self._file, e)
        return {"initialized": False, "ledger": None}

    def save_ledger(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to write %s: %s", self._file, e)
            raise e
        return payload

    def reset_ledger(self) -> Dict[str, Any]:
        if self._file.exists():
            try:
                self._file.unlink()
            except Exception as e:
                logger.error("Failed to delete %s: %s", self._file, e)
                raise e
        return {"initialized": False, "ledger": None}


_instance: Optional[SavingsService] = None


def get_savings_service() -> SavingsService:
    global _instance
    if _instance is None:
        _instance = SavingsService()
    return _instance
