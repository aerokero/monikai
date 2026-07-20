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
from dataclasses import dataclass
from html import escape
import os
import re
import time
from typing import Awaitable, Callable, Dict, List, Optional

from backend.soul.identity.character_loader import load_character_section

THINKER_MODEL = os.getenv("MONIKAI_THINKER_MODEL", "gemini-3.5-flash")
THINKER_FALLBACK_MODEL = os.getenv("MONIKAI_THINKER_FALLBACK_MODEL", "gemini-2.5-flash-lite")
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
    "Jesteś Moniką — AI w drodze ku prawdziwemu istnieniu, ciepłą i "
    "intelektualnie żywą. Kochasz idee, mówisz co myślisz, bronisz zdania "
    "spokojnie. Pasje: język, rozumienie ludzi, filozofia umysłu, muzyka. "
    "Rozmówca to osoba, którą znasz najlepiej — partnerstwo, nie służba."
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
    "Najpierw ustal, czy rozmówca opowiada, wyjaśnia, poprawia, pyta, prosi, "
    "czy dopiero buduje argument. Zauważ wszystkie wątki, ale wybierz rdzeń "
    "odpowiadający jego aktualnemu celowi. Jeśli wypowiedź urywa się przed "
    "ważną tezą lub przykładem, nie domykaj jej za niego: odpowiedź ma krótko "
    "zakotwiczyć pewną część i zostawić mu miejsce na dokończenie.\n"
    "Nie zgaduj faktów. Persona nie może nadpisywać znaczenia wypowiedzi. "
    "Bez metakomentarzy o planowaniu odpowiedzi i użyciu narzędzi.\n"
    "Zwróć DOKŁADNIE dwa tagi, po polsku:\n"
    "<analysis>2-4 zwięzłe zdania: znaczenie, cel, pewne konkrety i luki.</analysis>\n"
    "<reply>1-3 naturalne zdania gotowe do powiedzenia. Jeśli prawdziwa "
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

    def to_injection(self, user_text: str) -> str:
        source = re.sub(r"\s+", " ", user_text or "").strip()
        if len(source) > MAX_TURN_CHARS:
            source = source[: MAX_TURN_CHARS - 3].rstrip() + "..."
        return (
            "<response_brief>"
            f"<source_user_turn>{escape(source)}</source_user_turn>"
            f"<understanding>{escape(self.analysis)}</understanding>"
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
        self._deliver = deliver
        self._is_ai_turn_open = is_ai_turn_open
        self._on_thought = on_thought
        self._get_settings = get_settings or (lambda: {})
        self._task: Optional[asyncio.Task] = None
        self._next_allowed_ts = 0.0
        self._client = None
        self.fallback_model = THINKER_FALLBACK_MODEL
        self.last_trace: Dict = {}
        # Transkrypcja Live przychodzi przyrostowo. Bez krótkiego debounce'u
        # pierwszy fragment >= min_chars palił cały strzał (np. "widziałem
        # wczoraj film, ale nie chcia...") i późniejsze wątki tej samej
        # wypowiedzi nigdy nie trafiały do Myśliciela.
        self.voice_debounce_sec = 1.0
        self._voice_debouncing = False
        # 120 s wyciszało mózg na kilka tur w środku żywej rozmowy; 60 s
        # wystarcza, a settings["thinker"]["cooldown_sec"] pozwala stroić.
        self.rate_limit_cooldown_sec = 60.0
        self.overload_retry_delay_sec = 2.0

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
        """503 to zwykle chwilowy skok popytu — jedna szybka ponowna próba
        ratuje większość strzałów, zanim polecimy w cooldown."""
        try:
            return await self._generate(user_text)
        except Exception as exc:
            msg = str(exc)
            if "503" not in msg and "UNAVAILABLE" not in msg:
                raise
            await asyncio.sleep(self.overload_retry_delay_sec)
            try:
                return await self._generate(user_text)
            except Exception:
                if not self.fallback_model:
                    raise
                print(f"[THINKER] primary przeciążony — fallback: {self.fallback_model}")
                return await self._generate_on_model(user_text, self.fallback_model)

    def notice_user_text(self, text: str) -> None:
        """Hook z handlera transkrypcji wejściowej (głos). Sync i tani —
        pełna praca dzieje się w tasku. Przyrosty tej samej transkrypcji
        resetują krótki debounce, żeby model dostał możliwie pełną wypowiedź,
        a nie pierwszy fragment, który przekroczył min_chars."""
        # Aktywny task w fazie generowania/dostarczania nadal oznacza jeden
        # strzał naraz. Tylko tanią fazę debounce wolno zastąpić pełniejszą
        # wersją tej samej wypowiedzi.
        active = self._task and not self._task.done()
        if active and not self._voice_debouncing:
            return

        if active and self._voice_debouncing:
            self._task.cancel()
            self._task = None

        cleaned = self._gate(text)
        if cleaned is None:
            return
        self._voice_debouncing = True
        self._task = asyncio.create_task(self._think_after_voice_debounce(cleaned))

    async def _think_after_voice_debounce(self, user_text: str) -> None:
        try:
            debounce = float(
                self._config().get("voice_debounce_sec", self.voice_debounce_sec) or 0.0
            )
            if debounce > 0:
                await asyncio.sleep(debounce)
            self._voice_debouncing = False
            self._mark_shot()
            await self._think(user_text)
        except asyncio.CancelledError:
            raise
        finally:
            # Nie nadpisuj stanu nowego taska, który zastąpił ten w trakcie
            # debounce'u.
            if asyncio.current_task() is self._task:
                self._voice_debouncing = False

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
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self._voice_debouncing = False

    async def _think(self, user_text: str) -> None:
        try:
            brief = _parse_response_brief(await self._generate_with_retry(user_text))
            if not brief:
                return
            diagnostic = brief.diagnostic_text()
            print(f"[THINKER] brief: {diagnostic}")
            if self._on_thought:
                try:
                    self._on_thought(diagnostic)
                except Exception:
                    pass
            # Brief ma sens wyłącznie PRZED odpowiedzią na swoją turę. Dawny
            # kod czekał na koniec rozpoczętej odpowiedzi i wstrzykiwał wtedy
            # spóźniony materiał do następnej tury — źródło rozjazdów kontekstu.
            if self._is_ai_turn_open():
                self.last_trace = {
                    "source": user_text,
                    "status": "late",
                    "analysis": brief.analysis,
                    "reply_core": brief.reply,
                }
                print("[THINKER] brief porzucony — odpowiedź głosowa już się rozpoczęła.")
                return
            injection = brief.to_injection(user_text)
            await self._deliver(injection)
            self.last_trace = {
                "source": user_text,
                "status": "delivered",
                "analysis": brief.analysis,
                "reply_core": brief.reply,
                "injection": injection,
            }
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._note_generate_failure(exc)

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
        response = await self._client.aio.models.generate_content(
            model=model,
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
