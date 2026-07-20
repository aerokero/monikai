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
import json
from pathlib import Path
import re
import sys
from typing import Any

import socketio


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = ROOT / "scripts" / "scenarios" / "reasoning_smoke.json"
DEFAULT_REPORT = ROOT / "tmp" / "conversation_probe.md"

_WORD_RE = re.compile(r"[0-9a-ząćęłńóśźż]+", re.IGNORECASE)
_STOPWORDS = {
    "a", "ale", "bo", "być", "ci", "co", "czy", "do", "i", "jak", "jest",
    "mi", "na", "nie", "o", "się", "to", "w", "z", "że", "ten", "ta", "te",
    "the", "a", "an", "and", "is", "of", "to",
}
_QUESTION_WORDS = {"czy", "co", "jak", "kto", "komu", "czemu", "dlaczego", "gdzie", "kiedy", "z kim"}


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


def evaluate_turn(turn: dict[str, Any], trace: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    thinker = trace.get("thinker") if isinstance(trace.get("thinker"), dict) else {}
    core = str(thinker.get("reply_core") or "")
    response = str(trace.get("response") or "")
    expected = turn.get("expect") if isinstance(turn.get("expect"), dict) else {}

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("live_response", bool(response), "finalna transkrypcja odpowiedzi")
    add("brief_ready", thinker.get("status") == "ready", f"status={thinker.get('status', 'missing')}")
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
    return checks


def render_report(scenario: dict[str, Any], results: list[dict[str, Any]]) -> str:
    passed = sum(1 for result in results for check in result["checks"] if check["passed"])
    total = sum(len(result["checks"]) for result in results)
    lines = [
        f"# Conversation probe — {scenario.get('name', 'unnamed')}",
        "",
        f"- Czas: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Wynik: **{passed}/{total} checks passed**",
        "",
    ]
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


async def run(args: argparse.Namespace) -> int:
    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    turns = scenario.get("turns") or []
    if not isinstance(turns, list) or not turns:
        raise ValueError("scenario must contain a non-empty 'turns' list")

    client = socketio.AsyncClient(reconnection=False, logger=False, engineio_logger=False)
    await client.connect(args.url, wait_timeout=8)
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
            text = str((turn or {}).get("text") or "").strip()
            print(f"[{index}/{len(turns)}] Ty: {text}")
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
            checks = evaluate_turn(turn, trace)
            results.append({"turn": turn, "trace": trace, "checks": checks})
            print(f"      Monika: {trace.get('response') or '[brak odpowiedzi]'}")
            if not trace.get("ok"):
                print(f"      ERROR: {trace.get('error', 'unknown error')}")
    finally:
        if started_session and args.stop_after:
            await client.emit("stop_audio")
            await asyncio.sleep(0.2)
        await client.disconnect()

    report = render_report(scenario, results)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    failed = sum(1 for result in results for check in result["checks"] if not check["passed"])
    print(f"\nRaport: {report_path}")
    print(f"Wynik: {'PASS' if failed == 0 else 'FAIL'} ({failed} nieudanych kontroli)")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
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
