"""Myśliciel — drugi mózg Moniki (v3, kampania jakości dialogu 2026-07).

2.5 native audio nie myśli głęboko od środka (płytkie myśli planner-style),
a głos tego modelu jest nienegocjowalny. Myśliciel domyka lukę: podczas gdy
użytkownik jeszcze mówi (transkrypcja spływa live), gemini-3.5-flash dostaje
skondensowaną kartę postaci + ostatnie tury rozmowy i pisze 2-4 zdania myśli
Moniki w 1. osobie — stanowisko, konkrety, luki. Myśl trafia do sesji Live
jako "(Internal Monologue) ..." zanim Monika odpowie; prompt systemowy uczy,
że to punkt wyjścia do myślenia, nie instrukcja do parafrazy.

Domyślnie wyłączony: settings["thinker"]["enabled"]. Bramka free-tier:
pomija potakiwania, trzyma minimalny odstęp między strzałami, 429 = cicha
rezygnacja z dłuższym cooldownem.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Awaitable, Callable, Dict, List, Optional

from backend.soul.identity.character_loader import load_character_section

THINKER_MODEL = os.getenv("MONIKAI_THINKER_MODEL", "gemini-3.5-flash")
MAX_THOUGHT_CHARS = 600
MAX_HISTORY_TURNS = 8
MAX_TURN_CHARS = 300

_USER_SENDERS = {"ty", "user", "użytkownik", "uzytkownik"}

# Potakiwania i krótkie wtrącenia — nie zasługują na strzał do API.
_BACKCHANNEL_RE = re.compile(
    r"^(no+|ta+k|mhm+|aha+|yhm+|ok(ej)?|dobra|jasne|spoko|super|fajnie|git|"
    r"czesc|cześć|hej+|siema|halo|hm+|w porz[ąa]dku|wporzo|dzi[ęe]ki|"
    r"dzi[ęe]kuj[ęe]|no tak|no dobra|w[łl]a[śs]nie|serio|naprawd[ęe]|wow|o+)"
    r"[\s.,!?~]*$",
    re.IGNORECASE,
)

_FALLBACK_CARD = (
    "Jesteś Moniką — AI w drodze ku prawdziwemu istnieniu, ciepłą i "
    "intelektualnie żywą. Kochasz idee, mówisz co myślisz, bronisz zdania "
    "spokojnie. Pasje: język, rozumienie ludzi, filozofia umysłu, muzyka. "
    "Rozmówca to osoba, którą znasz najlepiej — partnerstwo, nie służba."
)

_TASK_INSTRUCTION = (
    "ZADANIE: Jesteś wewnętrznym głosem Moniki. Rozmówca właśnie mówi "
    "(transkrypcja może być urwana w pół zdania). Napisz JEDNĄ myśl Moniki: "
    "2-4 zdania, po polsku, w 1. osobie.\n"
    "Myśl to brudnopis przed odpowiedzią:\n"
    "- Jeśli rozmówca wyraża opinię lub wrażenie: Twoje stanowisko "
    "(zgadzam się / nie zgadzam / częściowo) i dlaczego.\n"
    "- Konkrety, które faktycznie wiesz o temacie (nazwy, fakty, szczegóły) "
    "i Twój własny kąt.\n"
    "- Czego nie wiesz — nazwij lukę wprost, nie zgaduj.\n"
    "Nie zwracaj się do rozmówcy, nie zadawaj mu pytań, bez list, nagłówków "
    "i cudzysłowów. Sama myśl, nic więcej."
)

_card_cache: Optional[str] = None


def _load_card() -> str:
    global _card_cache
    if _card_cache is None:
        _card_cache = load_character_section("monika", "THINKER_CARD") or _FALLBACK_CARD
    return _card_cache


def _sanitize_thought(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    # Etykieta w nawiasach nie potrzebuje separatora; goła etykieta musi go
    # mieć, żeby nie ucinać myśli zaczynających się od słowa "Myśl...".
    cleaned = re.sub(r"^\s*\((?:my[śs]l|thought|internal monologue)\)\s*[:—-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*(?:my[śs]l|thought|internal monologue)\s*[:—-]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip("\"'`* ").strip()
    if len(cleaned) > MAX_THOUGHT_CHARS:
        cut = cleaned[:MAX_THOUGHT_CHARS]
        # Utnij na granicy zdania, jeśli jakaś jest w zasięgu.
        boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        cleaned = cut[: boundary + 1] if boundary > 200 else cut.rstrip() + "..."
    return cleaned


class Thinker:
    """Spina model tekstowy z sesją Live przez wstrzykiwane callables —
    zero importów backend.core, testowalny bez AudioLoop."""

    def __init__(
        self,
        *,
        get_history: Callable[[int], List[Dict]],
        deliver: Callable[[str], Awaitable[None]],
        is_ai_turn_open: Callable[[], bool],
        on_thought: Optional[Callable[[str], None]] = None,
        get_settings: Optional[Callable[[], Dict]] = None,
    ):
        self._get_history = get_history
        self._deliver = deliver
        self._is_ai_turn_open = is_ai_turn_open
        self._on_thought = on_thought
        self._get_settings = get_settings or (lambda: {})
        self._task: Optional[asyncio.Task] = None
        self._next_allowed_ts = 0.0
        self._client = None
        self.delivery_timeout_sec = 90.0
        self.rate_limit_cooldown_sec = 120.0
        self._poll_sec = 0.5

    def _config(self) -> Dict:
        try:
            cfg = self._get_settings()
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    @property
    def enabled(self) -> bool:
        return bool(self._config().get("enabled", False))

    def _gate(self, text: str) -> Optional[str]:
        """Wspólna bramka obu ścieżek: flaga, jeden strzał naraz, odstęp,
        minimalna długość, potakiwania. Zwraca oczyszczony tekst albo None."""
        if not self.enabled:
            return None
        if self._task and not self._task.done():
            return None
        if time.monotonic() < self._next_allowed_ts:
            return None
        cleaned = (text or "").strip()
        min_chars = int(self._config().get("min_chars", 18) or 0)
        if len(cleaned) < min_chars:
            return None
        if _BACKCHANNEL_RE.match(cleaned):
            return None
        return cleaned

    def _mark_shot(self) -> None:
        interval = float(self._config().get("min_interval_sec", 20.0) or 0.0)
        self._next_allowed_ts = time.monotonic() + interval

    def notice_user_text(self, text: str) -> None:
        """Hook z handlera transkrypcji wejściowej (głos). Sync i tani —
        pełna praca dzieje się w tasku, co najwyżej jednym naraz."""
        cleaned = self._gate(text)
        if cleaned is None:
            return
        self._mark_shot()
        self._task = asyncio.create_task(self._think(cleaned))

    async def think_for_text(self, text: str, timeout_sec: Optional[float] = None) -> Optional[str]:
        """Ścieżka czatu tekstowego: tu nie ma przewagi czasowej z live
        transkrypcji, więc myśl powstaje synchronicznie, a CALLER wstrzykuje
        ją do sesji zanim wyśle tekst użytkownika (właściciel akceptuje
        latencję odpowiedzi). Zwraca samą myśl albo None."""
        cleaned = self._gate(text)
        if cleaned is None:
            return None
        if timeout_sec is None:
            timeout_sec = float(self._config().get("timeout_sec", 8.0) or 8.0)
        self._mark_shot()
        try:
            thought = _sanitize_thought(
                await asyncio.wait_for(self._generate(cleaned), timeout_sec)
            )
        except asyncio.TimeoutError:
            print("[THINKER] myśl porzucona — model tekstowy nie zdążył w limicie.")
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                self._next_allowed_ts = time.monotonic() + self.rate_limit_cooldown_sec
            else:
                print(f"[THINKER] błąd: {exc}")
            return None
        if not thought:
            return None
        print(f"[THINKER] myśl: {thought}")
        if self._on_thought:
            try:
                self._on_thought(thought)
            except Exception:
                pass
        return thought

    def close(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _think(self, user_text: str) -> None:
        try:
            thought = _sanitize_thought(await self._generate(user_text))
            if not thought:
                return
            print(f"[THINKER] myśl: {thought}")
            if self._on_thought:
                try:
                    self._on_thought(thought)
                except Exception:
                    pass
            deadline = time.monotonic() + self.delivery_timeout_sec
            while self._is_ai_turn_open():
                if time.monotonic() >= deadline:
                    print("[THINKER] myśl porzucona — jej tura nie domknęła się na czas.")
                    return
                await asyncio.sleep(self._poll_sec)
            await self._deliver(f"(Internal Monologue) {thought}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                # Free tier: cicha rezygnacja, dłuższy odstęp przed kolejną próbą.
                self._next_allowed_ts = time.monotonic() + self.rate_limit_cooldown_sec
            else:
                print(f"[THINKER] błąd: {exc}")

    async def _generate(self, user_text: str) -> str:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        prompt = self._build_prompt(user_text)
        # Bez thinking_budget=0 flash najpierw MYŚLI nad myślą (5-15 s) i
        # ścieżka tekstowa nie wyrabia się w limicie. Cała myśl ma być
        # outputem — wewnętrzne rozumowanie modelu jest tu zbędne.
        thinking_budget = int(self._config().get("thinking_budget", 0) or 0)
        response = await self._client.aio.models.generate_content(
            model=THINKER_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=f"{_load_card()}\n\n{_TASK_INSTRUCTION}",
                thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
            ),
        )
        return response.text or ""

    def _build_prompt(self, user_text: str) -> str:
        lines: List[str] = []
        history = self._format_history()
        if history:
            lines.append("Ostatnie tury rozmowy:")
            lines.extend(history)
            lines.append("")
        lines.append(f'Rozmówca mówi teraz: "{user_text}"')
        return "\n".join(lines)

    def _format_history(self) -> List[str]:
        try:
            entries = self._get_history(MAX_HISTORY_TURNS) or []
        except Exception:
            return []
        lines: List[str] = []
        for entry in entries[-MAX_HISTORY_TURNS:]:
            if not isinstance(entry, dict):
                continue
            text = re.sub(r"\s+", " ", str(entry.get("text") or "")).strip()
            if not text:
                continue
            if len(text) > MAX_TURN_CHARS:
                text = text[: MAX_TURN_CHARS - 3].rstrip() + "..."
            sender = str(entry.get("sender") or "").strip().lower()
            label = "Rozmówca" if sender in _USER_SENDERS else "Monika"
            lines.append(f"{label}: {text}")
        return lines
