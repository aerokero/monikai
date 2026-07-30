"""Deterministic pre-voice checks for common conversational failures."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import escape


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    guidance: str
    severity: str = "rewrite"


@dataclass(frozen=True)
class ValidationResult:
    issues: list[ValidationIssue]

    @property
    def needs_rewrite(self) -> bool:
        return any(issue.severity == "rewrite" for issue in self.issues)


_MEMORY_CLAIM_RE = re.compile(
    r"\b(zapisz[ęe]|zapisuj[ęe]|zapami[ęe]tam|zapisałam|dodałam do pamięci)\b",
    re.IGNORECASE,
)
_MEMORY_REQUEST_RE = re.compile(
    r"\b(zapisz|zapamiętaj|dodaj do pamięci)\b",
    re.IGNORECASE,
)
_UNCERTAIN_USER_RE = re.compile(
    r"\b(nie wiem|w sumie nie wiem|chyba|tak po prostu|jakoś)\b",
    re.IGNORECASE,
)
_INFLATION_RE = re.compile(
    r"\b("
    r"naturaln(?:a|ą) zdolno(?:ść|ścią)|"
    r"cenna cecha|rzadkość|rzadk(?:i|a|ie|ą|iego|im)\s+"
    r"(?:komfort|dar|talent|cech\w*|zdolno\w*|umiejętno\w*|ustawieni\w*)|"
    r"stabiln(?:y|e) punkt|"
    r"masz w sobie|"
    r"to wiele mówi o tobie|"
    r"fabryczn\w+(?:\s+\w+){0,4}\s+(?:wgran\w*|ustawieni\w*|zaprogramowan\w*)|"
    r"(?:można|pozostaje)\s+(?:ci\s+)?tylko\s+pozazdrościć|"
    r"tylko\s+pozazdrościć|"
    r"oszczędza\w*(?:\s+\w+){0,3}\s+energii"
    r"|wi[ęe]kszo[śs][ćc]\s+ludzi|nie\s+ka[żz]dy\s+tak"
    r"|luksus|rutyn\w*"
    r")\b",
    re.IGNORECASE,
)
_UNSOLICITED_ADVICE_RE = re.compile(
    r"\b(odpocznij|zrób sobie przerwę|powinieneś|powinnaś)\b",
    re.IGNORECASE,
)
_MUNDANE_INVENTION_RE = re.compile(
    r"\b(narzędzie przetrwania|nie element przyjemności|"
    r"przetrwa\w*\s+(?:biur|prac)\w*)\b",
    re.IGNORECASE,
)
_AUTO_BUFFER_RE = re.compile(
    r"^\s*(rozumiem|to ciekawe|aha,?\s+czyli|jasne,?\s+czyli)\b",
    re.IGNORECASE,
)
_USER_QUESTION_RE = re.compile(r"\?\s*$")
_SIMPLE_STATUS_RE = re.compile(
    r"\b(jestem w pracy|pracuj[ęe]|ca[łl]kiem spoko|u mnie spoko)\b",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip().casefold()
    return re.sub(r"[^\wąćęłńóśźż ]+", "", value)


def _similarity(left: str, right: str) -> float:
    a, b = _normalise(left), _normalise(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class ConversationResponseValidator:
    def validate(
        self,
        *,
        user_text: str,
        reply: str,
        recent_assistant_messages: list[str] | None = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        recent = [
            str(message or "").strip()
            for message in (recent_assistant_messages or [])
            if str(message or "").strip()
        ]
        user_asked_question = bool(_USER_QUESTION_RE.search(user_text.strip()))

        if _MEMORY_CLAIM_RE.search(reply) and not _MEMORY_REQUEST_RE.search(user_text):
            issues.append(
                ValidationIssue(
                    "unsolicited_memory_claim",
                    "Usuń deklarację zapisywania lub zapamiętywania. Po prostu odpowiedz.",
                )
            )

        if (
            "?" in reply
            and _UNCERTAIN_USER_RE.search(user_text)
            and not user_asked_question
        ):
            issues.append(
                ValidationIssue(
                    "question_after_uncertainty",
                    "Rozmówca powiedział, że nie wie. Nie przepytuj go dalej; "
                    "wnieś krótki konkret albo pozwól tematowi się domknąć.",
                )
            )

        if (
            "?" in reply
            and not user_asked_question
            and _SIMPLE_STATUS_RE.search(user_text)
        ):
            issues.append(
                ValidationIssue(
                    "unnecessary_question",
                    "To zwykły krótki status, nie zaproszenie do wywiadu. "
                    "Zareaguj krótko bez otwierania kolejnego pytania.",
                )
            )

        if _UNCERTAIN_USER_RE.search(user_text) and _INFLATION_RE.search(reply):
            issues.append(
                ValidationIssue(
                    "psychological_inflation",
                    "Nie rób z niepewnej, zwyczajnej wypowiedzi trwałej cechy, "
                    "rzadkiego talentu ani psychologicznego odkrycia.",
                )
            )

        if not user_asked_question and _UNSOLICITED_ADVICE_RE.search(reply):
            issues.append(
                ValidationIssue(
                    "unsolicited_advice",
                    "Rozmówca nie prosił o radę. Zareaguj na to, co powiedział, "
                    "bez pouczania go, co ma teraz zrobić.",
                )
            )

        if "kaw" in user_text.casefold() and _MUNDANE_INVENTION_RE.search(reply):
            issues.append(
                ValidationIssue(
                    "unsupported_elaboration",
                    "Nie dopisuj powodów, emocji ani dramatycznej ramy do "
                    "zwykłej informacji o kawie.",
                )
            )

        if recent:
            closest = max((_similarity(reply, message) for message in recent[-4:]), default=0.0)
            if closest >= 0.82:
                issues.append(
                    ValidationIssue(
                        "repeated_response",
                        "Odpowiedź powtarza niedawną wypowiedź Moniki. Zareaguj "
                        "krócej z nowego kąta albo zakończ temat.",
                    )
                )

            recent_questions = sum("?" in message for message in recent[-3:])
            if "?" in reply and recent_questions >= 2 and not user_asked_question:
                issues.append(
                    ValidationIssue(
                        "question_pressure",
                        "Monika zadała już pytania w co najmniej dwóch z trzech "
                        "ostatnich odpowiedzi. Tym razem odpowiedz bez pytania.",
                    )
                )

            if (
                _AUTO_BUFFER_RE.search(reply)
                and sum(bool(_AUTO_BUFFER_RE.search(message)) for message in recent[-3:]) >= 1
            ):
                issues.append(
                    ValidationIssue(
                        "repeated_acknowledgement",
                        "Nie zaczynaj ponownie od automatycznej parafrazy typu "
                        "„rozumiem” albo „aha, czyli”.",
                    )
                )

        return ValidationResult(issues)


def build_revision_prompt(
    *,
    original_prompt: str,
    candidate_reply: str,
    issues: list[ValidationIssue],
) -> str:
    guidance = "\n".join(f"- {issue.code}: {issue.guidance}" for issue in issues)
    return (
        f"{original_prompt}\n\n"
        "<revision_request>\n"
        "Poprzedni kandydat odpowiedzi nie przeszedł kontroli jakości:\n"
        f"<candidate_reply>{escape(candidate_reply)}</candidate_reply>\n"
        f"{guidance}\n"
        "Napisz odpowiedź ponownie. Zachowaj cel rozmówcy, ale usuń wskazane "
        "problemy. Zwróć ponownie dokładnie <analysis> i <reply>.\n"
        "</revision_request>"
    )
