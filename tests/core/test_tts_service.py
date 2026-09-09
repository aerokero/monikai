import io
import importlib.util
import sys
import tempfile
import wave
from pathlib import Path

# The production bridge puts Odysseus on PYTHONPATH as ``src``.  Mirror that
# layout in the isolated test runner without importing the broad services
# package (which has optional search dependencies).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "odysseus"))

_TTS_SPEC = importlib.util.spec_from_file_location(
    "monikai_tts_service_under_test",
    Path(__file__).resolve().parents[2]
    / "backend"
    / "odysseus"
    / "services"
    / "tts"
    / "tts_service.py",
)
_TTS_MODULE = importlib.util.module_from_spec(_TTS_SPEC)
assert _TTS_SPEC.loader is not None
_TTS_SPEC.loader.exec_module(_TTS_MODULE)

TTSService = _TTS_MODULE.TTSService
_kokoro_code = _TTS_MODULE._kokoro_code
_kokoro_polish_mode = _TTS_MODULE._kokoro_polish_mode
_map_polish_kokoro_phonemes = _TTS_MODULE._map_polish_kokoro_phonemes
_voice_for_kokoro_language = _TTS_MODULE._voice_for_kokoro_language
detect_text_language = _TTS_MODULE.detect_text_language
kokoro_language_for_voice = _TTS_MODULE.kokoro_language_for_voice


def test_kokoro_voice_prefix_selects_the_matching_language_pipeline():
    assert kokoro_language_for_voice("af_heart") == "a"
    assert kokoro_language_for_voice("bf_emma") == "b"
    assert kokoro_language_for_voice("ff_siwis") == "f"
    assert kokoro_language_for_voice("pf_dora") == "p"


def test_kokoro_language_aliases_and_polish_detection(monkeypatch):
    monkeypatch.delenv("KOKORO_POLISH_MODE", raising=False)
    assert _kokoro_code("en-US") == "a"
    assert _kokoro_code("fr") == "f"
    assert _kokoro_code("pl") is None
    assert detect_text_language("To jest wiadomość po polsku: żółć.") == "pl"
    assert detect_text_language("To jest test") == "pl"
    monkeypatch.setenv("KOKORO_POLISH_MODE", "experimental")
    assert _kokoro_code("pl") == "l"


def test_polish_is_the_safe_default_and_piper_locale_is_not_portuguese(monkeypatch):
    monkeypatch.delenv("KOKORO_POLISH_MODE", raising=False)
    assert _kokoro_polish_mode() == "espeak"

    service = TTSService(cache_dir=tempfile.mkdtemp())
    assert service._resolve_language("Dobrze.", "auto", "pl_PL-gosia-medium") == "pl"
    assert _TTS_MODULE._piper_voice_urls("pl_PL-gosia-medium")[0].endswith(
        "/pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx"
    )


def test_polish_experimental_voice_uses_stock_female_embedding(monkeypatch):
    monkeypatch.setenv("KOKORO_POLISH_MODE", "experimental")
    assert _kokoro_polish_mode() == "experimental"
    assert _voice_for_kokoro_language("af_heart", "l") == "af_heart"
    assert _voice_for_kokoro_language("af_bella", "l") == "af_bella"
    assert _voice_for_kokoro_language("", "l") == "af_heart"
    assert _voice_for_kokoro_language("am_adam", "l") is None


def test_polish_phoneme_map_replaces_missing_kokoro_symbols():
    mapped = _map_polish_kokoro_phonemes("dʑ tɕ dʒ tʃ dz ts ʑ")
    assert mapped == "ʥ ʨ ʤ ʧ ʣ ʦ ʒʲ"


def test_polish_can_be_forced_back_to_espeak(monkeypatch):
    monkeypatch.setenv("KOKORO_POLISH_MODE", "espeak")
    assert _kokoro_polish_mode() == "espeak"
    assert _kokoro_code("pl") is None


def test_espeak_fallback_returns_24khz_wav_for_polish():
    service = TTSService(cache_dir=tempfile.mkdtemp())
    audio = service._synthesize_with_espeak("To jest test polskiej wymowy.", "pl", 1.0)

    assert audio and audio[:4] == b"RIFF"
    with wave.open(io.BytesIO(audio), "rb") as rendered:
        assert rendered.getnchannels() == 1
        assert rendered.getsampwidth() == 2
        assert rendered.getframerate() == 24_000


def test_polish_synthesis_never_calls_kokoro_english_pipeline(monkeypatch):
    service = TTSService(cache_dir=tempfile.mkdtemp())
    monkeypatch.setattr(
        service,
        "_load_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "local",
            "tts_model": "Kokoro-82M",
            "tts_voice": "af_heart",
            "tts_speed": "1",
            "tts_language": "pl",
        },
    )

    kokoro_calls = []
    monkeypatch.setattr(service, "_get_kokoro", lambda: kokoro_calls.append(True))
    audio = service.synthesize("To jest po polsku.", use_cache=False)
    assert audio and audio[:4] == b"RIFF"
    assert kokoro_calls == []


def test_explicit_local_provider_overrides_a_different_saved_provider(monkeypatch):
    service = TTSService(cache_dir=tempfile.mkdtemp())
    monkeypatch.setattr(
        service,
        "_load_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "gemini",
            "tts_model": "tts-1",
            "tts_voice": "Leda",
            "tts_speed": "1",
            "tts_language": "pl",
        },
    )
    audio = service.synthesize(
        "To jest lokalny test.",
        use_cache=False,
        provider="local",
        language="pl",
    )
    assert audio and audio[:4] == b"RIFF"
