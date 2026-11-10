"""Runtime bridge for the server speaker and the alarm manager.

Same recipe as ``home_assistant_runtime``: native Odysseus code is mounted
before the MonikAI lifespan builds the microphone listener and the alarm
manager, so tools and delivery paths resolve the live objects at call time.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_announcer: Optional[Callable[[str], Awaitable[None]]] = None
_alarm_manager: Any = None


def set_announcer(fn: Optional[Callable[[str], Awaitable[None]]]) -> None:
    global _announcer
    _announcer = fn


def set_alarm_manager(manager: Any) -> None:
    global _alarm_manager
    _alarm_manager = manager


def get_alarm_manager() -> Any:
    return _alarm_manager


async def announce(text: str) -> bool:
    """Speak ``text`` on the server speakers. Never raises."""
    text = (text or "").strip()
    if not text or _announcer is None:
        return False
    try:
        await _announcer(text)
        return True
    except Exception as exc:
        logger.warning("Server speaker announcement failed: %s", exc)
        return False
