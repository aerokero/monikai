from backend.core import model_config as model_config
from backend.core.monikai import (
    _build_voice_renderer_thinking_config,
    _streaming_transcript_update,
)


def test_renderer_disables_native_thinking_on_gemini_25(monkeypatch):
    monkeypatch.setattr(model_config, "_is_31", False)
    config = _build_voice_renderer_thinking_config()
    assert config.thinking_budget == 0
    assert config.include_thoughts is False


def test_renderer_uses_minimal_floor_on_gemini_31(monkeypatch):
    monkeypatch.setattr(model_config, "_is_31", True)
    config = _build_voice_renderer_thinking_config()
    level = getattr(config.thinking_level, "value", config.thinking_level)
    assert str(level).lower() == "minimal"
    assert config.include_thoughts is False


def test_streaming_transcript_distinguishes_growth_revision_and_new_chunk():
    assert _streaming_transcript_update("Hej", "Hej, co słychać?") == (", co słychać?", False)

    repeated = "Rozumiem. Kontynuuj, słucham dokładnie."
    corrected = "Rozumiem. Kontynuuj — słucham dokładnie."
    assert _streaming_transcript_update(repeated, corrected) == (corrected, True)

    assert _streaming_transcript_update("Pierwsze zdanie.", "Drugie zdanie.") == (
        "Drugie zdanie.",
        False,
    )
