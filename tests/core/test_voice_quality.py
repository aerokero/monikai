from backend.conversation.voice_quality import (
    assess_voice_transcript,
    normalize_voice_confidence,
    voice_transcript_is_usable,
)


def test_voice_quality_accepts_short_clear_words_without_meaning_inference():
    assert voice_transcript_is_usable("proszę")
    assert voice_transcript_is_usable("piątek", confidence=0.91)


def test_voice_quality_rejects_explicit_unintelligible_markers():
    result = assess_voice_transcript("[unintelligible]")

    assert not result.accepted
    assert result.reason == "unintelligible_marker"


def test_voice_quality_rejects_low_confidence_before_generation():
    result = assess_voice_transcript("Okej, ja się waszy.", confidence=0.31)

    assert not result.accepted
    assert result.reason == "low_confidence"


def test_voice_quality_normalizes_percentage_confidence():
    assert normalize_voice_confidence("82") == 0.82
    assert normalize_voice_confidence("not-a-number") is None

