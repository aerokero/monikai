from __future__ import annotations

import asyncio
import time

import pytest

from backend.llm.thinker import Thinker, _sanitize_thought


def make_thinker(**overrides):
    calls = {"delivered": [], "thoughts": [], "generated": []}
    settings = {"enabled": True, "min_chars": 18, "min_interval_sec": 20.0}
    settings.update(overrides.pop("settings", {}))
    state = {"ai_turn_open": False}

    async def deliver(text):
        calls["delivered"].append(text)

    thinker = Thinker(
        get_history=lambda limit: overrides.get("history", []),
        deliver=deliver,
        is_ai_turn_open=lambda: state["ai_turn_open"],
        on_thought=lambda t: calls["thoughts"].append(t),
        get_settings=lambda: settings,
    )
    thinker._poll_sec = 0.01

    async def fake_generate(user_text):
        calls["generated"].append(user_text)
        return overrides.get("thought", "Ciekawa myśl o tym temacie.")

    thinker._generate = fake_generate
    return thinker, calls, settings, state


async def wait_for_task(thinker):
    if thinker._task:
        await thinker._task


async def test_disabled_means_no_task():
    thinker, calls, settings, _ = make_thinker(settings={"enabled": False})
    thinker.notice_user_text("to jest dłuższa wypowiedź o czymś ważnym")
    assert thinker._task is None
    assert calls["generated"] == []


async def test_happy_path_delivers_internal_monologue():
    thinker, calls, _, _ = make_thinker()
    thinker.notice_user_text("moim zdaniem interstellar jest lepszy niż hail mary")
    await wait_for_task(thinker)
    assert calls["delivered"] == ["(Internal Monologue) Ciekawa myśl o tym temacie."]
    assert calls["thoughts"] == ["Ciekawa myśl o tym temacie."]


async def test_backchannels_and_short_text_are_skipped():
    thinker, calls, _, _ = make_thinker()
    for text in ["mhm", "no dobra", "okej", "tak tak", "za krótkie"]:
        thinker.notice_user_text(text)
    assert thinker._task is None
    assert calls["generated"] == []


async def test_min_interval_between_shots():
    thinker, calls, _, _ = make_thinker()
    thinker.notice_user_text("pierwsza dłuższa wypowiedź o czymś konkretnym")
    await wait_for_task(thinker)
    thinker.notice_user_text("druga dłuższa wypowiedź o czymś zupełnie innym")
    await wait_for_task(thinker)
    assert len(calls["generated"]) == 1


async def test_single_task_in_flight():
    thinker, calls, _, state = make_thinker(settings={"min_interval_sec": 0.0})
    state["ai_turn_open"] = True  # trzymaj task przy życiu w pętli czekania
    thinker.notice_user_text("pierwsza dłuższa wypowiedź o czymś konkretnym")
    await asyncio.sleep(0.05)
    thinker.notice_user_text("druga dłuższa wypowiedź o czymś zupełnie innym")
    assert len(calls["generated"]) == 1
    state["ai_turn_open"] = False
    await wait_for_task(thinker)


async def test_waits_for_ai_turn_close_then_delivers():
    thinker, calls, _, state = make_thinker()
    state["ai_turn_open"] = True
    thinker.notice_user_text("dłuższa wypowiedź w trakcie jej mówienia")
    await asyncio.sleep(0.05)
    assert calls["delivered"] == []
    state["ai_turn_open"] = False
    await wait_for_task(thinker)
    assert len(calls["delivered"]) == 1


async def test_drops_thought_when_turn_never_closes():
    thinker, calls, _, state = make_thinker()
    thinker.delivery_timeout_sec = 0.05
    state["ai_turn_open"] = True
    thinker.notice_user_text("dłuższa wypowiedź w trakcie jej mówienia")
    await wait_for_task(thinker)
    assert calls["delivered"] == []
    assert calls["thoughts"]  # myśl trafiła do diagnostyki mimo porzucenia


async def test_429_sets_silent_cooldown():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})

    async def broken_generate(user_text):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota")

    thinker._generate = broken_generate
    thinker.notice_user_text("dłuższa wypowiedź o czymś konkretnym")
    await wait_for_task(thinker)
    assert calls["delivered"] == []
    assert thinker._next_allowed_ts > time.monotonic() + 60


def test_sanitize_strips_labels_quotes_and_caps_length():
    assert _sanitize_thought('  Myśl: "to jest myśl"  ') == "to jest myśl"
    assert _sanitize_thought("(Internal Monologue) coś tam") == "coś tam"
    long = "Zdanie pierwsze jest całkiem długie i konkretne. " * 30
    result = _sanitize_thought(long)
    assert len(result) <= 600
    assert result.endswith(".")
    assert _sanitize_thought("") == ""


def test_thinker_card_section_loads():
    from backend.soul.identity.character_loader import load_character_section

    card = load_character_section("monika", "THINKER_CARD")
    assert card and "Moniką" in card
    # ~1.5k znaków — ma być kondensatem, nie pełną biblią.
    assert len(card) < 2500
    # Sekcja nie jest wstrzykiwana do głównego promptu.
    from backend.soul.identity.character_loader import load_character_prompt

    main = load_character_prompt("monika")
    assert main and "kompas" in main  # IDENTITY nadal wchodzi
    assert "syntetyzujesz zamiast katalogować, nowe od razu" not in main
