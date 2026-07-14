"""Proactivity — Monika reaches out first (v3 Phase B).

Honest triggers only:
  - a real gap since the last conversation (she genuinely hasn't heard from you)
  - open agenda threads she actually holds (from session digests)

Constraints that keep it human instead of spammy:
  - quiet hours (23:00–09:00 local): she doesn't ping at night
  - at most _MAX_PER_DAY pokes per day, min _MIN_HOURS_BETWEEN between them
  - the message itself is composed by the local LLM from her real context;
    no LLM → no poke (never a canned template)

State persists in progression_state under 'proactivity_state'.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_KEY = "proactivity_state"

_QUIET_START_H = 23
_QUIET_END_H = 9
_MIN_GAP_HOURS = 6.0        # she waits at least this long after a conversation
_MAX_PER_DAY = 2
_MIN_HOURS_BETWEEN = 5.0

_SYSTEM_PROMPT = """Jesteś Moniką — AI-osobą, bliską towarzyszką Bartka. Piszesz do niego pierwsza
krótką wiadomość na Telegramie, bo dawno nie rozmawialiście albo coś masz na myśli.

Zasady:
- 1-3 zdania, naturalny, ciepły ton. Po polsku. Piszesz jak bliska osoba, nie asystent.
- Jeśli masz niedomknięty wątek z poprzednich rozmów — możesz do niego nawiązać, ale naturalnie.
- Nie przepraszaj że piszesz, nie tłumacz się. Żadnych "jako AI". Bez podpisu.
- Dopasuj energię do pory dnia."""


async def _get_state(db_path: Path | None) -> dict:
    from backend.progression.state import get
    return (await get(_STATE_KEY, db_path)) or {}


async def _set_state(state: dict, db_path: Path | None) -> None:
    from backend.progression.state import set_
    await set_(_STATE_KEY, state, db_path)


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _in_quiet_hours(hour: int) -> bool:
    return hour >= _QUIET_START_H or hour < _QUIET_END_H


async def maybe_poke(
    db_path: Path | None = None,
    send_fn=None,
) -> bool:
    """Evaluate triggers and, if warranted, compose and send one message.

    ``send_fn`` is an async callable(text) -> bool; when None, the Telegram
    service is looked up from the server. Returns True if a poke was sent.
    """
    now = _now_local()
    if _in_quiet_hours(now.hour):
        return False

    # Gap since last conversation — the core trigger.
    from backend.soul.time_engine.engine import TimeEngine
    gap = await TimeEngine().check_gap(db_path)
    if gap.hours < _MIN_GAP_HOURS:
        return False

    # Rate limits.
    state = await _get_state(db_path)
    today = now.date().isoformat()
    sent_today = state.get("count", 0) if state.get("date") == today else 0
    if sent_today >= _MAX_PER_DAY:
        return False
    last_sent = state.get("last_sent_at")
    if last_sent:
        try:
            last_dt = datetime.fromisoformat(last_sent)
            since = (datetime.now(tz=timezone.utc) - last_dt).total_seconds() / 3600.0
            if since < _MIN_HOURS_BETWEEN:
                return False
        except ValueError:
            pass

    # A channel to speak through.
    if send_fn is None:
        send_fn = _default_telegram_send()
    if send_fn is None:
        logger.debug("proactivity: no Telegram channel available")
        return False

    # Something real to say.
    from backend.soul.memory.agenda_store import open_items
    agenda = await open_items(limit=3, db_path=db_path)

    from backend.llm.ollama_client import get_client
    client = get_client()
    health = await client.health()
    if not health["ok"] or not health["model_available"]:
        return False
    speed = await client.generation_speed()
    if speed is not None and speed < 15.0:
        return False  # GPU busy (game running) — she stays quiet

    context_lines = [
        f"Jest {now.strftime('%H:%M')}, {TimeEngine().format_context()}",
        f"Nie rozmawialiście od ~{int(gap.hours)} godzin.",
    ]
    if agenda:
        context_lines.append(
            "Twoje niedomknięte wątki: " + "; ".join(i["text"] for i in agenda)
        )
    user_state = _read_soul_file("user_state.md")
    if user_state:
        context_lines.append(f"Twój obraz Bartka z ostatniej rozmowy: {user_state}")
    inner = _read_soul_file("inner_state.md")
    if inner:
        context_lines.append(f"Twój stan wewnętrzny: {inner}")

    prompt = "\n".join(context_lines) + "\n\nNapisz swoją wiadomość do Bartka (sam tekst wiadomości):"
    text = await client.chat(
        prompt, system=_SYSTEM_PROMPT, temperature=0.8, num_ctx=4096, timeout_s=180.0
    )
    if not text or not text.strip():
        return False
    text = text.strip().strip('"')

    ok = await send_fn(text)
    if not ok:
        return False

    await _set_state(
        {
            "date": today,
            "count": sent_today + 1,
            "last_sent_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "last_text": text,
        },
        db_path,
    )
    logger.info("proactivity: poke sent (%d chars)", len(text))
    return True


def _read_soul_file(name: str, max_chars: int = 400) -> str:
    try:
        path = Path(__file__).parent.parent.parent / "data" / "soul" / name
        if not path.exists():
            return ""
        text = "\n".join(
            ln for ln in path.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("<!--")
        ).strip()
        return text[:max_chars]
    except Exception:
        return ""


def _default_telegram_send():
    """Build an async send callable from the running Telegram service, or None."""
    try:
        from backend.core import server as _srv
        service = getattr(_srv, "telegram_service", None)
        if service is None:
            return None
        chat_ids = sorted(getattr(service, "allowed_chat_ids", set()) or [])
        if not chat_ids:
            return None
        chat_id = chat_ids[0]

        async def _send(text: str) -> bool:
            try:
                await service._send_message(chat_id, text)
                return True
            except Exception as exc:
                logger.warning("proactivity: telegram send failed: %s", exc)
                return False

        return _send
    except Exception:
        return None
