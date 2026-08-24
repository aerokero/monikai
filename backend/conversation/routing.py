"""Conservative routing between direct conversation and the legacy tool loop."""

from __future__ import annotations

import re


_CAPABILITY_REQUEST_RE = re.compile(
    r"\b("
    r"ustaw|dodaj|dopisz|zanotuj|nadpisz|usuń|usun|anuluj|przypomnij|zapisz|otwórz|otworz|zamknij|"
    r"włącz|wlacz|wyłącz|wylacz|uruchom|wyślij|wyslij|stwórz|stworz|zrób|zrob|weź|wez|"
    r"sprawdź|sprawdz|wyszukaj|znajdź|znajdz|pobierz|przeczytaj|"
    r"set|add|delete|remove|cancel|remind|save|open|close|turn\s+on|"
    r"turn\s+off|start|launch|send|create|check|search|find|download|read|take|write"
    r")\b.*\b("
    r"przypomn\w*|kalendar\w*|wydarzen\w*|plan\w*|notat\w*|plik\w*|folder\w*|"
    r"spotify|muzyk\w*|playlist\w*|pogod\w*|internet\w*|web|stron\w*|"
    r"przeglądark\w*|przegladark\w*|mail\w*|gmail|outlook|światł\w*|"
    r"swiatl\w*|lamp\w*|urządzen\w*|urzadzen\w*|pamięci|pamieci|wspomn\w*|"
    r"rozmow\w*|minecraft|program\w*|komputer\w*|"
    r"reminder|calendar|event|schedule|plan|note|notes|file|folder|music|weather|browser|"
    r"email|light|device|playlist|website|computer"
    r")\b",
    re.IGNORECASE,
)
_DIRECT_OPERATION_RE = re.compile(
    r"\bprzypomnij\s+mi\b|\bremind\s+me\b|"
    r"\b(zanotuj|zanotujmy|zrób\s+notatk\w*|zrob\s+notatk\w*|nowa\s+notatka|"
    r"zapisz\s+(to\s+)?(mi\s+)?(w|do)\s+notat\w*|dopisz\s+(to\s+)?(mi\s+)?(w|do)\s+notat\w*|"
    r"take\s+a\s+note|note\s+down|write\s+down|add\s+(this\s+)?to\s+(my\s+)?notes?)\b|"
    r"\b(co|jakie|jaki|pokaż|pokaz).{0,24}\b(kalendar\w*|wydarzen\w*|plan(\s+na\s+dziś|\s+dnia)?)\b|"
    r"\b(co|jakie|pokaż|pokaz|przeczytaj|odczytaj|wyświetl|wyswietl|show|read|list).{0,24}\b(notat\w*|notes?)\b|"
    r"\b(jaka\s+jest\s+pogoda|jaka\s+pogoda|sprawdź\s+pogodę|sprawdz\s+pogode|weather)\b|"
    r"\b(pamiętasz|pamietasz|co\s+pamiętasz|co\s+pamietasz|"
    r"zapamiętaj|zapamietaj|przypomnij\s+sobie)\b|"
    r"\b(remember|recall|what\s+do\s+you\s+remember)\b|"
    r"\b(co|czego|jaki|jaka|pokaż|pokaz|sprawdź|sprawdz|what|show|check).{0,32}\bspotify\b|"
    r"\b(now\s+playing|recently\s+played|playlists?).{0,20}\bspotify\b|"
    r"\b(jakie|pokaż|pokaz|wylistuj|lista|what|show|list).{0,28}\b"
    r"(urządzen\w*|urzadzen\w*|światł\w*|swiatl\w*|lamp\w*|devices?|lights?|lamps?)\b|"
    r"\b(what|show).{0,20}\b(calendar|events?|schedule)\b",
    re.IGNORECASE,
)


def requires_capability_runtime(
    text: str,
    *,
    has_external_context: bool = False,
) -> bool:
    """Return true when the turn needs tools, attachments, or visual context."""
    if has_external_context:
        return True
    value = str(text or "").strip()
    return bool(
        _CAPABILITY_REQUEST_RE.search(value)
        or _DIRECT_OPERATION_RE.search(value)
    )
