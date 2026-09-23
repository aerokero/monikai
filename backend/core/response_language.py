"""Conversation response-language instruction.

The language of a reply is a conversation setting, not part of a character
persona.  Keeping this layer separate lets the same English persona speak
Polish, English, or another supported language without changing who she is.
"""

from __future__ import annotations

from typing import Any


SUPPORTED_RESPONSE_LANGUAGES = {
    "auto": "same language as the user's latest message",
    "en": "English",
    "pl": "Polish",
    "zh": "Chinese",
    "ja": "Japanese",
}


def normalize_response_language(value: Any) -> str:
    normalized = str(value or "auto").strip().lower()
    return normalized if normalized in SUPPORTED_RESPONSE_LANGUAGES else "auto"


def get_response_language() -> str:
    from .settings_store import SETTINGS

    return normalize_response_language(SETTINGS.get("response_language"))


def response_language_instruction(value: Any = None) -> str:
    language = normalize_response_language(
        get_response_language() if value is None else value
    )
    if language == "auto":
        return (
            "LANGUAGE POLICY (CRITICAL): "
            "Dynamically match the exact language used by the user in their latest message. "
            "If the user writes or speaks in Polish, your reply MUST be entirely in natural Polish. "
            "If the user writes or speaks in English, your reply MUST be in English. "
            "Always follow the user's language shifts immediately. "
            "Never reply in English to a message written in Polish, and never translate unless explicitly requested."
        )
    return (
        f"LANGUAGE POLICY: Respond in {SUPPORTED_RESPONSE_LANGUAGES[language]}. "
        "Keep the selected language unless the user explicitly asks for another one."
    )
