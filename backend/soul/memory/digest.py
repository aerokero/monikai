"""Session Digest — the heart of Monika's memory (v3, Phase A).

After a session ends, a local LLM creates history metadata: a title and recap.
It does not write durable memory or manufacture psychological state.

Sessions with no meaningful content produce NOTHING — selection is the
feature, not a bug. A session is marked in its meta.json (``digest`` key)
so it is never processed twice; trivial sessions are marked as skipped.

No LLM → no digest. We never fall back to heuristics.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from backend.llm.ollama_client import get_client

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
# A session needs at least this much user-authored text to be worth an LLM call.
_MIN_USER_CHARS = 120

# Don't digest a session whose last turn is newer than this — it may still be live.
_MIN_IDLE_SECONDS = 15 * 60

# Below this generation speed the GPU is clearly contended (game running,
# model spilled to CPU) — background digestion politely defers.
_MIN_TOKENS_PER_S = 15.0

# ---------------------------------------------------------------------------
# LLM output model
# ---------------------------------------------------------------------------

class SessionDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    significant: bool
    title: str = ""
    recap: str = ""


SYSTEM_PROMPT = """Tworzysz metadane historii rozmów Moniki i Bartka. Piszesz po polsku.

Rozmowy bywają głosowe — transkrypcja może zawierać błędy i urwane zdania; ignoruj szum.
Linie od nadawców "MC:<nick>" to czat z gry Minecraft — wspólne granie Moniki i Bartka;
wydarzenia z gry (wspólne budowy, wyprawy, zabawne momenty) są pełnoprawnymi wspomnieniami.
Masz tylko dwa zadania:
- TITLE: krótki tytuł rozmowy (3-6 słów, po polsku), konkretny — po nim Bartek pozna tę rozmowę na liście. Bez cudzysłowów i kropki.
- RECAP: 1-3 rzeczowe zdania o tym, czego dotyczyła rozmowa. Bez interpretowania psychiki rozmówców.

Jeśli rozmowa była pusta lub testowa, ustaw significant=false. Nie wyciągaj faktów do pamięci i nie twórz żadnych innych pól ani stanów."""

_PROMPT_TMPL = """Transkrypt rozmowy (kanał: {channel}, data: {date}):

{transcript}

Przetwórz tę rozmowę na wspomnienia zgodnie z zasadami."""

# Streams (Minecraft, Telegram): a whole day's continuous log, not a single
# conversation. Recap replaces the psychological read of one session.
SYSTEM_PROMPT_STREAM = """Tworzysz metadane historii całodziennego kanału Moniki i Bartka. Piszesz po polsku.

Linie od nadawców "MC:<nick>" to czat z gry Minecraft — wspólne granie Moniki i Bartka.
Log bywa chaotyczny i pełen szumu (komendy, krótkie okrzyki) — selekcja to twoja praca.
Masz tylko dwa zadania:
- TITLE: krótki tytuł dnia na tym kanale (3-6 słów, po polsku), konkretny. Bez cudzysłowów i kropki.
- RECAP: 1-3 rzeczowe zdania o tym, co wydarzyło się na kanale.

Jeśli dzień był pusty lub był szumem, ustaw significant=false."""

_PROMPT_TMPL_STREAM = """Całodzienny log kanału {channel} (data: {date}):

{transcript}

Przetwórz ten dzień na wspomnienia zgodnie z zasadami."""


# ---------------------------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------------------------

def load_transcript(session_dir: Path) -> tuple[str, int]:
    """Read turns.jsonl → ("Bartek: ...\\nMonika: ...", user_chars)."""
    turns_path = session_dir / "turns.jsonl"
    if not turns_path.exists():
        return "", 0

    lines: list[str] = []
    user_chars = 0
    for raw in turns_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        sender = entry.get("sender")
        if sender == "AI":
            lines.append(f"Monika: {text}")
        elif sender in ("User", None, ""):
            lines.append(f"Bartek: {text}")
            user_chars += len(text)
        else:
            # e.g. "MC:<nick>" — in-game Minecraft chat or other channels.
            lines.append(f"{sender}: {text}")
            user_chars += len(text)
    return "\n".join(lines), user_chars


def _last_turn_age_seconds(session_dir: Path) -> float:
    turns_path = session_dir / "turns.jsonl"
    if not turns_path.exists():
        return float("inf")
    return time.time() - turns_path.stat().st_mtime


def _read_meta(session_dir: Path) -> dict:
    meta_path = session_dir / "meta.json"
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _mark_digested(session_dir: Path, record: dict, title: str | None = None) -> None:
    meta_path = session_dir / "meta.json"
    meta = _read_meta(session_dir)
    meta["digest"] = record
    if title:
        meta["title"] = title
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# LLM call — JSON mode + pydantic validation
# ---------------------------------------------------------------------------

_JSON_MODE_HINT = """

Odpowiedz WYŁĄCZNIE poprawnym JSON-em o tej strukturze (bez markdown, bez komentarzy):
{"significant": bool, "title": str, "recap": str}"""

_JSON_MODE_HINT_STREAM = """

Odpowiedz WYŁĄCZNIE poprawnym JSON-em o tej strukturze (bez markdown, bez komentarzy):
{"significant": bool, "title": str, "recap": str}"""


async def _run_digest_llm(
    prompt: str, session_id: str, *, system: str = SYSTEM_PROMPT, hint: str = _JSON_MODE_HINT
) -> SessionDigest | None:
    """JSON-mode generation + pydantic validation, one corrective retry.

    Measured on this machine: schema-grammar decode 15+ min vs JSON mode 15 s
    for the same prompt — so full-schema grammars are off the table.
    """
    client = get_client()

    raw = await client.chat_json(
        prompt + hint, system=system,
        num_ctx=8192, temperature=0.2, timeout_s=300.0,
    )
    if raw is None:
        logger.warning("digest: %s failed (no LLM result) — will retry next scan", session_id)
        return None

    try:
        return SessionDigest.model_validate(raw)
    except ValidationError as exc:
        logger.info("digest: %s invalid JSON shape, one corrective retry", session_id)
        raw = await client.chat_json(
            prompt + hint
            + f"\n\nPoprzednia odpowiedź miała zły format ({exc.error_count()} błędów). "
              "Trzymaj się DOKŁADNIE podanej struktury.",
            system=system,
            num_ctx=8192, temperature=0.1, timeout_s=300.0,
        )
        if raw is None:
            return None
        try:
            return SessionDigest.model_validate(raw)
        except ValidationError as exc2:
            logger.warning("digest: %s still invalid after retry: %s", session_id, exc2)
            return None


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------

async def digest_session(
    session_dir: Path,
    db_path: Path | None = None,
    channel: str | None = None,
) -> SessionDigest | None:
    """Create conversation-history metadata without writing memory."""
    session_dir = Path(session_dir)
    session_id = session_dir.name

    meta = _read_meta(session_dir)
    is_stream = meta.get("kind") == "stream" or session_id.startswith("stream_")
    channel = channel or meta.get("channel") or "voice"

    transcript, user_chars = load_transcript(session_dir)
    if user_chars < _MIN_USER_CHARS:
        _mark_digested(session_dir, {
            "status": "skipped_trivial",
            "at": _utciso(),
            "user_chars": user_chars,
        })
        logger.info("digest: %s skipped (trivial, %d user chars)", session_id, user_chars)
        return None

    date = session_dir.parent.name
    if is_stream:
        prompt = _PROMPT_TMPL_STREAM.format(channel=channel, date=date, transcript=transcript)
        digest = await _run_digest_llm(
            prompt, session_id, system=SYSTEM_PROMPT_STREAM, hint=_JSON_MODE_HINT_STREAM
        )
    else:
        prompt = _PROMPT_TMPL.format(channel=channel, date=date, transcript=transcript)
        digest = await _run_digest_llm(prompt, session_id)
    if digest is None:
        return None

    # The significance decision is a hard storage boundary. Local models may
    # still return residual fields alongside significant=false.
    if not digest.significant:
        _mark_digested(
            session_dir,
            {
                "status": "skipped_insignificant",
                "at": _utciso(),
                "significant": False,
            },
            title=digest.title.strip() or None,
        )
        logger.info("digest: %s skipped (LLM marked insignificant)", session_id)
        return None

    record = {
        "status": "done",
        "at": _utciso(),
        "significant": digest.significant,
    }
    if digest.recap.strip():
        record["recap"] = digest.recap.strip()
    _mark_digested(session_dir, record, title=digest.title.strip() or None)
    logger.info(
        "digest: %s history metadata stored",
        session_id,
    )
    return digest


def _utciso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Scan — catch-up digestion of all pending sessions
# ---------------------------------------------------------------------------

async def scan_and_digest(
    sessions_root: Path | None = None,
    db_path: Path | None = None,
    current_session_id: str | None = None,
    max_sessions: int = 10,
) -> int:
    """Digest every not-yet-digested, inactive session. Returns digested count.

    Streams (stream_<channel> dirs) are only digested for PAST days — today's
    stream is still being written to ("nightly" recap without a scheduler).
    Safe to call repeatedly (startup + periodic timer). Failed sessions stay
    unmarked and are retried on the next scan.
    """
    root = sessions_root or (_DATA_DIR / "sessions")
    if not root.exists():
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    pending: list[Path] = []
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        for sess_dir in sorted(day_dir.iterdir()):
            if not sess_dir.is_dir():
                continue
            if sess_dir.name == current_session_id:
                continue
            if sess_dir.name.startswith("stream_") and day_dir.name >= today:
                continue
            if "digest" in _read_meta(sess_dir):
                continue
            if not (sess_dir / "turns.jsonl").exists():
                continue
            if _last_turn_age_seconds(sess_dir) < _MIN_IDLE_SECONDS:
                continue
            pending.append(sess_dir)

    untitled = _find_untitled(root, current_session_id) if not pending else []
    if not pending and not untitled:
        return 0

    client = get_client()
    health = await client.health()
    if not health["ok"] or not health["model_available"]:
        logger.warning("digest: Ollama unavailable, %d sessions pending", len(pending))
        return 0

    # Yield to whatever owns the GPU right now (a running game forces Ollama
    # into CPU offload and a digest would take tens of minutes).
    speed = await client.generation_speed()
    if speed is not None and speed < _MIN_TOKENS_PER_S:
        logger.info(
            "digest: GPU busy (%.1f tok/s < %.0f) — deferring %d pending session(s)",
            speed, _MIN_TOKENS_PER_S, len(pending),
        )
        return 0

    done = 0
    for sess_dir in pending[:max_sessions]:
        try:
            result = await digest_session(sess_dir, db_path=db_path)
            if result is not None or "digest" in _read_meta(sess_dir):
                done += 1
        except Exception as exc:
            logger.warning("digest: %s crashed: %s", sess_dir.name, exc)
    if pending:
        logger.info("digest: scan complete — %d/%d sessions processed", done, len(pending))

    # Idle scans (nothing to digest) top up titles of legacy sessions that
    # were digested before titles existed (Phase G backfill).
    if untitled:
        titled = await backfill_titles(untitled)
        if titled:
            logger.info("digest: backfilled %d session title(s)", titled)
    return done


# ---------------------------------------------------------------------------
# Title backfill — legacy sessions digested before titles existed (Phase G)
# ---------------------------------------------------------------------------

_TITLE_BACKFILL_PER_SCAN = 5
_TITLE_TRANSCRIPT_CHARS = 3000

_TITLE_SYSTEM = (
    "Nadajesz tytuły zapisanym rozmowom Moniki (AI-kompanki) z Bartkiem. "
    "Tytuł: 3-6 słów, po polsku, konkretny — po nim można poznać rozmowę na liście. "
    "Bez cudzysłowów i kropki na końcu."
)


def _find_untitled(root: Path, current_session_id: str | None) -> list[Path]:
    """Sessions already digested as significant but lacking a title."""
    found: list[Path] = []
    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        for sess_dir in sorted(day_dir.iterdir(), reverse=True):
            if not sess_dir.is_dir() or sess_dir.name == current_session_id:
                continue
            meta = _read_meta(sess_dir)
            if meta.get("title"):
                continue
            digest = meta.get("digest") or {}
            if digest.get("status") != "done":
                continue
            if not (sess_dir / "turns.jsonl").exists():
                continue
            found.append(sess_dir)
            if len(found) >= _TITLE_BACKFILL_PER_SCAN:
                return found
    return found


async def backfill_titles(session_dirs: list[Path]) -> int:
    """Generate titles for already-digested sessions. Returns titled count."""
    client = get_client()
    titled = 0
    for sess_dir in session_dirs:
        transcript, _ = load_transcript(sess_dir)
        if not transcript:
            continue
        prompt = (
            f"Rozmowa:\n\n{transcript[:_TITLE_TRANSCRIPT_CHARS]}\n\n"
            'Nadaj tytuł. Odpowiedz WYŁĄCZNIE JSON-em: {"title": str}'
        )
        try:
            raw = await client.chat_json(
                prompt, system=_TITLE_SYSTEM,
                num_ctx=4096, temperature=0.2, timeout_s=120.0,
            )
        except Exception as exc:
            logger.debug("digest: title backfill LLM error for %s: %s", sess_dir.name, exc)
            continue
        title = str((raw or {}).get("title") or "").strip().strip('"')
        if not title:
            continue
        meta_path = sess_dir / "meta.json"
        meta = _read_meta(sess_dir)
        meta["title"] = title[:120]
        try:
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            titled += 1
        except Exception as exc:
            logger.debug("digest: title write failed for %s: %s", sess_dir.name, exc)
    return titled
