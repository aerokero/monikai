"""Home Assistant tool implementation for native Odysseus chat."""

from __future__ import annotations

from typing import Any, Dict, Optional


async def do_home_assistant_control(
    content: str,
    owner: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the same constrained HA mutation used by scheduled Tasks.

    The task action owns JSON validation, entity-filter enforcement, aliases,
    and the actual service call.  Reusing it keeps chat and Tasks consistent
    and prevents this native tool from becoming a generic HA proxy.
    """
    from src.builtin_actions import action_home_assistant_control
    from src.home_assistant_runtime import get_home_assistant_agent

    message, ok = await action_home_assistant_control(
        owner=owner or "owner",
        home_assistant_agent=get_home_assistant_agent(),
        prompt=content,
        # Interactive chat may honor an explicit “all lights” request. The
        # shared action maps that target to Home Assistant's light-domain
        # ``entity_id: all`` service; named targets still use the configured
        # entity filter, while scheduled Tasks keep their stricter single-
        # target default.
        allow_broad_targets=True,
    )
    return {
        "output": message,
        "exit_code": 0 if ok else 1,
    }
