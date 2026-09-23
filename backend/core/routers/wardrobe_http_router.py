"""HTTP adapter and persistence for Monika's Wardrobe system."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import Body, FastAPI, HTTPException

logger = logging.getLogger("monikai.wardrobe")

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_WARDROBE_FILE = _DATA_DIR / "wardrobe.json"

DEFAULT_STATE = {
    "outfit": "def",
    "hairStyle": "def",
    "ahoge": "ahoge_curl",
    "background": "auto",
    "autoMode": False,
}


def load_wardrobe_state() -> dict:
    if _WARDROBE_FILE.exists():
        try:
            with open(_WARDROBE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_STATE, **data}
        except Exception as e:
            logger.warning("Failed to load %s: %s", _WARDROBE_FILE, e)
    return dict(DEFAULT_STATE)


def save_wardrobe_state(state: dict) -> dict:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = load_wardrobe_state()
    current.update(state)
    try:
        with open(_WARDROBE_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to write %s: %s", _WARDROBE_FILE, e)
        raise e
    return current


def register_wardrobe_http_routes(
    app: FastAPI,
    emit_to_frontend: Optional[Callable[[str, Any], Any]] = None,
):
    @app.get("/api/wardrobe")
    async def get_wardrobe():
        state = load_wardrobe_state()
        return {"status": "ok", "state": state}

    @app.post("/api/wardrobe")
    async def update_wardrobe(payload: Dict[str, Any] = Body(...)):
        try:
            saved = save_wardrobe_state(payload)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save wardrobe: {e}")

        if emit_to_frontend:
            try:
                res = emit_to_frontend("set_wardrobe", saved)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

        return {"status": "ok", "state": saved}
