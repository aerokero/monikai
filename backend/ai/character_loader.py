"""Backwards-compatibility shim — canonical location is soul/identity/.

Re-exports load_character_prompt and list_characters so existing imports
continue to work during the v2 transition.
"""

from backend.soul.identity.character_loader import (  # noqa: F401
    load_character_prompt,
    list_characters,
)
