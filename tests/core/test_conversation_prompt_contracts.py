from backend.core.system_prompt import OPERATIONAL_PROMPT
from backend.core.tool_definitions import create_event_tool, memory_add_entry_tool


def test_voice_model_is_a_renderer_of_the_response_brief():
    assert "Nie twórz własnego wewnętrznego monologu" in OPERATIONAL_PROMPT
    assert "ukończonym tekstem Twojej następnej wypowiedzi" in OPERATIONAL_PROMPT
    assert "wypowiedz CAŁY `<reply_core>`" in OPERATIONAL_PROMPT
    assert "nie zastępuj pytania podobnym pytaniem" in OPERATIONAL_PROMPT


def test_uncertain_social_plans_are_not_memories_or_calendar_events():
    assert "planie z „może”" in OPERATIONAL_PROMPT
    assert "maybe going on a date tomorrow" in memory_add_entry_tool["description"]
    assert "hedged plan" in create_event_tool["description"]
