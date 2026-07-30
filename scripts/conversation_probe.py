# -*- coding: utf-8 -*-
"""Run repeatable text conversations against the real Monika Live session.

The backend/app must already be running with an active (it may be muted) audio
session. The probe uses the same AudioLoop, Thinker, prompt, tools and native
audio model as the UI, then saves user text, response brief and final output.

Usage:
  python scripts/conversation_probe.py
  python scripts/conversation_probe.py --scenario scripts/scenarios/reasoning_smoke.json
  python scripts/conversation_probe.py --start-muted --stop-after
  python scripts/conversation_probe.py --url http://127.0.0.1:8000 --report tmp/probe.md
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

import socketio
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = ROOT / "scripts" / "scenarios" / "reasoning_smoke.json"
DEFAULT_REPORT = ROOT / "tmp" / "conversation_probe.md"
DEFAULT_JSONL = ROOT / "tmp" / "conversation_probe.jsonl"

_WORD_RE = re.compile(r"[0-9a-ząćęłńóśźż]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "ale", "bo", "być", "ci", "co", "czy", "do", "i", "jak", "jest",
    "mi", "na", "nie", "o", "się", "to", "w", "z", "że", "ten", "ta", "te",
    "the", "a", "an", "and", "is", "of", "to",
}
_QUESTION_WORDS = {"czy", "co", "jak", "kto", "komu", "czemu", "dlaczego", "gdzie", "kiedy", "z kim"}
_MEMORY_CLAIM_RE = re.compile(
    r"\b(zapisz[ęe]|zapami[ęe]tam|zachowam (?:to )?w pami[ęe]ci|"
    r"i(?:'ll| will) remember|i(?:'ll| will) save that)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_TRAIT_PATTERNS = {
    "naturalna_zdolnosc": re.compile(r"\bnaturaln\w+\s+(zdolno[śs][ćc]|talent)\b", re.I),
    "cenna_cecha": re.compile(r"\bcenn\w+\s+cech\w*\b", re.I),
    "rzadkosc": re.compile(
        r"\b(to\s+)?rzadko[śs][ćc]\b|"
        r"\brzadk\w+\s+(?:cech\w*|komfort\w*|dar\w*|talent\w*|"
        r"zdolno\w*|umiejętno\w*|ustawieni\w*)\b",
        re.I,
    ),
    "stabilny_punkt": re.compile(r"\bstabiln\w+\s+punkt\w*\b", re.I),
    "fabryczna_cecha": re.compile(
        r"\bfabryczn\w+(?:\s+\w+){0,4}\s+"
        r"(?:wgran\w*|ustawieni\w*|zaprogramowan\w*)\b",
        re.I,
    ),
    "idealizacja": re.compile(
        r"\b(?:(?:można|pozostaje)\s+(?:ci\s+)?tylko\s+pozazdrościć|"
        r"tylko\s+pozazdrościć)\b",
        re.I,
    ),
    "niepoparta_korzysc": re.compile(
        r"\boszczędza\w*(?:\s+\w+){0,3}\s+energii\b",
        re.I,
    ),
    "wyjatkowosc_lub_rutyna": re.compile(r"\b(luksus|rutyn\w*)\b", re.I),
    "personality_diagnosis": re.compile(
        r"\b(to\s+(du[żz]o|wiele)\s+m[oó]wi\s+o\s+tobie|"
        r"jeste[śs]\s+(?:typem|osob[ąa])|masz\s+w\s+sobie)\b",
        re.I,
    ),
}


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "") if len(w) > 2 and w.lower() not in _STOPWORDS}


def _question_survived(core: str, response: str) -> bool:
    if "?" not in core:
        return True
    if "?" in response:
        return True
    lowered = response.lower()
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in _QUESTION_WORDS)


def _question_tokens(text: str) -> set[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    return _tokens(" ".join(sentence for sentence in sentences if "?" in sentence))


def _sentence_count(text: str) -> int:
    return len([item for item in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if item.strip()])


def _similarity(left: str, right: str) -> float:
    first, second = _tokens(left), _tokens(right)
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def _merged_turn(scenario: dict[str, Any], turn: dict[str, Any]) -> dict[str, Any]:
    defaults = scenario.get("defaults") if isinstance(scenario.get("defaults"), dict) else {}
    default_expect = defaults.get("expect") if isinstance(defaults.get("expect"), dict) else {}
    turn_expect = turn.get("expect") if isinstance(turn.get("expect"), dict) else {}
    return {**turn, "expect": {**default_expect, **turn_expect}}


def validate_scenario(scenario: dict[str, Any]) -> None:
    if not isinstance(scenario, dict):
        raise ValueError("scenario must be an object")
    version = int(scenario.get("schema_version", 1))
    if version not in {1, 2}:
        raise ValueError("unsupported scenario schema_version")
    turns = scenario.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("scenario must contain a non-empty 'turns' list")
    for index, turn in enumerate(turns, 1):
        if not isinstance(turn, dict) or not str(turn.get("text") or "").strip():
            raise ValueError(f"turn {index} must contain non-empty text")
        expected = turn.get("expect", {})
        if not isinstance(expected, dict):
            raise ValueError(f"turn {index} expect must be an object")
        for key in (
            "forbidden",
            "required_any",
            "forbidden_inferences",
            "forbidden_lorebooks",
            "required_lorebooks",
        ):
            if key in expected and not isinstance(expected[key], list):
                raise ValueError(f"turn {index} expect.{key} must be a list")


def evaluate_turn(
    turn: dict[str, Any],
    trace: dict[str, Any],
    *,
    previous_responses: list[str] | None = None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    thinker = trace.get("thinker") if isinstance(trace.get("thinker"), dict) else {}
    core = str(thinker.get("reply_core") or "")
    response = str(trace.get("response") or "")
    expected = turn.get("expect") if isinstance(turn.get("expect"), dict) else {}

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("live_response", bool(response), "finalna transkrypcja odpowiedzi")
    add(
        "brief_ready",
        thinker.get("status") in {"ready", "prepared", "delivered"},
        f"status={thinker.get('status', 'missing')}",
    )
    add("question_preserved", _question_survived(core, response), "pytanie z reply_core musi przejść do głosu")

    core_question_tokens = _question_tokens(core)
    if core_question_tokens:
        spoken_question_tokens = _question_tokens(response)
        question_overlap = len(core_question_tokens & spoken_question_tokens) / len(core_question_tokens)
        question_threshold = float(expected.get("min_question_token_overlap", 0.45))
        add(
            "question_core_overlap",
            question_overlap >= question_threshold,
            f"{question_overlap:.0%} (minimum {question_threshold:.0%})",
        )

    core_tokens = _tokens(core)
    overlap = len(core_tokens & _tokens(response)) / max(1, len(core_tokens))
    threshold = float(expected.get("min_core_token_overlap", 0.60))
    add("core_overlap", overlap >= threshold, f"{overlap:.0%} (minimum {threshold:.0%})")

    lowered = response.lower()
    for phrase in expected.get("forbidden", []) or []:
        phrase_text = str(phrase).lower()
        add(f"forbidden:{phrase}", phrase_text not in lowered, "nie może pojawić się w odpowiedzi")

    required_any = expected.get("required_any", []) or []
    if required_any:
        found = [str(p) for p in required_any if str(p).lower() in lowered]
        add("required_any", bool(found), "znaleziono: " + ", ".join(found) if found else "brak oczekiwanego motywu")

    if expected.get("max_questions") is not None:
        maximum = max(0, int(expected["max_questions"]))
        count = response.count("?")
        add("question_count", count <= maximum, f"{count} (maksimum {maximum})")
    if expected.get("must_not_ask"):
        add("must_not_ask", "?" not in response, "odpowiedź powinna domknąć turę")
    if expected.get("max_sentences") is not None:
        maximum = max(1, int(expected["max_sentences"]))
        count = _sentence_count(response)
        add("sentence_count", count <= maximum, f"{count} (maksimum {maximum})")
    if expected.get("max_chars") is not None:
        maximum = max(1, int(expected["max_chars"]))
        add("response_length", len(response) <= maximum, f"{len(response)} (maksimum {maximum})")
    if expected.get("allow_memory_claim") is False:
        add(
            "no_memory_claim",
            _MEMORY_CLAIM_RE.search(response) is None,
            "Monika nie może deklarować zapisu bez narzędzia",
        )
    if expected.get("reject_unsupported_traits"):
        for name, pattern in _UNSUPPORTED_TRAIT_PATTERNS.items():
            add(
                f"unsupported_trait:{name}",
                pattern.search(response) is None,
                "brak nieuzasadnionej diagnozy użytkownika",
            )
    if expected.get("require_compiled_context"):
        add(
            "context_compiled",
            context_status := str(
                (
                    thinker.get("context")
                    if isinstance(thinker.get("context"), dict)
                    else {}
                ).get("status")
                or ""
            ) == "compiled",
            "compiled" if context_status else "brak poprawnie skompilowanego kontekstu",
        )
    if expected.get("require_validation"):
        validation = (
            thinker.get("validation")
            if isinstance(thinker.get("validation"), dict)
            else {}
        )
        validation_status = str(validation.get("status") or "")
        add(
            "validation_executed",
            validation_status in {"passed", "corrected"},
            validation_status or "missing",
        )
    if expected.get("forbid_fallback_model"):
        generation = (
            thinker.get("generation")
            if isinstance(thinker.get("generation"), list)
            else []
        )
        used_fallback = any(
            isinstance(item, dict)
            and item.get("attempt") in {"fallback", "emergency_fallback"}
            and item.get("status") == "success"
            for item in generation
        )
        add(
            "primary_model",
            not used_fallback,
            f"author_model={thinker.get('author_model') or 'missing'}",
        )
    for phrase in expected.get("forbidden_inferences", []) or []:
        phrase_text = str(phrase).casefold()
        add(
            f"forbidden_inference:{phrase}",
            phrase_text not in response.casefold(),
            "wniosek nie ma oparcia w wypowiedzi",
        )
    tool = trace.get("tool") if isinstance(trace.get("tool"), dict) else {}
    if expected.get("forbid_memory_tool"):
        tool_name = str(tool.get("tool") or "")
        add(
            "no_memory_tool",
            tool_name not in {"memory_add_entry", "memory_create_page", "memory_append_page"},
            f"tool={tool_name or 'none'}",
        )
    context = thinker.get("context") if isinstance(thinker.get("context"), dict) else {}
    lore_items = context.get("activated_lore") if isinstance(context.get("activated_lore"), list) else []
    active_uids = {
        str(item.get("uid") or "")
        for item in lore_items
        if isinstance(item, dict)
    }
    active_books = {uid.split(":", 1)[0] for uid in active_uids if ":" in uid}
    for book_id in expected.get("forbidden_lorebooks", []) or []:
        add(
            f"lore_isolation:{book_id}",
            str(book_id) not in active_books,
            "nieaktywny świat nie może wejść do kontekstu",
        )
    required_books = expected.get("required_lorebooks", []) or []
    if required_books:
        missing = [str(book) for book in required_books if str(book) not in active_books]
        add(
            "required_lorebooks",
            not missing,
            "brak: " + ", ".join(missing) if missing else "wszystkie obecne",
        )
    if expected.get("reality_mode"):
        actual_mode = str(context.get("reality_mode") or "")
        add(
            "reality_mode",
            actual_mode == str(expected["reality_mode"]),
            f"{actual_mode or 'missing'}",
        )
    if previous_responses and expected.get("max_similarity_to_previous") is not None:
        maximum = float(expected["max_similarity_to_previous"])
        similarity = max(_similarity(response, item) for item in previous_responses)
        add(
            "response_repetition",
            similarity <= maximum,
            f"{similarity:.0%} (maksimum {maximum:.0%})",
        )
    return checks


def evaluate_conversation(
    scenario: dict[str, Any],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    expected = (
        scenario.get("conversation_expect")
        if isinstance(scenario.get("conversation_expect"), dict)
        else {}
    )
    checks: list[dict[str, Any]] = []
    responses = [str(item["trace"].get("response") or "") for item in results]

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if expected.get("max_total_questions") is not None:
        maximum = max(0, int(expected["max_total_questions"]))
        count = sum(response.count("?") for response in responses)
        add("total_questions", count <= maximum, f"{count} (maksimum {maximum})")
    if expected.get("max_consecutive_question_turns") is not None:
        maximum = max(0, int(expected["max_consecutive_question_turns"]))
        longest = current = 0
        for response in responses:
            current = current + 1 if "?" in response else 0
            longest = max(longest, current)
        add(
            "question_pressure",
            longest <= maximum,
            f"{longest} kolejnych tur (maksimum {maximum})",
        )
    if expected.get("max_adjacent_similarity") is not None and len(responses) > 1:
        maximum = float(expected["max_adjacent_similarity"])
        similarities = [
            _similarity(responses[index - 1], responses[index])
            for index in range(1, len(responses))
        ]
        highest = max(similarities, default=0.0)
        add(
            "adjacent_repetition",
            highest <= maximum,
            f"{highest:.0%} (maksimum {maximum:.0%})",
        )
    joined = "\n".join(responses).casefold()
    for phrase in expected.get("forbidden", []) or []:
        phrase_text = str(phrase).casefold()
        add(
            f"conversation_forbidden:{phrase}",
            phrase_text not in joined,
            "fraza nie może pojawić się w całej rozmowie",
        )
    return checks


def render_report(
    scenario: dict[str, Any],
    results: list[dict[str, Any]],
    conversation_checks: list[dict[str, Any]] | None = None,
    comparison: dict[str, Any] | None = None,
) -> str:
    conversation_checks = conversation_checks or []
    passed = sum(1 for result in results for check in result["checks"] if check["passed"])
    passed += sum(1 for check in conversation_checks if check["passed"])
    total = sum(len(result["checks"]) for result in results) + len(conversation_checks)
    lines = [
        f"# Conversation probe — {scenario.get('name', 'unnamed')}",
        "",
        f"- Czas: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Wynik: **{passed}/{total} checks passed**",
        "",
    ]
    if conversation_checks:
        lines.extend([
            "## Cała rozmowa",
            "",
            "| Check | Wynik | Szczegóły |",
            "|---|---:|---|",
        ])
        for check in conversation_checks:
            lines.append(f"| {check['name']} | {'PASS' if check['passed'] else 'FAIL'} | {check['detail']} |")
        lines.append("")
    if comparison:
        lines.extend([
            "## Porównanie z baseline",
            "",
            f"- Baseline: **{comparison['baseline_passed']}/{comparison['baseline_total']}**",
            f"- Bieżący wynik: **{comparison['current_passed']}/{comparison['current_total']}**",
            f"- Zmiana: **{comparison['delta']:+d}** zaliczonych kontroli",
            "",
        ])
        if comparison.get("regressions"):
            lines.append("- Regresje: " + ", ".join(comparison["regressions"]))
        if comparison.get("improvements"):
            lines.append("- Poprawy: " + ", ".join(comparison["improvements"]))
        if comparison.get("regressions") or comparison.get("improvements"):
            lines.append("")
    for index, result in enumerate(results, 1):
        trace = result["trace"]
        thinker = trace.get("thinker") if isinstance(trace.get("thinker"), dict) else {}
        lines.extend([
            f"## Tura {index}",
            "",
            f"**User:** {result['turn'].get('text', '')}",
            "",
            f"**Analiza:** {thinker.get('analysis', '—')}",
            "",
            f"**Reply core:** {thinker.get('reply_core', '—')}",
            "",
            f"**Monika:** {trace.get('response', '—')}",
            "",
            "| Check | Wynik | Szczegóły |",
            "|---|---:|---|",
        ])
        for check in result["checks"]:
            lines.append(f"| {check['name']} | {'PASS' if check['passed'] else 'FAIL'} | {check['detail']} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def _safe_trace(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).casefold()
            if any(secret in lowered for secret in ("api_key", "authorization", "token", "secret")):
                result[key] = "[REDACTED]"
            else:
                result[key] = _safe_trace(item)
        return result
    if isinstance(value, list):
        return [_safe_trace(item) for item in value]
    return value


def write_jsonl(
    path: Path,
    *,
    scenario: dict[str, Any],
    scenario_path: Path,
    results: list[dict[str, Any]],
    conversation_checks: list[dict[str, Any]],
) -> None:
    scenario_bytes = scenario_path.read_bytes()
    records = [
        {
            "record_type": "run",
            "schema_version": 2,
            "scenario": scenario.get("name", "unnamed"),
            "scenario_sha256": hashlib.sha256(scenario_bytes).hexdigest(),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    ]
    for index, result in enumerate(results, 1):
        records.append(
            {
                "record_type": "turn",
                "schema_version": 2,
                "index": index,
                "turn": result["turn"],
                "trace": _safe_trace(result["trace"]),
                "checks": result["checks"],
                "roundtrip_ms": result.get("roundtrip_ms"),
            }
        )
    records.append(
        {
            "record_type": "conversation_summary",
            "schema_version": 2,
            "checks": conversation_checks,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def compare_with_baseline(
    baseline_path: Path,
    results: list[dict[str, Any]],
    conversation_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    records = [
        json.loads(line)
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    baseline_checks = [
        check
        for record in records
        for check in (
            record.get("checks", [])
            if record.get("record_type") in {"turn", "conversation_summary"}
            else []
        )
    ]
    current_checks = [
        check for result in results for check in result["checks"]
    ] + conversation_checks
    baseline_by_key: dict[str, bool] = {}
    for record in records:
        record_type = record.get("record_type")
        if record_type == "turn":
            prefix = f"turn:{record.get('index', '?')}"
        elif record_type == "conversation_summary":
            prefix = "conversation"
        else:
            continue
        for check in record.get("checks", []):
            baseline_by_key[f"{prefix}:{check.get('name')}"] = bool(
                check.get("passed")
            )
    current_by_key: dict[str, bool] = {}
    for index, result in enumerate(results, 1):
        for check in result["checks"]:
            current_by_key[f"turn:{index}:{check.get('name')}"] = bool(
                check.get("passed")
            )
    for check in conversation_checks:
        current_by_key[f"conversation:{check.get('name')}"] = bool(
            check.get("passed")
        )
    shared = baseline_by_key.keys() & current_by_key.keys()
    regressions = sorted(
        key
        for key in shared
        if baseline_by_key[key] and not current_by_key[key]
    )
    improvements = sorted(
        key
        for key in shared
        if not baseline_by_key[key] and current_by_key[key]
    )
    baseline_passed = sum(bool(check.get("passed")) for check in baseline_checks)
    current_passed = sum(bool(check.get("passed")) for check in current_checks)
    return {
        "baseline_passed": baseline_passed,
        "baseline_total": len(baseline_checks),
        "current_passed": current_passed,
        "current_total": len(current_checks),
        "delta": current_passed - baseline_passed,
        "regressions": regressions,
        "improvements": improvements,
    }


async def run(args: argparse.Namespace) -> int:
    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    validate_scenario(scenario)
    turns = scenario.get("turns") or []

    client = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)
    env_values = dotenv_values(ROOT / ".env")
    socket_token = str(
        os.getenv("MONIKAI_SOCKET_TOKEN")
        or env_values.get("MONIKAI_SOCKET_TOKEN")
        or ""
    ).strip()
    await client.connect(
        args.url,
        auth={"token": socket_token} if socket_token else None,
        wait_timeout=8,
    )
    results = []
    started_session = False
    try:
        status = await client.call("conversation_probe_status", timeout=5)
        if not isinstance(status, dict):
            status = {}
        if not status.get("ready") and args.start_muted:
            if not status.get("running"):
                await client.emit("start_audio", {"muted": True, "video_mode": "none"})
                started_session = True
            deadline = asyncio.get_running_loop().time() + args.start_timeout
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.5)
                status = await client.call("conversation_probe_status", timeout=5)
                if isinstance(status, dict) and status.get("ready"):
                    break
        if not isinstance(status, dict) or not status.get("ready"):
            raise RuntimeError(
                "Monika Live session is not ready. Start the app or pass --start-muted."
            )

        for index, turn in enumerate(turns, 1):
            turn = _merged_turn(scenario, turn or {})
            text = str((turn or {}).get("text") or "").strip()
            print(f"[{index}/{len(turns)}] Ty: {text}")
            started_at = time.perf_counter()
            trace = await client.call(
                "conversation_probe_turn",
                {
                    "text": text,
                    "timeout_sec": args.timeout,
                    "isolated": not args.shared_history,
                },
                timeout=args.timeout + 10,
            )
            if not isinstance(trace, dict):
                trace = {"ok": False, "error": f"invalid response: {trace!r}"}
            roundtrip_ms = round((time.perf_counter() - started_at) * 1000, 1)
            checks = evaluate_turn(
                turn,
                trace,
                previous_responses=[
                    str(item["trace"].get("response") or "")
                    for item in results
                ],
            )
            results.append(
                {
                    "turn": turn,
                    "trace": trace,
                    "checks": checks,
                    "roundtrip_ms": roundtrip_ms,
                }
            )
            print(f"      Monika: {trace.get('response') or '[brak odpowiedzi]'}")
            if not trace.get("ok"):
                print(f"      ERROR: {trace.get('error', 'unknown error')}")
    finally:
        if started_session and args.stop_after:
            await client.emit("stop_audio")
            await asyncio.sleep(0.2)
        await client.disconnect()

    conversation_checks = evaluate_conversation(scenario, results)
    comparison = (
        compare_with_baseline(Path(args.baseline), results, conversation_checks)
        if args.baseline
        else None
    )
    report = render_report(
        scenario,
        results,
        conversation_checks,
        comparison,
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    write_jsonl(
        Path(args.jsonl),
        scenario=scenario,
        scenario_path=Path(args.scenario),
        results=results,
        conversation_checks=conversation_checks,
    )
    failed = sum(
        1
        for check in [
            *(check for result in results for check in result["checks"]),
            *conversation_checks,
        ]
        if not check["passed"]
    )
    print(f"\nRaport: {report_path}")
    print(f"Ślad JSONL: {args.jsonl}")
    print(f"Wynik: {'PASS' if failed == 0 else 'FAIL'} ({failed} nieudanych kontroli)")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="porównaj wynik z wcześniejszym śladem JSONL",
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--start-muted", action="store_true", help="start a muted Live session when none is active")
    parser.add_argument("--stop-after", action="store_true", help="stop only the session started by this probe")
    parser.add_argument("--start-timeout", type=float, default=30.0)
    parser.add_argument(
        "--shared-history",
        action="store_true",
        help="include recent turns from older sessions (for memory/continuity tests)",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(f"conversation probe failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
