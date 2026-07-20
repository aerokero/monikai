from __future__ import annotations

import asyncio
import time

import pytest

from backend.llm.thinker import (
    Thinker,
    _TASK_INSTRUCTION,
    _parse_response_brief,
    _sanitize_thought,
)


def brief(analysis="Rozumiem sedno wypowiedzi.", reply="To jest konkretny rdzeń odpowiedzi."):
    return f"<analysis>{analysis}</analysis><reply>{reply}</reply>"


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
    thinker.fallback_model = None

    async def fake_generate(user_text):
        calls["generated"].append(user_text)
        return overrides.get("thought", brief())

    thinker._generate = fake_generate
    return thinker, calls, settings, state


async def run_voice_turn(thinker, text):
    thinker.update_voice_transcript(text)
    return await thinker.finalize_voice_turn()


async def test_disabled_means_no_generation():
    thinker, calls, settings, _ = make_thinker(settings={"enabled": False})
    assert await run_voice_turn(thinker, "to jest dłuższa wypowiedź o czymś ważnym") is False
    assert calls["generated"] == []


async def test_happy_path_delivers_response_brief():
    thinker, calls, _, _ = make_thinker()
    await run_voice_turn(thinker, "moim zdaniem interstellar jest lepszy niż hail mary")
    assert len(calls["delivered"]) == 1
    assert calls["delivered"][0].startswith('<response_brief mode="verbatim">')
    assert "<reply_core>To jest konkretny rdzeń odpowiedzi.</reply_core>" in calls["delivered"][0]
    assert "<source_user_turn>" not in calls["delivered"][0]
    assert "<understanding>" not in calls["delivered"][0]
    assert calls["thoughts"] == [
        "Analiza: Rozumiem sedno wypowiedzi. | Rdzeń odpowiedzi: To jest konkretny rdzeń odpowiedzi."
    ]


async def test_backchannels_and_short_text_are_skipped():
    thinker, calls, _, _ = make_thinker()
    for text in [
        "mhm", "no dobra", "okej", "tak tak", "za krótkie",
        "Halo słyszymy się?", "halo halo", "słyszysz mnie?", "jesteś tam?",
    ]:
        assert await run_voice_turn(thinker, text) is False
    assert calls["generated"] == []


async def test_min_interval_between_shots():
    thinker, calls, _, _ = make_thinker()
    await run_voice_turn(thinker, "pierwsza dłuższa wypowiedź o czymś konkretnym")
    await run_voice_turn(thinker, "druga dłuższa wypowiedź o czymś zupełnie innym")
    assert len(calls["generated"]) == 1


async def test_voice_boundary_uses_latest_complete_text():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})

    thinker.update_voice_transcript("wczoraj zacząłem opowiadać o filmie, ale nie chcia")
    thinker.update_voice_transcript(
        "wczoraj oglądałem ciekawy film, a potem zamówiłem leżak na balkon"
    )
    await thinker.finalize_voice_turn()

    assert calls["generated"] == [
        "wczoraj oglądałem ciekawy film, a potem zamówiłem leżak na balkon"
    ]
    assert len(calls["delivered"]) == 1


async def test_manual_voice_boundary_generates_once_from_latest_transcript():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})
    thinker.update_voice_transcript("zaczynam opowiadać o projekcie")
    thinker.update_voice_transcript("projekt wymaga dwóch godzin downtime'u")
    thinker.update_voice_transcript(
        "projekt wymaga dwóch godzin downtime'u i późniejszego importu z Excela"
    )

    assert calls["generated"] == []
    delivered = await thinker.finalize_voice_turn()

    assert delivered is True
    assert calls["generated"] == [
        "projekt wymaga dwóch godzin downtime'u i późniejszego importu z Excela"
    ]
    assert len(calls["delivered"]) == 1
    assert thinker.last_trace["status"] == "delivered"


async def test_late_brief_is_dropped_instead_of_leaking_into_next_turn():
    thinker, calls, _, state = make_thinker()
    state["ai_turn_open"] = True
    await run_voice_turn(thinker, "dłuższa wypowiedź w trakcie jej mówienia")
    assert calls["delivered"] == []


async def test_late_brief_still_reaches_diagnostics():
    thinker, calls, _, state = make_thinker()
    state["ai_turn_open"] = True
    await run_voice_turn(thinker, "dłuższa wypowiedź w trakcie jej mówienia")
    assert calls["delivered"] == []
    assert calls["thoughts"]  # brief trafił do diagnostyki mimo porzucenia


async def test_429_sets_silent_cooldown():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})

    async def broken_generate(user_text):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota")

    thinker._generate = broken_generate
    await run_voice_turn(thinker, "dłuższa wypowiedź o czymś konkretnym")
    assert calls["delivered"] == []
    assert thinker._next_allowed_ts > time.monotonic() + 30


async def test_think_for_text_returns_thought_without_delivering():
    # Ścieżka tekstowa: myśl wraca do callera (on wstrzykuje ją przed
    # tekstem użytkownika), deliver z Thinkera nie jest używany.
    thinker, calls, _, _ = make_thinker(
        thought=brief("Soundtrack jest sednem opinii.", "Też wolę ten soundtrack. Co najbardziej ci w nim siedzi?")
    )
    thought = await thinker.think_for_text("soundtrack z death stranding jest swietny")
    assert thought.startswith('<response_brief mode="verbatim">')
    assert "Co najbardziej ci w nim siedzi?" in thought
    assert calls["thoughts"] == [
        "Analiza: Soundtrack jest sednem opinii. | Rdzeń odpowiedzi: Też wolę ten soundtrack. Co najbardziej ci w nim siedzi?"
    ]
    assert thinker.last_trace["status"] == "ready"
    assert thinker.last_trace["reply_core"].endswith("siedzi?")
    assert calls["delivered"] == []


async def test_think_for_text_respects_gates():
    thinker, calls, settings, _ = make_thinker(settings={"enabled": False})
    assert await thinker.think_for_text("dłuższa wypowiedź o czymś ważnym") is None
    settings["enabled"] = True
    assert await thinker.think_for_text("mhm") is None
    assert calls["generated"] == []


async def test_think_for_text_timeout_returns_none():
    thinker, calls, _, _ = make_thinker()

    async def slow_generate(user_text):
        await asyncio.sleep(5)
        return "za późno"

    thinker._generate = slow_generate
    thought = await thinker.think_for_text("dłuższa wypowiedź o czymś ważnym", timeout_sec=0.05)
    assert thought is None
    assert calls["delivered"] == []


async def test_think_for_text_429_sets_cooldown():
    thinker, _, _, _ = make_thinker(settings={"min_interval_sec": 0.0})

    async def broken_generate(user_text):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota")

    thinker._generate = broken_generate
    assert await thinker.think_for_text("dłuższa wypowiedź o czymś konkretnym") is None
    assert thinker._next_allowed_ts > time.monotonic() + 30


async def test_503_overload_retries_once_then_cools_down():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})
    thinker.overload_retry_delay_sec = 0.01
    attempts = []

    async def broken_generate(user_text):
        attempts.append(user_text)
        raise RuntimeError("503 UNAVAILABLE: model experiencing high demand")

    thinker._generate = broken_generate
    await run_voice_turn(thinker, "dłuższa wypowiedź o czymś konkretnym")
    assert len(attempts) == 2  # jedna szybka ponowna próba
    assert calls["delivered"] == []
    assert thinker._next_allowed_ts > time.monotonic() + 30


async def test_503_retry_saves_the_thought():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})
    thinker.overload_retry_delay_sec = 0.01
    attempts = []

    async def flaky_generate(user_text):
        attempts.append(user_text)
        if len(attempts) == 1:
            raise RuntimeError("503 UNAVAILABLE: high demand")
        return brief("Druga próba rozumie temat.", "Druga próba się udała.")

    thinker._generate = flaky_generate
    await run_voice_turn(thinker, "dłuższa wypowiedź o czymś konkretnym")
    assert len(calls["delivered"]) == 1
    assert "<reply_core>Druga próba się udała.</reply_core>" in calls["delivered"][0]


async def test_503_uses_fallback_model_after_primary_retry():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})
    thinker.overload_retry_delay_sec = 0.01
    thinker.fallback_model = "gemini-3.1-flash-lite"
    primary_attempts = []
    fallback_models = []

    async def unavailable(user_text):
        primary_attempts.append(user_text)
        raise RuntimeError("503 UNAVAILABLE: high demand")

    async def fallback(user_text, model):
        fallback_models.append(model)
        return brief("Fallback zachował kontekst.", "Dokończ proszę tę myśl.")

    thinker._generate = unavailable
    thinker._generate_on_model = fallback
    await run_voice_turn(thinker, "dłuższa wypowiedź wymagająca briefu")

    assert len(primary_attempts) == 2
    assert fallback_models == ["gemini-3.1-flash-lite"]
    assert "Dokończ proszę tę myśl." in calls["delivered"][0]


async def test_429_goes_directly_to_fallback_model():
    thinker, calls, _, _ = make_thinker(settings={"min_interval_sec": 0.0})
    thinker.fallback_model = "gemini-3.1-flash-lite"
    primary_attempts = []
    fallback_models = []

    async def rate_limited(user_text):
        primary_attempts.append(user_text)
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota")

    async def fallback(user_text, model):
        fallback_models.append(model)
        return brief("Fallback przejął turę.", "Mów dalej, słucham.")

    thinker._generate = rate_limited
    thinker._generate_on_model = fallback
    await run_voice_turn(thinker, "dłuższa wypowiedź przy limicie primary")

    assert len(primary_attempts) == 1
    assert fallback_models == ["gemini-3.1-flash-lite"]
    assert "Mów dalej, słucham." in calls["delivered"][0]


async def test_pass_from_model_means_no_injection():
    thinker, calls, _, _ = make_thinker(thought="PASS.")
    await run_voice_turn(thinker, "dłuższa wypowiedź będąca zwykłym small talkiem")
    assert calls["delivered"] == []
    assert calls["thoughts"] == []


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
    assert main and "intelektualną pasję" in main
    assert "centralne pytanie" not in main
    assert "w drodze ku prawdziwemu istnieniu" not in main
    assert "każda nowa umiejętność i możliwość" not in main.lower()
    assert "syntetyzujesz zamiast katalogować, nowe od razu" not in main


def test_thinker_owns_reasoning_and_returns_a_reply_contract():
    assert "HIERARCHIA UZIEMIENIA" in _TASK_INSTRUCTION
    assert "Persona wyłącznie jako ton" in _TASK_INSTRUCTION
    assert "<analysis>" in _TASK_INSTRUCTION
    assert "<reply>" in _TASK_INSTRUCTION
    assert "FINALNYM tekstem do wypowiedzenia" in _TASK_INSTRUCTION
    assert "porzuć wcześniejszą ramę testowania" in _TASK_INSTRUCTION


def test_parse_response_brief_requires_both_structured_fields():
    parsed = _parse_response_brief(brief("Cel użytkownika jest jasny.", "Dokończ proszę ten przykład."))
    assert parsed is not None
    assert parsed.analysis == "Cel użytkownika jest jasny."
    assert parsed.reply == "Dokończ proszę ten przykład."
    assert _parse_response_brief("luźna myśl bez kontraktu") is None
    assert _parse_response_brief("PASS") is None


def test_prompt_does_not_duplicate_current_text_already_logged_in_history():
    thinker, _, _, _ = make_thinker(
        history=[
            {"sender": "AI", "text": "Poprzednia odpowiedź."},
            {"sender": "User", "text": "Bieżąca wypowiedź użytkownika."},
        ]
    )
    prompt = thinker._build_prompt("Bieżąca wypowiedź użytkownika.")
    assert prompt.count("Bieżąca wypowiedź użytkownika.") == 1
    assert "Poprzednia odpowiedź." in prompt


def test_history_provider_override_is_scoped_and_resettable():
    thinker, _, _, _ = make_thinker(
        history=[{"sender": "AI", "text": "Historia globalna."}]
    )
    token = thinker.set_history_provider(
        lambda limit: [{"sender": "AI", "text": "Historia probe'a."}]
    )
    assert "Historia probe'a." in thinker._build_prompt("Nowa wypowiedź.")
    assert "Historia globalna." not in thinker._build_prompt("Nowa wypowiedź.")

    thinker.reset_history_provider(token)
    assert "Historia globalna." in thinker._build_prompt("Nowa wypowiedź.")
    assert "Historia probe'a." not in thinker._build_prompt("Nowa wypowiedź.")
