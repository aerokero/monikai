"""Runtime bridge for the shared Home Assistant agent.

The native Odysseus routes are mounted before the async application lifespan
creates integrations.  Keep the reference in this tiny dependency-free module
so tool implementations can resolve the live agent at execution time without
introducing a server/route import cycle.
"""

from __future__ import annotations

from typing import Any


_home_assistant_agent: Any = None


def set_home_assistant_agent(agent: Any) -> None:
    """Publish the current shared Home Assistant agent to native tools."""
    global _home_assistant_agent
    _home_assistant_agent = agent


def get_home_assistant_agent() -> Any:
    """Return the live shared Home Assistant agent, if configured."""
    return _home_assistant_agent
