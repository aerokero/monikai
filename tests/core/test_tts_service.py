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
    assert _kokoro_code("pl") == "l"
    assert detect_text_language("To jest wiadomość po polsku: żółć.") == "pl"
    assert detect_text_language("To jest test") == "pl"


def test_polish_kokoro_is_the_default_and_voice_locale_stays_kokoro(monkeypatch):
    monkeypatch.delenv("KOKORO_POLISH_MODE", raising=False)
    assert _kokoro_polish_mode() == "experimental"

    service = TTSService(cache_dir=tempfile.mkdtemp())
    assert service._resolve_language("To jest dobrze.", "auto", "af_heart") == "pl"


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


def test_polish_synthesis_uses_kokoro_polish_pipeline(monkeypatch):
    service = TTSService(cache_dir=tempfile.mkdtemp())
    monkeypatch.setattr(
        service,
        "_load_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "local",
            "tts_model": "Kokoro",
            "tts_voice": "af_heart",
            "tts_speed": "1",
            "tts_language": "pl",
        },
    )

    class FakeKokoro:
        available = True

        def synthesize_raw(self, text, voice, *, language):
            assert text == "To jest po polsku."
            assert voice == "af_heart"
            assert language == "pl"
            return b"RIFFfake-kokoro-audio"

    kokoro_calls = []
    monkeypatch.setattr(service, "_get_kokoro", lambda: kokoro_calls.append(True) or FakeKokoro())
    audio = service.synthesize("To jest po polsku.", use_cache=False)
    assert audio and audio[:4] == b"RIFF"
    assert kokoro_calls == [True]


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


def test_xtts_provider_settings_and_synthesis(monkeypatch):
    service = TTSService(cache_dir=tempfile.mkdtemp())
    monkeypatch.setattr(
        service,
        "_load_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "xtts",
            "tts_model": "XTTS-v2",
            "tts_voice": "monika",
            "tts_speed": "1",
            "tts_language": "pl",
        },
    )

    class FakeXTTS:
        available = True

        def synthesize(self, text, speaker=None, language=None, speed=1.0):
            assert text == "Cześć, jak się masz?"
            assert speaker in {"monika", "leda"}
            assert language == "pl"
            return b"RIFFfake-xtts-audio-bytes"

    xtts_calls = []
    monkeypatch.setattr(service, "_get_xtts", lambda: xtts_calls.append(True) or FakeXTTS())
    assert service.available is True

    audio = service.synthesize("Cześć, jak się masz?", use_cache=False)
    assert audio == b"RIFFfake-xtts-audio-bytes"
    assert len(xtts_calls) == 2


def test_xtts_fallback_to_local_when_unavailable(monkeypatch):
    service = TTSService(cache_dir=tempfile.mkdtemp())
    monkeypatch.setattr(
        service,
        "_load_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "xtts",
            "tts_model": "XTTS-v2",
            "tts_voice": "monika",
            "tts_speed": "1",
            "tts_language": "pl",
        },
    )

    class FakeUnavailableXTTS:
        available = False

        def synthesize(self, text, speaker=None, language=None, speed=1.0):
            return None

    class FakeKokoro:
        available = True

        def synthesize_raw(self, text, voice, *, language):
            return b"RIFFfake-kokoro-fallback"

    monkeypatch.setattr(service, "_get_xtts", lambda: FakeUnavailableXTTS())
    monkeypatch.setattr(service, "_get_kokoro", lambda: FakeKokoro())

    audio = service.synthesize("Fallback test.", use_cache=False)
    assert audio == b"RIFFfake-kokoro-fallback"


def test_pocket_tts_provider_settings_and_synthesis(monkeypatch):
    service = TTSService(cache_dir=tempfile.mkdtemp())
    monkeypatch.setattr(
        service,
        "_load_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "pocket",
            "tts_model": "pocket-tts-polish-6l",
            "tts_voice": "Leda",
            "tts_speed": "1.10",
            "tts_language": "pl",
            "tts_pocket_temperature": 0.75,
            "tts_pocket_steps": 2,
        },
    )

    class FakePocket:
        available = True

        def synthesize(self, text, voice=None, speed=1.0, temperature=0.7, steps=2):
            assert text == "Cześć, jak się masz?"
            assert voice == "Leda"
            assert round(speed, 2) == 1.10
            assert temperature == 0.75
            assert steps == 2
            return b"RIFFfake-pocket-audio-bytes"

    pocket_calls = []
    monkeypatch.setattr(service, "_get_pocket", lambda: pocket_calls.append(True) or FakePocket())
    assert service.available is True

    audio = service.synthesize("Cześć, jak się masz?", use_cache=False)
    assert audio == b"RIFFfake-pocket-audio-bytes"
    assert len(pocket_calls) == 2


def test_pocket_tts_fallback_to_local_when_unavailable(monkeypatch):
    service = TTSService(cache_dir=tempfile.mkdtemp())
    monkeypatch.setattr(
        service,
        "_load_settings",
        lambda: {
            "tts_enabled": True,
            "tts_provider": "pocket",
            "tts_model": "pocket-tts-polish-6l",
            "tts_voice": "Leda",
            "tts_speed": "1",
            "tts_language": "pl",
        },
    )

    class FakeUnavailablePocket:
        available = False

        def synthesize(self, text, voice=None, speed=1.0, temperature=0.7, steps=2):
            return None

    class FakeKokoro:
        available = True

        def synthesize_raw(self, text, voice, *, language, speed=1.0):
            return b"RIFFfake-kokoro-fallback"

    monkeypatch.setattr(service, "_get_pocket", lambda: FakeUnavailablePocket())
    monkeypatch.setattr(service, "_get_kokoro", lambda: FakeKokoro())

    audio = service.synthesize("Fallback test.", use_cache=False)
    assert audio == b"RIFFfake-kokoro-fallback"


