"""Conservative routing between direct conversation and the legacy tool loop."""

from __future__ import annotations

import re


_CAPABILITY_REQUEST_RE = re.compile(
    r"\b("
    r"ustaw|dodaj|dopisz|zanotuj|nadpisz|usuń|usun|anuluj|przypomnij|zapisz|otwórz|otworz|zamknij|"
    r"włącz|wlacz|wyłącz|wylacz|przełącz|przelacz|zmień|zmien|aktywuj|odpal|zgaś|zgas|zaświeć|zaswiec|"
    r"uruchom|wyślij|wyslij|stwórz|stworz|zrób|zrob|weź|wez|"
    r"sprawdź|sprawdz|wyszukaj|znajdź|znajdz|pobierz|przeczytaj|obudź|obudz|"
    r"set|add|delete|remove|cancel|remind|save|open|close|turn\s+on|"
    r"turn\s+off|switch|change|activate|start|launch|send|create|check|search|find|download|read|take|write|wake"
    r")\b.*\b("
    r"przypomn\w*|budzik\w*|alarm\w*|kalendar\w*|wydarzen\w*|plan\w*|notat\w*|plik\w*|folder\w*|"
    r"spotify|muzyk\w*|playlist\w*|pogod\w*|internet\w*|web|stron\w*|"
    r"przeglądark\w*|przegladark\w*|mail\w*|gmail|outlook|światł\w*|"
    r"swiatl\w*|lamp\w*|urządzen\w*|urzadzen\w*|pamięci|pamieci|wspomn\w*|"
    r"rozmow\w*|minecraft|program\w*|komputer\w*|tryb\w*|scen\w*|relaks\w*|wieczor\w*|zakup\w*|"
    r"kuchni\w*|salon\w*|biurk\w*|pokoj\w*|pokój\w*|wszystk\w*|projektor\w*|rzutnik\w*|kin\w*|film\w*|chromecast\w*|cyrkadow\w*|adaptacyjn\w*|"
    r"reminder|calendar|event|schedule|plan|note|notes|file|folder|music|weather|browser|"
    r"email|light|device|playlist|website|computer|scene|mode|shopping|projector|cinema|movie|chromecast"
    r")\b|"
    r"\b("
    r"przypomn\w*|budzik\w*|alarm\w*|kalendar\w*|wydarzen\w*|plan\w*|notat\w*|plik\w*|folder\w*|"
    r"spotify|muzyk\w*|playlist\w*|pogod\w*|światł\w*|swiatl\w*|lamp\w*|urządzen\w*|urzadzen\w*|"
    r"tryb\w*|scen\w*|relaks\w*|wieczor\w*|zakup\w*|kuchni\w*|salon\w*|biurk\w*|pokoj\w*|pokój\w*|wszystk\w*|projektor\w*|rzutnik\w*|kin\w*|film\w*|chromecast\w*|cyrkadow\w*|adaptacyjn\w*|"
    r"reminder|calendar|event|schedule|plan|note|notes|file|folder|music|weather|light|device|scene|mode|shopping|projector|cinema|movie|chromecast"
    r")\b.*\b("
    r"ustaw\w*|dodaj\w*|dopisz\w*|zanotuj\w*|usuń\w*|usun\w*|anuluj\w*|zapisz\w*|włącz\w*|wlacz\w*|wyłącz\w*|wylacz\w*|przełącz\w*|przelacz\w*|zmień\w*|zmien\w*|aktywuj\w*|zgaś\w*|zgas\w*|zaświeć\w*|zaswiec\w*|stwórz\w*|stworz\w*|zrób\w*|zrob\w*|"
    r"set|add|delete|remove|cancel|save|turn\s+on|turn\s+off|switch|change|activate|create"
    r")\b",
    re.IGNORECASE,
)
_DIRECT_OPERATION_RE = re.compile(
    r"\bprzypomnij\s+mi\b|\bremind\s+me\b|\bobudź\s+mnie\b|\bobudz\s+mnie\b|\bustaw\s+budzik\b|\bustaw\s+alarm\b|"
    r"\b(zanotuj|zanotujmy|zrób\s+notatk\w*|zrob\s+notatk\w*|nowa\s+notatka|"
    r"zapisz\s+(to\s+)?(mi\s+)?(w|do)\s+notat\w*|dopisz\s+(to\s+)?(mi\s+)?(w|do)\s+notat\w*|"
    r"take\s+a\s+note|note\s+down|write\s+down|add\s+(this\s+)?to\s+(my\s+)?notes?)\b|"
    r"\b(co|jakie|jaki|pokaż|pokaz).{0,24}\b(kalendar\w*|wydarzen\w*|plan(\s+na\s+dziś|\s+dnia)?)\b|"
    r"\b(co|jakie|pokaż|pokaz|przeczytaj|odczytaj|wyświetl|wyswietl|show|read|list).{0,24}\b(notat\w*|notes?)\b|"
    r"\b(co|jakie|pokaż|pokaz|przeczytaj|odczytaj|wyświetl|wyswietl|lista|list|show|read).{0,24}\b(zakup\w*|shopping)\b|"
    r"\b(jaka\s+jest\s+pogoda|jaka\s+pogoda|sprawdź\s+pogodę|sprawdz\s+pogode|weather)\b|"
    r"\b(pamiętasz|pamietasz|co\s+pamiętasz|co\s+pamietasz|"
    r"zapamiętaj|zapamietaj|przypomnij\s+sobie)\b|"
    r"\b(remember|recall|what\s+do\s+you\s+remember)\b|"
    r"\b(co|czego|jaki|jaka|pokaż|pokaz|sprawdź|sprawdz|what|show|check).{0,32}\bspotify\b|"
    r"\b(now\s+playing|recently\s+played|playlists?).{0,20}\bspotify\b|"
    r"\b(jakie|pokaż|pokaz|wylistuj|lista|what|show|list).{0,28}\b"
    r"(urządzen\w*|urzadzen\w*|światł\w*|swiatl\w*|lamp\w*|devices?|lights?|lamps?)\b|"
    r"\b(tryb|scen\w*|relaks\w*|wieczor\w*)\b|"
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
