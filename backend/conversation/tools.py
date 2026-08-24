"""Provider-neutral contracts for text-first tool grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ConversationToolRequest:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversationToolResult:
    name: str
    result: str
    ok: bool = True

    def as_evidence(self) -> str:
        status = "success" if self.ok else "error"
        return f"tool={self.name}\nstatus={status}\nresult={self.result}"


@dataclass(frozen=True)
class ToolTurnOutcome:
    handled: bool
    reply: str = ""
    tool_name: str | None = None
    error: str | None = None


class ConversationToolExecutor(Protocol):
    async def execute(
        self,
        request: ConversationToolRequest,
    ) -> ConversationToolResult: ...


@dataclass(frozen=True)
class ConversationToolDefinition:
    name: str
    description: str
    parameters_json_schema: dict[str, Any]


CONVERSATION_TOOL_DEFINITIONS = (
    ConversationToolDefinition(
        name="get_time_context",
        description="Get the current local time, date, timezone, and UTC offset.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    ConversationToolDefinition(
        name="get_weather",
        description="Refresh and get the current weather known to Monika.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    ConversationToolDefinition(
        name="list_reminders",
        description="List the user's currently scheduled reminders.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    ConversationToolDefinition(
        name="create_reminder",
        description=(
            "Create a reminder. Supply exactly one timing field: at in local "
            "YYYY-MM-DD HH:MM format, in_minutes, or in_seconds."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "at": {"type": "string"},
                "in_minutes": {"type": "integer"},
                "in_seconds": {"type": "integer"},
                "speak": {"type": "boolean"},
                "alert": {"type": "boolean"},
            },
            "required": ["message"],
        },
    ),
    ConversationToolDefinition(
        name="cancel_reminder",
        description="Cancel a scheduled reminder when its exact ID is known.",
        parameters_json_schema={
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    ),
    ConversationToolDefinition(
        name="list_events",
        description="List calendar events overlapping a specified local time range.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "start_range_iso": {"type": "string"},
                "end_range_iso": {"type": "string"},
            },
            "required": ["start_range_iso", "end_range_iso"],
        },
    ),
    ConversationToolDefinition(
        name="create_event",
        description=(
            "Create a calendar event only when the user explicitly asks to add "
            "or record it. Use ISO 8601 local timestamps. end_iso is exclusive."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start_iso": {"type": "string"},
                "end_iso": {"type": "string"},
                "description": {"type": "string"},
                "all_day": {"type": "boolean"},
            },
            "required": ["summary", "start_iso", "end_iso"],
        },
    ),
    ConversationToolDefinition(
        name="update_event",
        description="Change the summary of an existing calendar event by exact ID.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["event_id", "summary"],
        },
    ),
    ConversationToolDefinition(
        name="delete_event",
        description="Delete an existing calendar event by exact ID.",
        parameters_json_schema={
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    ),
    ConversationToolDefinition(
        name="notes_get",
        description="Read the user's global notes.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    ConversationToolDefinition(
        name="notes_append",
        description="Append text to the user's global notes without replacing existing content.",
        parameters_json_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    ),
    ConversationToolDefinition(
        name="notes_set",
        description=(
            "Replace all global notes with new content. Use only when the user "
            "explicitly asks to overwrite or replace the whole notes document."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    ),
    ConversationToolDefinition(
        name="memory_search",
        description=(
            "Search durable memory for facts or preferences only when the user "
            "explicitly asks what is remembered or refers to prior knowledge."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    ),
    ConversationToolDefinition(
        name="recall_conversation",
        description=(
            "Find past conversations by topic, title, or date when the user "
            "explicitly refers to an earlier conversation."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    ),
    ConversationToolDefinition(
        name="memory_add_entry",
        description=(
            "Save one distilled fact only after an explicit user request to "
            "remember it. Never save an ordinary conversational detail."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["semantic", "episodic", "stm"],
                },
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "entities": {"type": "array", "items": {"type": "string"}},
                "stability": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
            },
            "required": ["type", "content"],
        },
    ),
    ConversationToolDefinition(
        name="memory_get_page",
        description="Read a markdown page located under the memory/pages directory.",
        parameters_json_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    ConversationToolDefinition(
        name="memory_create_page",
        description=(
            "Create a named markdown page under memory/pages only when the user "
            "explicitly asks for a new memory/topic page."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "folder": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
    ),
    ConversationToolDefinition(
        name="memory_append_page",
        description=(
            "Append content to an existing page under memory/pages. Never "
            "replace its current content."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ),
    ConversationToolDefinition(
        name="spotify_get_status",
        description="Check whether Spotify is configured and connected.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    ConversationToolDefinition(
        name="spotify_get_now_playing",
        description="Get the track currently playing on the user's Spotify account.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    ConversationToolDefinition(
        name="spotify_list_playlists",
        description="List the user's Spotify playlists.",
        parameters_json_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    ),
    ConversationToolDefinition(
        name="spotify_recently_played",
        description="List tracks recently played on the user's Spotify account.",
        parameters_json_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    ),
    ConversationToolDefinition(
        name="list_smart_devices",
        description="List smart-home devices currently known to Monika.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    ConversationToolDefinition(
        name="control_light",
        description=(
            "Control a smart light or compatible device only after an explicit "
            "user command. Preserve the requested action exactly."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "set"],
                },
                "brightness": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                },
                "color": {"type": "string"},
            },
            "required": ["target", "action"],
        },
    ),
)


_TIME_RE = re.compile(
    r"\b(która|ktora)\s+(jest\s+)?godzina\b|"
    r"\b(jaki|który|ktory)\s+(jest\s+)?(dziś|dzisiaj|dzis)\s+(dzień|dzien|data)\b|"
    r"\bwhat\s+time\b|\bwhat(?:'s|\s+is)\s+the\s+date\b",
    re.IGNORECASE,
)
_WEATHER_RE = re.compile(
    r"\b(jaka|jaką|jakiej|sprawdź|sprawdz|powiedz).{0,24}\b"
    r"(pogoda|pogodę|pogode|temperatura)\b|"
    r"\b(weather|temperature)\b",
    re.IGNORECASE,
)
_LIST_REMINDERS_RE = re.compile(
    r"\b(jakie|pokaż|pokaz|wylistuj|lista|czy\s+mam).{0,28}\b"
    r"(przypomnienia|przypomnień|przypomnien|budziki|budzików|alarmy|alarmów)\b|"
    r"\b(list|show|what).{0,20}\b(reminders?|alarms?)\b",
    re.IGNORECASE,
)
_CREATE_REMINDER_INTENT_RE = re.compile(
    r"\b(przypomnij\s+mi|ustaw.{0,28}(przypomn\w*|reminder|budzik\w*|alarm\w*)|"
    r"dodaj.{0,28}(przypomn\w*|reminder|budzik\w*|alarm\w*)|"
    r"(przypomn\w*|reminder|budzik\w*|alarm\w*).{0,28}(ustaw\w*|dodaj\w*|zrób\w*|zrob\w*)|"
    r"obudź\s+mnie|obudz\s+mnie|jako\s+(reminder|przypomn\w*|budzik\w*|alarm\w*)|"
    r"remind\s+me|set.{0,28}(reminder|alarm)|create.{0,28}(reminder|alarm))\b",
    re.IGNORECASE,
)
_CANCEL_REMINDER_INTENT_RE = re.compile(
    r"\b(anuluj|usuń|usun|skasuj|wyłącz|wylacz|cancel|delete|remove).{0,32}\b"
    r"(przypomn\w*|reminder|budzik\w*|alarm\w*)\b",
    re.IGNORECASE,
)
_NEGATED_MUTATION_RE = re.compile(
    r"\b(nie|proszę\s+nie|prosze\s+nie|do\s+not|don't|dont|never)\b.{0,24}\b"
    r"(przypomin|zapamięt|zapamiet|ustaw|dodaw|dopisz|wpis|zapis|zanot|nadpis|zastąp|zastap|"
    r"twórz|tworz|edyt|zmien|przesu|włącz|wlacz|wyłącz|wylacz|zapal|zgaś|zgas|"
    r"anul|usu|kas|remind|remember|set|add|create|edit|update|move|cancel|delete|remove|"
    r"turn\s+on|turn\s+off|switch\s+on|switch\s+off)",
    re.IGNORECASE,
)
_CREATE_EVENT_INTENT_RE = re.compile(
    r"\b(dodaj|wpisz|zapisz|utwórz|utworz|stwórz|stworz|add|create|schedule)"
    r".{0,36}\b(kalendar\w*|wydarzen\w*|event)\b|"
    r"\b(dodaj|wpisz|zapisz).{0,20}\b(do|w)\s+kalendar",
    re.IGNORECASE,
)
_UPDATE_EVENT_INTENT_RE = re.compile(
    r"\b(zmień|zmien|edytuj|zaktualizuj|przesuń|przesun|change|edit|update|move)"
    r".{0,36}\b(wydarzen\w*|event)\b",
    re.IGNORECASE,
)
_DELETE_EVENT_INTENT_RE = re.compile(
    r"\b(usuń|usun|skasuj|anuluj|delete|remove|cancel)"
    r".{0,36}\b(wydarzen\w*|event)\b",
    re.IGNORECASE,
)
_APPEND_NOTES_INTENT_RE = re.compile(
    r"\b(dopisz|dodaj|zapisz|zanotuj|zrób|zrob|append|add|note\s+down|take|write)"
    r".{0,36}\b(notat\w*|notes?)\b|"
    r"\b(zanotuj|zanotujmy|note\s+down|take\s+a\s+note|write\s+down)\b",
    re.IGNORECASE,
)
_SET_NOTES_INTENT_RE = re.compile(
    r"\b(nadpisz|zastąp|zastap|zamień\s+całe|zamien\s+cale|overwrite|replace)"
    r".{0,36}\b(notat\w*|notes?)\b",
    re.IGNORECASE,
)
_MEMORY_WRITE_INTENT_RE = re.compile(
    r"\b(zapamiętaj|zapamietaj|zapisz\s+(to\s+)?w\s+pamięci|"
    r"zapisz\s+(to\s+)?w\s+pamieci|remember\s+this|remember\s+that)\b",
    re.IGNORECASE,
)
_CREATE_MEMORY_PAGE_INTENT_RE = re.compile(
    r"\b(utwórz|utworz|stwórz|stworz|załóż|zaloz|create)"
    r".{0,40}\b(stron\w*|page)\b.{0,20}\b(pamięci|pamieci|memory)\b|"
    r"\b(utwórz|utworz|stwórz|stworz|create).{0,30}\b"
    r"(memory|pamięci|pamieci).{0,20}\b(stron\w*|page)\b",
    re.IGNORECASE,
)
_APPEND_MEMORY_PAGE_INTENT_RE = re.compile(
    r"\b(dopisz|dodaj|append|add).{0,30}\b(do|to)\b.{0,24}\b"
    r"(stron\w*|page)\b",
    re.IGNORECASE,
)
_LIGHT_TARGET_RE = re.compile(
    r"\b(światł\w*|swiatl\w*|lamp\w*|żarów\w*|zarow\w*|light\w*|bulb\w*)\b",
    re.IGNORECASE,
)
_LIGHT_ON_INTENT_RE = re.compile(
    r"\b(włącz|wlacz|zapal|turn\s+on|switch\s+on)\b",
    re.IGNORECASE,
)
_LIGHT_OFF_INTENT_RE = re.compile(
    r"\b(wyłącz|wylacz|zgaś|zgas|turn\s+off|switch\s+off)\b",
    re.IGNORECASE,
)
_LIGHT_SET_INTENT_RE = re.compile(
    r"\b(ustaw|zmień|zmien|set|change)\b.{0,32}\b"
    r"(jasnoś\w*|jasnos\w*|kolor\w*|brightness|colo(?:u)?r)\b",
    re.IGNORECASE,
)
_GET_NOTES_RE = re.compile(
    r"\b(co|jakie|pokaż|pokaz|przeczytaj|odczytaj|wyświetl|wyswietl|show|read|list).{0,24}\b(notat\w*|notes?)\b",
    re.IGNORECASE,
)


def plan_read_only_tool(text: str) -> ConversationToolRequest | None:
    """Recognize a narrow, non-mutating tool set with high precision."""
    value = str(text or "").strip()
    if _TIME_RE.search(value):
        return ConversationToolRequest("get_time_context")
    if _LIST_REMINDERS_RE.search(value):
        return ConversationToolRequest("list_reminders")
    if _WEATHER_RE.search(value):
        return ConversationToolRequest("get_weather")
    if _GET_NOTES_RE.search(value):
        return ConversationToolRequest("notes_get")
    return None


def validate_planned_tool_request(
    text: str,
    request: ConversationToolRequest,
) -> bool:
    """Require deterministic evidence before accepting a mutating model plan."""
    value = str(text or "").strip()
    mutating = {
        "create_reminder",
        "cancel_reminder",
        "create_event",
        "update_event",
        "delete_event",
        "notes_append",
        "notes_set",
        "memory_add_entry",
        "memory_create_page",
        "memory_append_page",
        "control_light",
    }
    if request.name not in mutating:
        return True
    if _NEGATED_MUTATION_RE.search(value):
        return False
    if request.name == "create_reminder":
        return bool(_CREATE_REMINDER_INTENT_RE.search(value))
    if request.name == "cancel_reminder":
        return bool(_CANCEL_REMINDER_INTENT_RE.search(value))
    if request.name == "create_event":
        return bool(_CREATE_EVENT_INTENT_RE.search(value))
    if request.name == "update_event":
        return bool(_UPDATE_EVENT_INTENT_RE.search(value))
    if request.name == "delete_event":
        return bool(_DELETE_EVENT_INTENT_RE.search(value))
    if request.name == "notes_append":
        return bool(_APPEND_NOTES_INTENT_RE.search(value))
    if request.name == "notes_set":
        return bool(_SET_NOTES_INTENT_RE.search(value))
    if request.name == "memory_add_entry":
        return bool(_MEMORY_WRITE_INTENT_RE.search(value))
    if request.name == "memory_create_page":
        return bool(_CREATE_MEMORY_PAGE_INTENT_RE.search(value))
    if request.name == "memory_append_page":
        return bool(_APPEND_MEMORY_PAGE_INTENT_RE.search(value))
    if request.name == "control_light":
        args = request.arguments
        target = str(args.get("target") or "").strip()
        action = str(args.get("action") or "").strip()
        if not target or not _LIGHT_TARGET_RE.search(value):
            return False
        if action == "turn_on":
            return bool(_LIGHT_ON_INTENT_RE.search(value))
        if action == "turn_off":
            return bool(_LIGHT_OFF_INTENT_RE.search(value))
        if action != "set" or not _LIGHT_SET_INTENT_RE.search(value):
            return False
        brightness = args.get("brightness")
        color = args.get("color")
        if brightness is None and color is None:
            return False
        if brightness is not None:
            if isinstance(brightness, bool) or not isinstance(brightness, int):
                return False
            if not 0 <= brightness <= 100:
                return False
        return color is None or bool(str(color).strip())
    return False
