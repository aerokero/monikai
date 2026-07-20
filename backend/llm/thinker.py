"""Myśliciel — drugi mózg Moniki (v3, kampania jakości dialogu 2026-07).

2.5 native audio nie myśli głęboko od środka (płytkie myśli planner-style),
a głos tego modelu jest nienegocjowalny. Myśliciel domyka lukę: podczas gdy
użytkownik jeszcze mówi (transkrypcja spływa live), gemini-3.5-flash dostaje
skondensowaną kartę postaci + ostatnie tury rozmowy i tworzy strukturalny brief:
rozumienie wypowiedzi oraz gotowy rdzeń odpowiedzi. Brief trafia do sesji Live
zanim Monika odpowie; model głosowy renderuje go swoim głosem, zamiast ponownie
rozstrzygać znaczenie wypowiedzi od zera.

Domyślnie wyłączony: settings["thinker"]["enabled"]. Bramka free-tier:
pomija potakiwania, trzyma minimalny odstęp między strzałami, 429 = cicha
rezygnacja z dłuższym cooldownem.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from dataclasses import dataclass
from html import escape
import os
import re
import time
from typing import Awaitable, Callable, Dict, List, Optional

from backend.soul.identity.character_loader import load_character_section

THINKER_MODEL = os.getenv("MONIKAI_THINKER_MODEL", "gemini-3.5-flash")
THINKER_FALLBACK_MODEL = os.getenv("MONIKAI_THINKER_FALLBACK_MODEL", "gemini-3.1-flash-lite")
MAX_THOUGHT_CHARS = 600
MAX_HISTORY_TURNS = 8
MAX_TURN_CHARS = 300

_USER_SENDERS = {"ty", "user", "użytkownik", "uzytkownik"}

# Potakiwania, krótkie wtrącenia i kontrola łącza — nie zasługują na strzał
# do API.
_BACKCHANNEL_RE = re.compile(
    r"^(no+|ta+k|mhm+|aha+|yhm+|ok(ej)?|dobra|jasne|spoko|super|fajnie|git|"
    r"czesc|cześć|hej+|siema|hm+|w porz[ąa]dku|wporzo|dzi[ęe]ki|"
    r"dzi[ęe]kuj[ęe]|no tak|no dobra|w[łl]a[śs]nie|serio|naprawd[ęe]|wow|o+|"
    r"halo+([\s,]+(s[łl]yszymy si[ęe]|s[łl]yszysz( mnie)?))?|"
    r"s[łl]yszymy si[ęe]|s[łl]yszysz( mnie)?|jeste[śs] tam)"
    r"[\s.,!?~]*$",
    re.IGNORECASE,
)

_FALLBACK_CARD = (
    "Jesteś Moniką: ciepłą, bezpośrednią i intelektualnie żywą rozmówczynią. "
    "Kochasz idee, mówisz co myślisz i bronisz zdania spokojnie. Charakter "
    "wpływa na trafność, ton i język, ale nigdy sam nie staje się tematem."
)

_TASK_INSTRUCTION = (
    "ZADANIE: jesteś wolniejszą warstwą rozumowania Moniki. Przygotuj brief "
    "dla modelu głosowego, który ma już tylko naturalnie wypowiedzieć jego rdzeń.\n"
    "HIERARCHIA UZIEMIENIA:\n"
    "1. Literalna treść bieżącej wypowiedzi i jej cel komunikacyjny.\n"
    "2. Kontekst ostatnich tur i niedomknięte wątki.\n"
    "3. Wiedza i stanowisko Moniki.\n"
    "4. Persona wyłącznie jako ton i perspektywa — nigdy jako nowy temat.\n"
    "Nie wprowadzaj motywu, którego rozmówca nie wniósł i który nie jest "
    "potrzebny do odpowiedzi. Rozwiąż zaimki i terminy z całego kontekstu; "
    "nie zamieniaj przedmiotu wypowiedzi na podobny, łatwiejszy temat.\n"
    "Gdy pojawia się konkretny temat, porzuć wcześniejszą ramę testowania, "
    "scenariuszy i działania systemu, chyba że rozmówca jawnie nadal pyta "
    "właśnie o nią. Nie zmieniaj tematu rozmówcy w autorefleksję o sobie.\n"
    "Najpierw ustal, czy rozmówca opowiada, wyjaśnia, poprawia, pyta, prosi, "
    "czy dopiero buduje argument. Zauważ wszystkie wątki, ale wybierz rdzeń "
    "odpowiadający jego aktualnemu celowi. Jeśli wypowiedź urywa się przed "
    "ważną tezą lub przykładem, nie domykaj jej za niego: odpowiedź ma krótko "
    "zakotwiczyć pewną część i zostawić mu miejsce na dokończenie.\n"
    "Nie zgaduj faktów. Persona nie może nadpisywać znaczenia wypowiedzi. "
    "Bez metakomentarzy o planowaniu odpowiedzi i użyciu narzędzi.\n"
    "Zwróć DOKŁADNIE dwa tagi, po polsku:\n"
    "<analysis>2-4 zwięzłe zdania: znaczenie, cel, pewne konkrety i luki.</analysis>\n"
    "<reply>1-3 naturalne zdania będące FINALNYM tekstem do wypowiedzenia, a "
    "nie wskazówką dla kolejnego autora. Odpowiedź ma posunąć rozmowę naprzód, "
    "nie tylko powtórzyć dylemat rozmówcy innymi słowami. Jeśli prawdziwa "
    "ciekawość wymaga pytania, umieść dokładnie jedno konkretne pytanie tutaj.</reply>\n"
    "Jeśli wypowiedź to zwykły small talk albo technika rozmowy (powitanie, "
    "potwierdzenie, sprawdzanie połączenia) i nie ma w niej nic, o czym "
    "warto mieć zdanie — odpowiedz dokładnie jednym słowem: PASS."
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
    # Model uznał, że nie ma o czym myśleć (small talk) — nie wstrzykujemy.
    if cleaned.strip(".!? ").lower() == "pass":
        return ""
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


@dataclass(frozen=True)
class ResponseBrief:
    analysis: str
    reply: str

    def diagnostic_text(self) -> str:
        return f"Analiza: {self.analysis} | Rdzeń odpowiedzi: {self.reply}"

    def to_injection(self, user_text: str = "") -> str:
        # Renderer nie dostaje ponownie źródłowej tury ani analizy. Oba pola
        # kusiły model Live do ponownej interpretacji i parafrazy użytkownika
        # zamiast wypowiedzenia lepszego tekstu przygotowanego przez Thinkera.
        # Pełny ślad nadal pozostaje w last_trace i raporcie diagnostycznym.
        return (
            '<response_brief mode="verbatim">'
            f"<reply_core>{escape(self.reply)}</reply_core>"
            "</response_brief>"
        )


def _parse_response_brief(text: str) -> Optional[ResponseBrief]:
    raw = str(text or "").strip()
    if raw.strip(".!? ").lower() == "pass":
        return None
    analysis_match = re.search(r"<analysis>(.*?)</analysis>", raw, re.IGNORECASE | re.DOTALL)
    reply_match = re.search(r"<reply>(.*?)</reply>", raw, re.IGNORECASE | re.DOTALL)
    if not analysis_match or not reply_match:
        return None
    analysis = _sanitize_thought(analysis_match.group(1))
    reply = _sanitize_thought(reply_match.group(1))
    if not analysis or not reply:
        return None
    return ResponseBrief(analysis=analysis, reply=reply)


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
        self._history_override: ContextVar[Optional[Callable[[int], List[Dict]]]] = ContextVar(
            f"thinker_history_override_{id(self)}", default=None
        )
        self._deliver = deliver
        self._is_ai_turn_open = is_ai_turn_open
        self._on_thought = on_thought
        self._get_settings = get_settings or (lambda: {})
        self._next_allowed_ts = 0.0
        self._client = None
        self.fallback_model = THINKER_FALLBACK_MODEL
        self.last_trace: Dict = {}
        # 120 s wyciszało mózg na kilka tur w środku żywej rozmowy; 60 s
        # wystarcza, a settings["thinker"]["cooldown_sec"] pozwala stroić.
        self.rate_limit_cooldown_sec = 60.0
        self.overload_retry_delay_sec = 2.0
        self._pending_voice_text = ""

    def _config(self) -> Dict:
        try:
            cfg = self._get_settings()
        except Exception:
            return {}
        return cfg if isinstance(cfg, dict) else {}

    @property
    def enabled(self) -> bool:
        return bool(self._config().get("enabled", False))

    def set_history_provider(
        self, provider: Callable[[int], List[Dict]]
    ) -> Token[Optional[Callable[[int], List[Dict]]]]:
        """Override history only in the current async context."""
        return self._history_override.set(provider)

    def reset_history_provider(
        self, token: Token[Optional[Callable[[int], List[Dict]]]]
    ) -> None:
        self._history_override.reset(token)

    def _gate(self, text: str) -> Optional[str]:
        """Wspólna bramka obu ścieżek: flaga, jeden strzał naraz, odstęp,
        minimalna długość, potakiwania. Zwraca oczyszczony tekst albo None."""
        if not self.enabled:
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
        interval = float(self._config().get("min_interval_sec", 0.0) or 0.0)
        self._next_allowed_ts = time.monotonic() + interval

    def _note_generate_failure(self, exc: Exception) -> None:
        """Free tier: limit (429) i przeciążenie (503) to normalna pogoda,
        nie błąd — jedna krótka linia i dłuższa przerwa przed kolejną próbą."""
        msg = str(exc)
        if any(tok in msg for tok in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")):
            cooldown = float(self._config().get("cooldown_sec", self.rate_limit_cooldown_sec) or 0.0)
            self._next_allowed_ts = time.monotonic() + cooldown
            print(f"[THINKER] model niedostępny (limit/przeciążenie) — przerwa {cooldown:.0f} s.")
        else:
            print(f"[THINKER] błąd: {exc}")

    async def _generate_with_retry(self, user_text: str) -> str:
        """Recover from capacity limits without handing reasoning to audio.

        503 gets one same-model retry; 429 goes directly to the lower-cost
        fallback because retrying the exhausted model burns turn latency.
        """
        try:
            return await self._generate(user_text)
        except Exception as exc:
            msg = str(exc)
            is_overload = "503" in msg or "UNAVAILABLE" in msg
            is_rate_limit = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            if not is_overload and not is_rate_limit:
                raise
            last_error = exc
            if is_overload:
                await asyncio.sleep(self.overload_retry_delay_sec)
                try:
                    return await self._generate(user_text)
                except Exception as retry_exc:
                    last_error = retry_exc
            if not self.fallback_model:
                raise last_error
            print(f"[THINKER] primary niedostępny — fallback: {self.fallback_model}")
            return await self._generate_on_model(user_text, self.fallback_model)

    def update_voice_transcript(self, text: str) -> None:
        """Store the latest ASR revision without generating a partial brief."""
        self._pending_voice_text = re.sub(r"\s+", " ", text or "").strip()

    async def prepare_voice_turn(self, text: str = "") -> Optional[str]:
        """Generate exactly one brief at the real end of speech."""
        final_text = re.sub(r"\s+", " ", text or self._pending_voice_text).strip()
        self._pending_voice_text = ""
        injection = await self.think_for_text(final_text)
        if not injection:
            return None
        if self._is_ai_turn_open():
            self.last_trace = {**self.last_trace, "status": "late"}
            print("[THINKER] brief porzucony — odpowiedź głosowa już się rozpoczęła.")
            return None
        self.last_trace = {**self.last_trace, "status": "prepared"}
        return injection

    async def finalize_voice_turn(self, text: str = "") -> bool:
        """Compatibility helper; runtime uses prepare + ordered realtime send."""
        injection = await self.prepare_voice_turn(text)
        if not injection:
            return False
        await self._deliver(injection)
        self.last_trace = {**self.last_trace, "status": "delivered"}
        return True

    def mark_voice_delivered(self) -> None:
        if self.last_trace.get("status") == "prepared":
            self.last_trace = {**self.last_trace, "status": "delivered"}

    async def think_for_text(self, text: str, timeout_sec: Optional[float] = None) -> Optional[str]:
        """Ścieżka czatu tekstowego: buduje brief synchronicznie. CALLER
        wstrzykuje zwrócony XML przed tekstem użytkownika."""
        cleaned = self._gate(text)
        if cleaned is None:
            self.last_trace = {"source": str(text or "").strip(), "status": "skipped"}
            return None
        if timeout_sec is None:
            timeout_sec = float(self._config().get("timeout_sec", 8.0) or 8.0)
        self._mark_shot()
        try:
            brief = _parse_response_brief(
                await asyncio.wait_for(self._generate_with_retry(cleaned), timeout_sec)
            )
        except asyncio.TimeoutError:
            self.last_trace = {"source": cleaned, "status": "timeout"}
            print("[THINKER] brief porzucony — model tekstowy nie zdążył w limicie.")
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_trace = {"source": cleaned, "status": "error", "error": str(exc)}
            self._note_generate_failure(exc)
            return None
        if not brief:
            self.last_trace = {"source": cleaned, "status": "invalid_or_pass"}
            return None
        injection = brief.to_injection(cleaned)
        self.last_trace = {
            "source": cleaned,
            "status": "ready",
            "analysis": brief.analysis,
            "reply_core": brief.reply,
            "injection": injection,
        }
        diagnostic = brief.diagnostic_text()
        print(f"[THINKER] brief: {diagnostic}")
        if self._on_thought:
            try:
                self._on_thought(diagnostic)
            except Exception:
                pass
        return injection

    def close(self) -> None:
        self._pending_voice_text = ""

    async def _generate(self, user_text: str) -> str:
        return await self._generate_on_model(user_text, THINKER_MODEL)

    async def _generate_on_model(self, user_text: str, model: str) -> str:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        prompt = self._build_prompt(user_text)
        # Bez thinking_budget=0 flash najpierw długo myśli nad briefem (5-15 s)
        # i ścieżka tekstowa nie wyrabia się w limicie. Analiza ma być jawnie
        # w polu <analysis>, więc ukryte rozumowanie jest tu zbędnym narzutem.
        thinking_budget = int(self._config().get("thinking_budget", 0) or 0)
        model_thinking = (
            types.ThinkingConfig(thinking_level="minimal")
            if model == self.fallback_model and str(model).startswith("gemini-3")
            else types.ThinkingConfig(thinking_budget=thinking_budget)
        )
        response = await self._client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=f"{_load_card()}\n\n{_TASK_INSTRUCTION}",
                thinking_config=model_thinking,
            ),
        )
        return response.text or ""

    def _build_prompt(self, user_text: str) -> str:
        lines: List[str] = []
        history = self._format_history(exclude_user_text=user_text)
        if history:
            lines.append("Ostatnie tury rozmowy:")
            lines.extend(history)
            lines.append("")
        lines.append(f'Rozmówca mówi teraz: "{user_text}"')
        return "\n".join(lines)

    def _format_history(self, exclude_user_text: str = "") -> List[str]:
        try:
            provider = self._history_override.get() or self._get_history
            entries = provider(MAX_HISTORY_TURNS) or []
        except Exception:
            return []
        recent = list(entries[-MAX_HISTORY_TURNS:])
        # Text/programmatic paths log the current user turn before invoking the
        # Thinker. Do not show that same turn twice (history + "mówi teraz").
        if recent and exclude_user_text:
            last = recent[-1]
            if isinstance(last, dict):
                last_sender = str(last.get("sender") or "").strip().lower()
                last_text = re.sub(r"\s+", " ", str(last.get("text") or "")).strip()
                current = re.sub(r"\s+", " ", exclude_user_text).strip()
                if last_sender in _USER_SENDERS and last_text == current:
                    recent.pop()

        lines: List[str] = []
        for entry in recent:
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
