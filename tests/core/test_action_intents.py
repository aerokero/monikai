import sys
from pathlib import Path


ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(ODY_ROOT))

from src.action_intents import (  # noqa: E402
    classify_tool_intent,
    extract_smart_home_command,
)
from src.agent_loop import (  # noqa: E402
    _classify_agent_request,
    _looks_like_local_computer_request,
)
from src.tool_index import ToolIndex  # noqa: E402


def test_polish_home_assistant_scene_command_is_promoted_to_tools():
    intent = classify_tool_intent("Włącz tryb nocny w Home Assistant.")

    assert intent.needs_tools is True
    assert intent.category == "smart_home"


def test_polish_relaxation_mode_command_is_promoted_to_home_assistant_tools():
    intent = classify_tool_intent("Czy możesz włączyć w domu tryb relaksu?")

    assert intent.needs_tools is True
    assert intent.category == "smart_home"

    agent_intent = _classify_agent_request(
        [{"role": "user", "content": "Czy możesz włączyć w domu tryb relaksu?"}],
        "Czy możesz włączyć w domu tryb relaksu?",
    )
    assert "smart_home" in agent_intent["domains"]


def test_named_night_scene_is_not_classified_as_monikai_ui_theme():
    intent = classify_tool_intent("Aktywuj scenę Tryb nocny w Home Assistant")

    assert intent.needs_tools is True
    assert intent.category == "smart_home"


def test_home_assistant_clarification_keeps_prior_command_on_agent_path():
    intent = classify_tool_intent("Chodzi o Home Assistant, nie motyw MonikAI.")

    assert intent.needs_tools is True
    assert intent.category == "smart_home"


def test_attached_smart_home_phrasings_keep_the_home_assistant_tool_available():
    phrases = (
        "Hey, can you turn off all lights please?",
        "Can you turn on night lights please?",
        "I mean HA, scene night i believe",
        "You have just turned off the lights, now turn on the relax scene or something",
        "ok, now, the noc scene",
    )

    for phrase in phrases:
        route_intent = classify_tool_intent(phrase)
        agent_intent = _classify_agent_request(
            [{"role": "user", "content": phrase}],
            phrase,
        )
        assert route_intent.needs_tools is True, phrase
        assert route_intent.category == "smart_home", phrase
        assert "smart_home" in agent_intent["domains"], phrase


def test_unambiguous_all_lights_commands_are_canonicalized_with_polarity():
    assert extract_smart_home_command(
        "Wyłącz proszę wszystkie światła."
    ) == {"action": "turn_off", "target": "all lights"}
    assert extract_smart_home_command(
        "Włączyć wszystko dosłownie.",
        "Wyłącz proszę wszystkie światła.",
    ) == {"action": "turn_on", "target": "all lights"}


def test_all_lights_fallback_does_not_execute_explanations_or_negations():
    assert extract_smart_home_command(
        "Dlaczego nie mogę wyłączyć wszystkich świateł?"
    ) is None
    assert extract_smart_home_command(
        "Nie wyłączaj wszystkich świateł."
    ) is None
    assert extract_smart_home_command(
        "How do I turn off all lights?"
    ) is None


def test_smart_home_followup_keeps_the_previous_lighting_topic():
    intent = _classify_agent_request(
        [
            {"role": "user", "content": "Wyłącz proszę wszystkie światła."},
            {
                "role": "assistant",
                "content": "Czy chodzi o konkretne światło albo scenariusz?",
            },
            {"role": "user", "content": "Wyłączyć wszystko dosłownie."},
        ],
        "Wyłączyć wszystko dosłownie.",
    )

    assert intent["continuation"] is True
    assert intent["domains"] == {"smart_home"}
    assert intent["smart_home_command"] == {
        "action": "turn_off",
        "target": "all lights",
    }


def test_turn_on_night_lights_is_not_a_named_computer_request():
    assert not _looks_like_local_computer_request(
        "Can you turn on night lights please?"
    )
    assert _looks_like_local_computer_request("Run the tests on hades")


def test_scene_word_order_variants_force_include_home_assistant_tool():
    for phrase in ("scene night", "noc scene", "night lights", "relax scene"):
        selected = set()
        for keywords, tools in ToolIndex._KEYWORD_HINTS.items():
            if any(keyword in phrase for keyword in keywords):
                selected.update(tools)
        assert "home_assistant_control" in selected, phrase
