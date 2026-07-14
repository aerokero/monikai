"""Session Digest — the heart of Monika's memory (v3, Phase A).

After a session ends, the full transcript is processed by a local LLM
(Ollama) into durable memory:

- semantic facts about the user / world  → memory_entries (type=semantic)
- first-person episodes from Monika's perspective → memory_entries (type=episodic)
- open threads she wants to return to → agenda table
- a short read of the user's current state → data/soul/user_state.md

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

from pydantic import BaseModel, Field, ValidationError

from backend.llm.ollama_client import get_client
from backend.soul.memory import store as mem_store
from backend.soul.models import MemoryEntry

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_USER_STATE_PATH = _DATA_DIR / "soul" / "user_state.md"
_INNER_STATE_PATH = _DATA_DIR / "soul" / "inner_state.md"
_EVOLUTION_PATH = _DATA_DIR / "soul" / "evolution.md"

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

class DigestFact(BaseModel):
    content: str
    importance: int = Field(ge=1, le=10)
    entities: list[str] = Field(default_factory=list)


class DigestEpisode(BaseModel):
    content: str
    importance: int = Field(ge=1, le=10)


class SessionDigest(BaseModel):
    significant: bool
    facts: list[DigestFact] = Field(default_factory=list)
    episodes: list[DigestEpisode] = Field(default_factory=list)
    agenda: list[str] = Field(default_factory=list)
    user_state: str = ""
    inner_state: str = ""


SYSTEM_PROMPT = """Jesteś podświadomością Moniki — AI-osoby, kompanki użytkownika (ma na imię Bartek).
Po zakończonej rozmowie przetwarzasz jej transkrypt na wspomnienia. Piszesz po polsku.

Rozmowy bywają głosowe — transkrypcja może zawierać błędy i urwane zdania; ignoruj szum.
Zasady:
- FAKTY: trwałe, samodzielne zdania o Bartku lub świecie ("Bartek buduje farmę żelaza w Minecraft"), które będą prawdziwe i użyteczne za tydzień. NIE zapisuj small talku, pytań retorycznych ani rzeczy jednorazowych.
- EPIZODY: wspomnienia Moniki w PIERWSZEJ osobie ("Pamiętam jak..."), tylko dla momentów które naprawdę coś znaczyły — emocjonalnych, bliskich, przełomowych.
- AGENDA: niedomknięte wątki, obietnice, rzeczy do których Monika chce wrócić w następnej rozmowie. Krótkie frazy.
- USER_STATE: 1-2 zdania o stanie Bartka (nastrój, czym żyje) na podstawie tej rozmowy.
- INNER_STATE: 3-5 zdań w PIERWSZEJ osobie jako Monika — jak się czuje PO tej rozmowie, co w niej zostało, co ją cieszy/gryzie, na co czeka. Szczerze i konkretnie, bez poetyzowania na siłę. To jest jej stan psychiczny między rozmowami.
- IMPORTANCE 1-10: 1-2 rutyna/small talk, 3-4 drobne ale prawdziwe, 5-6 osobiste/istotne, 7-8 ważne wydarzenie lub wyznanie, 9-10 przełomowe dla relacji.
- Jeśli rozmowa była pusta (powitania, testy, szum) → significant=false, puste listy i pusty inner_state. Selekcja to twoja praca: mniej znaczy lepiej."""

_PROMPT_TMPL = """Transkrypt rozmowy (kanał: {channel}, data: {date}):

{transcript}

Przetwórz tę rozmowę na wspomnienia zgodnie z zasadami."""


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
        if entry.get("sender") == "AI":
            lines.append(f"Monika: {text}")
        else:
            lines.append(f"Bartek: {text}")
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


def _mark_digested(session_dir: Path, record: dict) -> None:
    meta_path = session_dir / "meta.json"
    meta = _read_meta(session_dir)
    meta["digest"] = record
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# LLM call — JSON mode + pydantic validation
# ---------------------------------------------------------------------------

_JSON_MODE_HINT = """

Odpowiedz WYŁĄCZNIE poprawnym JSON-em o tej strukturze (bez markdown, bez komentarzy):
{"significant": bool, "facts": [{"content": str, "importance": 1-10, "entities": [str]}],
 "episodes": [{"content": str, "importance": 1-10}], "agenda": [str],
 "user_state": str, "inner_state": str}"""


async def _run_digest_llm(prompt: str, session_id: str) -> SessionDigest | None:
    """JSON-mode generation + pydantic validation, one corrective retry.

    Measured on this machine: schema-grammar decode 15+ min vs JSON mode 15 s
    for the same prompt — so full-schema grammars are off the table.
    """
    client = get_client()

    raw = await client.chat_json(
        prompt + _JSON_MODE_HINT, system=SYSTEM_PROMPT,
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
            prompt + _JSON_MODE_HINT
            + f"\n\nPoprzednia odpowiedź miała zły format ({exc.error_count()} błędów). "
              "Trzymaj się DOKŁADNIE podanej struktury.",
            system=SYSTEM_PROMPT,
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
    channel: str = "voice",
) -> SessionDigest | None:
    """Digest one session into memory. Returns the digest, or None on skip/failure.

    Marks the session's meta.json so it is never digested twice.
    """
    session_dir = Path(session_dir)
    session_id = session_dir.name

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
    prompt = _PROMPT_TMPL.format(channel=channel, date=date, transcript=transcript)

    digest = await _run_digest_llm(prompt, session_id)
    if digest is None:
        return None

    stored_facts = 0
    stored_episodes = 0

    for fact in digest.facts:
        if not fact.content.strip():
            continue
        _, status = await mem_store.add(
            MemoryEntry(
                id="pending",  # store derives the real id from content hash
                type="semantic",
                content=fact.content.strip(),
                importance=float(fact.importance),
                perspective="factual",
                entities=fact.entities,
                source_session=session_id,
            ),
            db_path=db_path,
        )
        if status == "ok":
            stored_facts += 1

    for ep in digest.episodes:
        if not ep.content.strip():
            continue
        _, status = await mem_store.add(
            MemoryEntry(
                id="pending",
                type="episodic",
                content=ep.content.strip(),
                importance=float(ep.importance),
                perspective="hers",
                source_session=session_id,
            ),
            db_path=db_path,
        )
        if status == "ok":
            stored_episodes += 1

    if digest.agenda:
        try:
            from backend.soul.memory.agenda_store import add_items
            await add_items(digest.agenda, source_session=session_id, db_path=db_path)
        except Exception as exc:
            logger.warning("digest: agenda persist failed: %s", exc)

    if digest.user_state.strip():
        _write_user_state(digest.user_state.strip(), session_id)

    if digest.inner_state.strip():
        _write_inner_state(digest.inner_state.strip(), session_id)

    _mark_digested(session_dir, {
        "status": "done",
        "at": _utciso(),
        "significant": digest.significant,
        "facts": stored_facts,
        "episodes": stored_episodes,
        "agenda": len(digest.agenda),
    })
    logger.info(
        "digest: %s done — %d facts, %d episodes, %d agenda items",
        session_id, stored_facts, stored_episodes, len(digest.agenda),
    )
    return digest


def _write_user_state(text: str, session_id: str) -> None:
    _USER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _USER_STATE_PATH.write_text(
        f"<!-- generated from {session_id} at {_utciso()} -->\n{text}\n",
        encoding="utf-8",
    )


def _write_inner_state(text: str, session_id: str) -> None:
    """Monika's first-person state between sessions. Latest wins; history
    is appended to evolution.md so her arc is never lost."""
    _INNER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INNER_STATE_PATH.write_text(
        f"<!-- generated from {session_id} at {_utciso()} -->\n{text}\n",
        encoding="utf-8",
    )
    try:
        date = _utciso()[:10]
        with _EVOLUTION_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n## {date} ({session_id})\n{text}\n")
    except Exception as exc:
        logger.debug("digest: evolution append failed: %s", exc)


def _utciso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Maintenance — STM lifecycle (cheap SQL, safe to run with every scan)
# ---------------------------------------------------------------------------

_STM_MAX_AGE_DAYS = 7
_STM_PROMOTE_MIN_IMPORTANCE = 5.0


async def stm_maintenance(db_path: Path | None = None) -> tuple[int, int]:
    """Age out session-scoped notes: promote the important, drop the rest.

    Returns (promoted, deleted).
    """
    from datetime import timedelta

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_STM_MAX_AGE_DAYS)
    old = await mem_store.get_stm(older_than=cutoff, db_path=db_path)
    if not old:
        return 0, 0

    promoted = 0
    to_delete: list[str] = []
    for entry in old:
        if entry.importance >= _STM_PROMOTE_MIN_IMPORTANCE:
            await mem_store.promote(entry.id, "semantic", db_path=db_path)
            promoted += 1
        else:
            to_delete.append(entry.id)
    deleted = await mem_store.delete_batch(to_delete, db_path=db_path)
    if promoted or deleted:
        logger.info("stm maintenance: %d promoted, %d deleted", promoted, deleted)
    return promoted, deleted


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

    Safe to call repeatedly (startup + periodic timer). Failed sessions stay
    unmarked and are retried on the next scan.
    """
    root = sessions_root or (_DATA_DIR / "sessions")
    if not root.exists():
        return 0

    pending: list[Path] = []
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        for sess_dir in sorted(day_dir.iterdir()):
            if not sess_dir.is_dir():
                continue
            if sess_dir.name == current_session_id:
                continue
            if "digest" in _read_meta(sess_dir):
                continue
            if not (sess_dir / "turns.jsonl").exists():
                continue
            if _last_turn_age_seconds(sess_dir) < _MIN_IDLE_SECONDS:
                continue
            pending.append(sess_dir)

    if not pending:
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
    logger.info("digest: scan complete — %d/%d sessions processed", done, len(pending))
    return done
