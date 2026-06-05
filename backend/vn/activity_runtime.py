"""Runtime owner for one active shared activity session."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.soul.models import MemoryEntry
from backend.vn.activities import ActivityKind, ActivitySession

logger = logging.getLogger(__name__)

_VALID_KINDS = {"film", "game", "music", "reading", "other"}


class SharedActivityRuntime:
    """Process-scoped active shared activity manager.

    `ActivitySession` owns the domain behavior. This wrapper gives the server a
    stable place to start/end a session and to feed screen OCR updates into it.
    """

    def __init__(self, *, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._active: ActivitySession | None = None
        self._last_context: str = ""

    @property
    def active(self) -> ActivitySession | None:
        return self._active

    def is_active(self) -> bool:
        return self._active is not None

    async def start(
        self,
        kind: str,
        *,
        title: str | None = None,
        context: str = "",
    ) -> ActivitySession:
        if kind not in _VALID_KINDS:
            raise ValueError(f"Unsupported shared activity kind: {kind}")

        if self._active is not None:
            logger.info("Replacing active shared activity: %s", self._active.kind)

        session = await ActivitySession.start(
            kind=kind,  # type: ignore[arg-type]
            title=_clean_optional(title),
            context=_clean_context(context),
        )
        self._active = session
        self._last_context = session.context
        return session

    async def end(self, *, notes: str = "") -> MemoryEntry | None:
        if self._active is None:
            return None

        session = self._active
        self._active = None
        self._last_context = ""
        return await session.end(notes=notes, db_path=self._db_path)

    def update_context(self, context: str) -> bool:
        """Update active session context. Returns True when it changed."""
        if self._active is None:
            return False

        cleaned = _clean_context(context)
        if not cleaned or cleaned == self._last_context:
            return False

        self._active.update_context(cleaned)
        self._last_context = cleaned
        logger.debug("Shared activity context updated (%d chars)", len(cleaned))
        return True

    def monika_context(self) -> str:
        if self._active is None:
            return ""
        return self._active.monika_context()

    def snapshot(self) -> dict[str, Any]:
        if self._active is None:
            return {"active": False}

        scene = self._active.vn_scene()
        return {
            "active": True,
            "kind": self._active.kind,
            "title": self._active.title,
            "context": self._active.context,
            "started_at": self._active.started_at.isoformat(timespec="seconds"),
            "scene": {
                "bg": scene.bg,
                "outfit": scene.outfit,
                "expr": scene.expr,
                "light": scene.light,
                "ambience": scene.ambience,
            },
        }


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_context(value: str) -> str:
    return " ".join(str(value or "").split())[:2000]
