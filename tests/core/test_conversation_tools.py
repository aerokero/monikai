from backend.conversation.tools import (
    ConversationToolRequest,
    ConversationToolResult,
    plan_read_only_tool,
    validate_planned_tool_request,
)


def test_read_only_planner_recognizes_supported_queries():
    assert plan_read_only_tool("Która jest godzina?").name == "get_time_context"
    assert plan_read_only_tool("Jakie mam przypomnienia?").name == "list_reminders"
    assert plan_read_only_tool("Sprawdź pogodę.").name == "get_weather"
    assert plan_read_only_tool("Co mam w notatkach?").name == "notes_get"
    assert plan_read_only_tool("Pokaż notatki.").name == "notes_get"


def test_read_only_planner_does_not_claim_mutating_requests():
    assert plan_read_only_tool("Ustaw przypomnienie na jutro.") is None
    assert plan_read_only_tool("Usuń wszystkie przypomnienia.") is None
    assert plan_read_only_tool("Włącz światło.") is None


def test_tool_result_has_explicit_runtime_status():
    evidence = ConversationToolResult(
        name="get_weather",
        result="Current weather: rain",
    ).as_evidence()

    assert "tool=get_weather" in evidence
    assert "status=success" in evidence
    assert "Current weather: rain" in evidence


def test_mutating_model_plan_requires_explicit_non_negated_intent():
    create = ConversationToolRequest(
        "create_reminder",
        {"message": "raport", "in_minutes": 10},
    )

    assert validate_planned_tool_request(
        "Przypomnij mi o raporcie za 10 minut.",
        create,
    )
    assert not validate_planned_tool_request(
        "Nie przypominaj mi o raporcie.",
        create,
    )
    assert not validate_planned_tool_request(
        "Podaj przykład prośby o ustawienie przypomnienia.",
        create,
    )


def test_calendar_mutation_requires_explicit_non_negated_intent():
    create = ConversationToolRequest(
        "create_event",
        {
            "summary": "Dentysta",
            "start_iso": "2026-08-01T12:00:00+02:00",
            "end_iso": "2026-08-01T13:00:00+02:00",
        },
    )

    assert validate_planned_tool_request(
        "Dodaj wydarzenie do kalendarza: dentysta w sobotę o 12.",
        create,
    )
    assert not validate_planned_tool_request(
        "Nie dodawaj wydarzenia do kalendarza.",
        create,
    )
    assert not validate_planned_tool_request(
        "Może pójdę w sobotę do dentysty.",
        create,
    )


def test_notes_append_and_overwrite_have_distinct_intents():
    append = ConversationToolRequest("notes_append", {"content": "kup mleko"})
    overwrite = ConversationToolRequest("notes_set", {"content": "kup mleko"})

    assert validate_planned_tool_request(
        "Dopisz do notatek: kup mleko.",
        append,
    )
    assert validate_planned_tool_request(
        "Zanotuj: kup mleko.",
        append,
    )
    assert validate_planned_tool_request(
        "Zrób notatkę: kup mleko.",
        append,
    )
    assert validate_planned_tool_request(
        "Zapisz w notatkach: kup mleko.",
        append,
    )
    assert not validate_planned_tool_request(
        "Nie dopisuj niczego do notatek.",
        append,
    )
    assert not validate_planned_tool_request(
        "Dopisz do notatek: kup mleko.",
        overwrite,
    )
    assert validate_planned_tool_request(
        "Nadpisz całe notatki tekstem: kup mleko.",
        overwrite,
    )


def test_memory_write_requires_explicit_non_negated_request():
    request = ConversationToolRequest(
        "memory_add_entry",
        {"type": "semantic", "content": "Bartosz nie lubi oliwek."},
    )

    assert validate_planned_tool_request(
        "Zapamiętaj, że nie lubię oliwek.",
        request,
    )
    assert not validate_planned_tool_request(
        "Nie zapamiętuj tego, że nie lubię oliwek.",
        request,
    )
    assert not validate_planned_tool_request(
        "Nie lubię oliwek.",
        request,
    )


def test_memory_page_mutations_require_explicit_intent():
    create = ConversationToolRequest(
        "memory_create_page",
        {"title": "Projekt", "folder": "topics"},
    )
    append = ConversationToolRequest(
        "memory_append_page",
        {"path": "topics/projekt.md", "content": "Nowy punkt"},
    )

    assert validate_planned_tool_request(
        "Utwórz stronę pamięci o nazwie Projekt.",
        create,
    )
    assert validate_planned_tool_request(
        "Dopisz do strony pamięci Projekt: Nowy punkt.",
        append,
    )
    assert not validate_planned_tool_request(
        "Nie twórz strony pamięci Projekt.",
        create,
    )


def test_light_control_preserves_explicit_action_and_rejects_negation():
    turn_on = ConversationToolRequest(
        "control_light",
        {"target": "lampa w salonie", "action": "turn_on"},
    )
    turn_off = ConversationToolRequest(
        "control_light",
        {"target": "lampa w salonie", "action": "turn_off"},
    )

    assert validate_planned_tool_request(
        "Włącz lampę w salonie.",
        turn_on,
    )
    assert not validate_planned_tool_request(
        "Włącz lampę w salonie.",
        turn_off,
    )
    assert not validate_planned_tool_request(
        "Nie włączaj lampy w salonie.",
        turn_on,
    )


def test_light_setting_requires_a_valid_explicit_change():
    valid = ConversationToolRequest(
        "control_light",
        {
            "target": "światło w gabinecie",
            "action": "set",
            "brightness": 40,
        },
    )
    invalid = ConversationToolRequest(
        "control_light",
        {
            "target": "światło w gabinecie",
            "action": "set",
            "brightness": 140,
        },
    )

    assert validate_planned_tool_request(
        "Ustaw jasność światła w gabinecie na 40 procent.",
        valid,
    )
    assert not validate_planned_tool_request(
        "Ustaw jasność światła w gabinecie na 140 procent.",
        invalid,
    )
