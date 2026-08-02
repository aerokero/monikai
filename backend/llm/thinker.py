"""Text-first response author and structured tool planner for Monika."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from html import escape
import hashlib
import os
import re
import time
from typing import Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

from backend.conversation.author import (
    AUTHOR_INSTRUCTION,
    ResponseBrief,
    parse_response_brief,
)
from backend.soul.identity.character_loader import load_character_section
from backend.conversation.models import CompiledConversationContext
from backend.conversation.providers import (
    GeminiTextProvider,
    TextGenerationRequest,
    ToolPlanningRequest,
)
from backend.conversation.tools import (
    ConversationToolDefinition,
    ConversationToolRequest,
)
from backend.conversation.validator import (
    ConversationResponseValidator,
    build_revision_prompt,
)

THINKER_MODEL = os.getenv(
    "MONIKAI_CONVERSATION_MODEL",
    os.getenv("MONIKAI_THINKER_MODEL", "gemini-3.5-flash"),
)
THINKER_FALLBACK_MODEL = os.getenv(
    "MONIKAI_CONVERSATION_FALLBACK_MODEL",
    os.getenv("MONIKAI_THINKER_FALLBACK_MODEL", "gemini-3.1-pro-preview"),
)
THINKER_EMERGENCY_MODEL = os.getenv(
    "MONIKAI_CONVERSATION_EMERGENCY_MODEL",
    "gemini-3.5-flash-lite",
)
MAX_THOUGHT_CHARS = 600
MAX_HISTORY_TURNS = 8
MAX_TURN_CHARS = 300

_USER_SENDERS = {"ty", "user", "użytkownik", "uzytkownik"}

# Czyste potakiwania i wtrącenia w trakcie już trwającej wypowiedzi — nie
# zasługują na strzał do API. NIE wolno tu wrzucać powitań ("hej", "cześć")
# ani kontroli łącza ("halo, słyszysz mnie?", "jesteś tam?"): w trybie
# dedicated_speech Thinker jest JEDYNYM kanałem odpowiedzi, więc odrzucenie
# tu = całkowita cisza bez żadnego komunikatu — gorsze niż zbędny strzał.
_BACKCHANNEL_RE = re.compile(
    r"^(no+|ta+k(?:\s+ta+k)*|mhm+|aha+|yhm+|ok(ej)?|dobra|jasne|spoko|super|fajnie|git|"
    r"hm+|w porz[ąa]dku|wporzo|dzi[ęe]ki|"
    r"dzi[ęe]kuj[ęe]|no tak|no dobra|w[łl]a[śs]nie|serio|naprawd[ęe]|wow|o+)"
    r"[\s.,!?~]*$",
    re.IGNORECASE,
)

_FALLBACK_CARD = (
    "Jesteś Moniką: ciepłą, bezpośrednią i intelektualnie żywą rozmówczynią. "
    "Kochasz idee, mówisz co myślisz i bronisz zdania spokojnie. Charakter "
    "wpływa na trafność, ton i język, ale nigdy sam nie staje się tematem."
)

_TASK_INSTRUCTION = AUTHOR_INSTRUCTION

_card_cache: Optional[str] = None


class ContextCompilationError(RuntimeError):
    """The configured immutable context could not be built for this turn."""


def _compact_error(exc: Exception, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(exc or "")).strip()[:limit]


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


def _parse_response_brief(text: str) -> Optional[ResponseBrief]:
    return parse_response_brief(text)


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
        get_conversation_id: Optional[Callable[[], str | None]] = None,
        get_world_snapshot: Optional[Callable] = None,
    ):
        self._get_history = get_history
        self._history_override: ContextVar[Optional[Callable[[int], List[Dict]]]] = ContextVar(
            f"thinker_history_override_{id(self)}", default=None
        )
        self._deliver = deliver
        self._is_ai_turn_open = is_ai_turn_open
        self._on_thought = on_thought
        self._get_settings = get_settings or (lambda: {})
        self._get_conversation_id = get_conversation_id
        self._next_allowed_ts = 0.0
        self._text_provider = None
        self._last_success_model: str | None = None
        self.fallback_model = THINKER_FALLBACK_MODEL
        self.emergency_model = THINKER_EMERGENCY_MODEL
        self.last_trace: Dict = {}
        self._last_context_trace: Dict = {}
        self._last_validation_trace: Dict = {}
        self._generation_attempts: list[dict] = []
        self._validator = ConversationResponseValidator()
        # 120 s wyciszało mózg na kilka tur w środku żywej rozmowy; 60 s
        # wystarcza, a settings["thinker"]["cooldown_sec"] pozwala stroić.
        self.rate_limit_cooldown_sec = 60.0
        self.overload_retry_delay_sec = 2.0
        self._pending_voice_text = ""
        self._compiled_context: ContextVar[Optional[CompiledConversationContext]] = ContextVar(
            f"thinker_compiled_context_{id(self)}", default=None
        )
        self._context_compiler = None
        if get_conversation_id is not None:
            from backend.conversation.context import ConversationContextCompiler

            self._context_compiler = ConversationContextCompiler(
                get_history=lambda limit: (
                    self._history_override.get() or self._get_history
                )(limit),
                get_conversation_id=get_conversation_id,
                get_world_snapshot=get_world_snapshot,
            )

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
        if not cleaned:
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
        async def attempt(label: str, model: str, generate) -> str:
            started = time.monotonic()
            try:
                result = await generate()
                self._generation_attempts.append(
                    {
                        "attempt": label,
                        "model": model,
                        "status": "success",
                        "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    }
                )
                return result
            except Exception as exc:
                self._generation_attempts.append(
                    {
                        "attempt": label,
                        "model": model,
                        "status": "error",
                        "latency_ms": round((time.monotonic() - started) * 1000, 1),
                        "error_type": type(exc).__name__,
                        "error": _compact_error(exc),
                    }
                )
                raise

        try:
            return await attempt(
                "primary",
                THINKER_MODEL,
                lambda: self._generate(user_text),
            )
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
                    return await attempt(
                        "primary_retry",
                        THINKER_MODEL,
                        lambda: self._generate(user_text),
                    )
                except Exception as retry_exc:
                    last_error = retry_exc
            if not self.fallback_model:
                raise last_error
            print(f"[THINKER] primary niedostępny — fallback: {self.fallback_model}")
            try:
                return await attempt(
                    "fallback",
                    self.fallback_model,
                    lambda: self._generate_on_model(
                        user_text,
                        self.fallback_model,
                    ),
                )
            except Exception as fallback_exc:
                if (
                    not self.emergency_model
                    or self.emergency_model == self.fallback_model
                ):
                    raise
                print(
                    "[THINKER] fallback niedostępny — awaryjny model: "
                    f"{self.emergency_model}"
                )
                return await attempt(
                    "emergency_fallback",
                    self.emergency_model,
                    lambda: self._generate_on_model(
                        user_text,
                        self.emergency_model,
                    ),
                )

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

    async def prepare_spoken_reply(
        self,
        text: str = "",
        *,
        turn_evidence: str | None = None,
    ) -> Optional[str]:
        """Author final display/speech text without creating a Live prompt."""
        final_text = re.sub(r"\s+", " ", text or self._pending_voice_text).strip()
        self._pending_voice_text = ""
        injection = await self.think_for_text(
            final_text,
            turn_evidence=turn_evidence,
        )
        if not injection:
            return None
        if self._is_ai_turn_open():
            self.last_trace = {**self.last_trace, "status": "late"}
            print("[THINKER] odpowiedź porzucona — poprzednia tura nadal trwa.")
            return None
        reply = str(self.last_trace.get("reply_core") or "").strip()
        if not reply:
            return None
        self.last_trace = {**self.last_trace, "status": "prepared"}
        return reply

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

    async def think_for_text(
        self,
        text: str,
        timeout_sec: Optional[float] = None,
        *,
        turn_evidence: str | None = None,
    ) -> Optional[str]:
        """Ścieżka czatu tekstowego: buduje brief synchronicznie. CALLER
        wstrzykuje zwrócony XML przed tekstem użytkownika."""
        cleaned = self._gate(text)
        if cleaned is None:
            self.last_trace = {"source": str(text or "").strip(), "status": "skipped"}
            self._last_context_trace = {}
            self._last_validation_trace = {}
            return None
        if timeout_sec is None:
            timeout_sec = float(self._config().get("timeout_sec", 8.0) or 8.0)
        self._mark_shot()
        try:
            brief = _parse_response_brief(
                await self._generate_with_compiled_context(
                    cleaned,
                    generation_timeout_sec=timeout_sec,
                    turn_evidence=turn_evidence,
                )
            )
        except asyncio.TimeoutError:
            self.last_trace = {
                "source": cleaned,
                "status": "timeout",
                "context": dict(self._last_context_trace),
                "validation": dict(self._last_validation_trace),
                "generation": list(self._generation_attempts),
            }
            print("[THINKER] brief porzucony — model tekstowy nie zdążył w limicie.")
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_trace = {
                "source": cleaned,
                "status": "error",
                "error": str(exc),
                "context": dict(self._last_context_trace),
                "validation": dict(self._last_validation_trace),
                "generation": list(self._generation_attempts),
            }
            self._note_generate_failure(exc)
            return None
        if not brief:
            self.last_trace = {
                "source": cleaned,
                "status": "invalid_or_pass",
                "context": dict(self._last_context_trace),
                "validation": dict(self._last_validation_trace),
                "generation": list(self._generation_attempts),
            }
            return None
        injection = brief.to_injection(cleaned)
        self.last_trace = {
            "source": cleaned,
            "status": "ready",
            "author_model": self._last_success_model,
            "analysis": brief.analysis,
            "reply_core": brief.reply,
            "injection": injection,
            "context": dict(self._last_context_trace),
            "validation": dict(self._last_validation_trace),
            "generation": list(self._generation_attempts),
        }
        diagnostic = brief.diagnostic_text()
        print(f"[THINKER] brief: {diagnostic}")
        if self._on_thought:
            try:
                self._on_thought(diagnostic)
            except Exception:
                pass
        return injection

    async def _generate_with_compiled_context(
        self,
        user_text: str,
        *,
        generation_timeout_sec: float | None = None,
        turn_evidence: str | None = None,
    ) -> str:
        """Compile one immutable turn context and reuse it for all retries."""
        compiled = await self._compile_turn_context(
            user_text,
            turn_evidence=turn_evidence,
        )
        self._last_validation_trace = {"status": "not_run", "issues": []}
        if self._context_compiler is not None and compiled is None:
            raise ContextCompilationError(
                str(self._last_context_trace.get("error") or "context compilation failed")
            )

        token = self._compiled_context.set(compiled)
        try:
            generation = self._generate_with_retry(user_text)
            raw = (
                await asyncio.wait_for(generation, generation_timeout_sec)
                if generation_timeout_sec is not None
                else await generation
            )
            brief = _parse_response_brief(raw)
            if brief is None:
                self._last_validation_trace = {
                    "status": "invalid_response",
                    "issues": [],
                }
                return raw

            validation = self._validator.validate(
                user_text=user_text,
                reply=brief.reply,
                recent_assistant_messages=self._recent_assistant_messages(),
            )
            self._last_validation_trace = {
                "status": "rewrite_needed" if validation.needs_rewrite else "passed",
                "issues": [issue.code for issue in validation.issues],
            }
            if not validation.needs_rewrite:
                return raw
            if compiled is None:
                self._last_validation_trace["status"] = "rejected_no_revision_context"
                return ""

            try:
                revision_timeout = float(
                    self._config().get("revision_timeout_sec", 2.5) or 2.5
                )
                revised_raw = await asyncio.wait_for(
                    self._revise_once(
                        compiled=compiled,
                        candidate=brief,
                        issues=validation.issues,
                    ),
                    timeout=max(0.1, revision_timeout),
                )
                revised = _parse_response_brief(revised_raw)
                if revised is None:
                    self._last_validation_trace["status"] = "revision_invalid"
                    return ""
                revised_validation = self._validator.validate(
                    user_text=user_text,
                    reply=revised.reply,
                    recent_assistant_messages=self._recent_assistant_messages(),
                )
                self._last_validation_trace = {
                    "status": (
                        "corrected"
                        if not revised_validation.needs_rewrite
                        else "corrected_with_remaining_issues"
                    ),
                    "issues": [issue.code for issue in validation.issues],
                    "remaining_issues": [
                        issue.code for issue in revised_validation.issues
                    ],
                }
                if revised_validation.needs_rewrite:
                    return ""
                return revised_raw
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_validation_trace["status"] = "revision_failed"
                self._last_validation_trace["error_type"] = type(exc).__name__
                self._last_validation_trace["error"] = (
                    _compact_error(exc) or type(exc).__name__
                )
                return ""
        finally:
            self._compiled_context.reset(token)

    async def _compile_turn_context(
        self,
        user_text: str,
        *,
        turn_evidence: str | None = None,
    ) -> CompiledConversationContext | None:
        self._last_success_model = None
        self._generation_attempts = []
        self._last_context_trace = {"status": "not_configured"}
        if self._context_compiler is None:
            return None
        try:
            conversation_id = str(self._get_conversation_id() or "conversation")
            turn_id = f"{conversation_id}:turn_{uuid4().hex[:12]}"
            compiled = await self._context_compiler.compile(
                user_text=user_text,
                author_instruction=_TASK_INSTRUCTION,
                turn_id=turn_id,
                turn_evidence=turn_evidence,
            )
            self._last_context_trace = {
                "status": "compiled",
                "conversation_id": compiled.conversation_id,
                "turn_id": compiled.turn_id,
                "reality_mode": compiled.reality_mode,
                "activated_lore": [
                    {
                        "uid": item.entry.uid,
                        "reason": item.reason,
                        "score": item.score,
                    }
                    for item in compiled.activated_lore
                ],
                "tool_evidence": bool(turn_evidence),
                "system_instruction_sha256": hashlib.sha256(
                    compiled.system_instruction.encode("utf-8")
                ).hexdigest(),
                "user_prompt_sha256": hashlib.sha256(
                    compiled.user_prompt.encode("utf-8")
                ).hexdigest(),
                "system_instruction_chars": len(compiled.system_instruction),
                "user_prompt_chars": len(compiled.user_prompt),
            }
            return compiled
        except Exception as exc:
            self._last_context_trace = {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": _compact_error(exc),
            }
            print(f"[THINKER] context compiler error: {_compact_error(exc)}")
            return None

    def _recent_assistant_messages(self) -> list[str]:
        try:
            provider = self._history_override.get() or self._get_history
            entries = provider(8) or []
        except Exception:
            return []
        result: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            sender = str(entry.get("sender") or "").strip().casefold()
            text = re.sub(r"\s+", " ", str(entry.get("text") or "")).strip()
            if text and sender not in _USER_SENDERS:
                result.append(text)
        return result[-4:]

    async def _revise_once(
        self,
        *,
        compiled: CompiledConversationContext,
        candidate: ResponseBrief,
        issues,
    ) -> str:
        model = self._last_success_model or THINKER_MODEL
        prompt = build_revision_prompt(
            original_prompt=compiled.user_prompt,
            candidate_reply=candidate.reply,
            issues=issues,
        )
        return await self._provider_generate(
            model=model,
            system_instruction=compiled.system_instruction,
            prompt=prompt,
            thinking_level_override="low",
        )

    def close(self) -> None:
        self._pending_voice_text = ""

    async def _generate(self, user_text: str) -> str:
        return await self._generate_on_model(user_text, THINKER_MODEL)

    async def _generate_on_model(self, user_text: str, model: str) -> str:
        compiled = self._compiled_context.get()
        prompt = compiled.user_prompt if compiled is not None else self._build_prompt(user_text)
        result = await self._provider_generate(
            model=model,
            system_instruction=(
                compiled.system_instruction
                if compiled is not None
                else f"{_load_card()}\n\n{_TASK_INSTRUCTION}"
            ),
            prompt=prompt,
        )
        self._last_success_model = model
        return result

    async def _provider_generate(
        self,
        *,
        model: str,
        system_instruction: str,
        prompt: str,
        thinking_level_override: str | None = None,
    ) -> str:
        if self._text_provider is None:
            self._text_provider = GeminiTextProvider(
                api_key=os.getenv("GEMINI_API_KEY")
            )
        config = self._config()
        is_gemini_3 = str(model).startswith("gemini-3")
        thinking_level = (
            str(
                thinking_level_override
                or config.get("thinking_level")
                or "medium"
            ).strip().lower()
            if is_gemini_3
            else None
        )
        if thinking_level not in {"minimal", "low", "medium", "high"}:
            thinking_level = "medium"
        legacy_budget = config.get("thinking_budget")
        thinking_budget = (
            int(legacy_budget)
            if legacy_budget is not None and not is_gemini_3
            else None
        )
        return await self._text_provider.generate(
            TextGenerationRequest(
                model=model,
                system_instruction=system_instruction,
                prompt=prompt,
                thinking_level=thinking_level,
                thinking_budget=thinking_budget,
            )
        )

    async def plan_tool_calls(
        self,
        user_text: str,
        *,
        tools: tuple[ConversationToolDefinition, ...],
        runtime_context: str = "",
    ) -> tuple[ConversationToolRequest, ...]:
        """Ask the text provider for structured calls; never execute them here."""
        if self._text_provider is None:
            self._text_provider = GeminiTextProvider(
                api_key=os.getenv("GEMINI_API_KEY")
            )
        planner = getattr(self._text_provider, "plan_tools", None)
        if planner is None:
            return ()
        prompt = str(user_text or "").strip()
        if runtime_context:
            prompt = (
                f"<runtime_context>{escape(runtime_context)}</runtime_context>\n"
                f"<current_user_turn>{escape(prompt)}</current_user_turn>"
            )
        else:
            prompt = f"<current_user_turn>{escape(prompt)}</current_user_turn>"
        return await planner(
            ToolPlanningRequest(
                model=THINKER_MODEL,
                system_instruction=(
                    "Jesteś planerem narzędzi, nie autorem odpowiedzi. "
                    "Wywołaj najwyżej jedno narzędzie tylko wtedy, gdy użytkownik "
                    "jawnie prosi o daną operację lub aktualny odczyt. Nie wywołuj "
                    "narzędzi dla luźnej rozmowy, hipotetycznych przykładów ani "
                    "negacji. Argumenty mają wiernie zachować intencję użytkownika."
                ),
                prompt=prompt,
                tools=tools,
            )
        )

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
