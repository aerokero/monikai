# src/tts_service.py
"""Multi-provider TTS service with a pronunciation-safe Polish local path."""

import io
import importlib.util
import os
import wave
import logging
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import httpx
from pathlib import Path
from typing import Optional, Dict, Any

from src.constants import TTS_CACHE_DIR

logger = logging.getLogger(__name__)


# Kokoro's language code is part of the model/G2P contract.  Passing an
# English pipeline a Polish sentence does not merely affect the accent: it
# tokenizes the sentence with English phonemes and then renders it with an
# English voice.  Keep this table local to the provider boundary so callers
# never have to know Kokoro's one-letter codes.
KOKORO_LANGUAGE_CODES = {
    "a": "American English",
    "b": "British English",
    "e": "Spanish",
    "f": "French",
    "h": "Hindi",
    "i": "Italian",
    "j": "Japanese",
    "p": "Brazilian Portuguese",
    "z": "Mandarin Chinese",
}
# ``l`` is intentionally kept out of the official table above.  It is a
# local, experimental language layer: Kokoro's acoustic model is reused with
# Polish espeak-ng phonemes mapped onto the stock Kokoro vocabulary.  This is
# not an upstream Polish voice, but it lets Polish use a neural female timbre
# instead of the very synthetic espeak-ng waveform.
KOKORO_EXPERIMENTAL_LANGUAGE_CODES = {
    "l": "Polish (experimental G2P)",
}
KOKORO_LANGUAGE_ALIASES = {
    "en": "a",
    "en-us": "a",
    "en-gb": "b",
    "es": "e",
    "fr": "f",
    "fr-fr": "f",
    "hi": "h",
    "it": "i",
    "ja": "j",
    "pt": "p",
    "pt-br": "p",
    "zh": "z",
    "zh-cn": "z",
}
KOKORO_EXPERIMENTAL_LANGUAGE_ALIASES = {
    "pl": "l",
    "pl-pl": "l",
    "polish": "l",
}

KOKORO_POLISH_CODE = "l"
KOKORO_POLISH_MODE_ENV = "KOKORO_POLISH_MODE"

# Piper has an actual Polish phoneme inventory and a Polish female voice. It
# is used only for local Polish synthesis; Kokoro remains useful for the
# languages it was trained on and remains an optional experimental fallback.
PIPER_POLISH_MODEL_ID = "pl_PL-gosia-medium"
PIPER_MODEL_ID_ENV = "PIPER_MODEL_ID"
PIPER_MODEL_PATH_ENV = "PIPER_MODEL_PATH"
PIPER_MODEL_DIR_ENV = "PIPER_MODEL_DIR"
PIPER_AUTO_DOWNLOAD_ENV = "PIPER_AUTO_DOWNLOAD"
PIPER_USE_CUDA_ENV = "PIPER_USE_CUDA"
PIPER_VOICES_BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main"
)

# Keep this list deliberately explicit.  These are stock female embeddings
# that are known to exist in the official Kokoro v1.0 voice set and therefore
# can be used with the shared model.  They provide the timbre; the Polish G2P
# layer below provides pronunciation.  They are not Polish-trained speakers.
KOKORO_POLISH_EXPERIMENTAL_VOICES = {
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_heart",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
}

# These are deliberately conservative defaults.  A user-selected voice always
# wins when its prefix matches the selected language.  If the stored voice is
# the old generic English default and a supported language is selected, use a
# matching Kokoro voice instead of silently running the wrong voice through a
# different G2P pipeline.  The voice file is downloaded lazily by Kokoro.
KOKORO_DEFAULT_VOICES = {
    "a": "af_heart",
    "b": "bf_emma",
    "e": "ef_dora",
    "f": "ff_siwis",
    "h": "hf_alpha",
    "i": "if_sara",
    "j": "jf_alpha",
    "p": "pf_dora",
    "z": "zf_xiaobei",
    KOKORO_POLISH_CODE: "af_heart",
}
GENERIC_KOKORO_VOICES = {
    "",
    "alloy",
    "af_heart",
    "leda",
    "aoede",
    "kore",
    "sulafat",
    "puck",
    "charon",
    "fenrir",
}

# The official Kokoro-82M v1.0 has no Polish voice.  The experimental layer
# below is opt-in through ``KOKORO_POLISH_MODE=experimental`` and falls back
# to the pronunciation-correct local espeak-ng path if it cannot be
# initialized or synthesized. Keeping espeak as the default is intentional:
# a correct Polish pronunciation is preferable to an attractive but wrong
# English phoneme approximation.
ESPEAK_LANGUAGE_ALIASES = {
    "a": "en-us",
    "b": "en-gb",
    "e": "es",
    "f": "fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt-br",
    "z": "cmn",
    "en": "en-us",
    "en-us": "en-us",
    "en-gb": "en-gb",
    "pl": "pl",
    "polish": "pl",
    "de": "de",
    "german": "de",
    "nl": "nl",
    "dutch": "nl",
    "ru": "ru",
    "russian": "ru",
    "uk": "uk",
    "ukrainian": "uk",
    "cs": "cs",
    "czech": "cs",
    "sk": "sk",
    "sl": "sl",
    "sv": "sv",
    "da": "da",
    "no": "no",
    "fi": "fi",
    "tr": "tr",
    "ro": "ro",
}


def _kokoro_polish_mode() -> str:
    """Return the local Polish rendering mode.

    ``experimental`` uses the neural Kokoro acoustic model with Polish G2P;
    ``espeak``/``off`` disables it and preserves the old pronunciation-first
    fallback.  Reading the variable per request makes switching modes during
    a running process safe for diagnostics and cache invalidation.
    """
    value = os.getenv(KOKORO_POLISH_MODE_ENV, "espeak").strip().lower()
    if value in {"espeak", "fallback", "off", "disabled", "false", "0"}:
        return "espeak"
    return "experimental"


def normalize_tts_language(value: Any) -> str:
    """Normalize an app language setting without guessing unknown values."""
    normalized = str(value or "auto").strip().lower().replace("_", "-")
    return normalized or "auto"


def kokoro_language_for_voice(voice: str) -> Optional[str]:
    """Return Kokoro's language code encoded in a voice id, if present."""
    candidate = str(voice or "").strip().lower().split(",", 1)[0]
    if not candidate:
        return None
    prefix = candidate.split("_", 1)[0]
    # Kokoro voice ids use a two-character gender/language prefix for most
    # languages (af_, ff_, pf_, ...), while the language itself is its first
    # character.  Accept a bare language code as well for API callers.
    code = prefix[:1]
    if code in KOKORO_LANGUAGE_CODES:
        return code
    return prefix if prefix in KOKORO_LANGUAGE_CODES else None


def detect_text_language(text: str) -> str:
    """Detect only high-confidence scripts/diacritics used by local TTS.

    This is intentionally not a general language detector.  It prevents the
    common Polish case (including ``ąęłńóśźż``) from being sent through the
    English Kokoro G2P while leaving ambiguous ASCII text to the configured
    voice/language.
    """
    value = str(text or "")
    if re.search(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", value):
        return "pl"
    # A short Polish sentence is often written without diacritics (for
    # example, "To jest test"). A script/diacritic-only detector then sends
    # it through the configured English voice. Require two common Polish
    # markers so ordinary English text containing a single "to" is not
    # misclassified.
    ascii_markers = {
        "ale",
        "czy",
        "dla",
        "jest",
        "mam",
        "masz",
        "nie",
        "oraz",
        "to",
        "tobie",
        "twoj",
        "wiem",
        "zeby",
    }
    words = set(re.findall(r"[a-ząćęłńóśźż]+", value.casefold()))
    if len(words & ascii_markers) >= 2:
        return "pl"
    if re.search(r"[\u3040-\u30ff]", value):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", value):
        return "zh"
    if re.search(r"[\u0900-\u097f]", value):
        return "hi"
    return "auto"


def _kokoro_code(language: str) -> Optional[str]:
    normalized = normalize_tts_language(language)
    if normalized == "auto":
        return None
    if (
        _kokoro_polish_mode() == "experimental"
        and normalized in KOKORO_EXPERIMENTAL_LANGUAGE_ALIASES
    ):
        return KOKORO_EXPERIMENTAL_LANGUAGE_ALIASES[normalized]
    if normalized in KOKORO_LANGUAGE_CODES:
        return normalized
    return KOKORO_LANGUAGE_ALIASES.get(normalized)


def _espeak_voice(language: str) -> Optional[str]:
    normalized = normalize_tts_language(language)
    if normalized == "auto":
        return None
    fallback = (
        normalized
        if re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", normalized)
        else None
    )
    return ESPEAK_LANGUAGE_ALIASES.get(normalized, fallback)


def _voice_for_kokoro_language(voice: str, language_code: str) -> Optional[str]:
    """Keep a configured voice and G2P language in the same language."""
    selected = str(voice or "").strip()

    if language_code == KOKORO_POLISH_CODE:
        # Polish experimental G2P is intentionally decoupled from the stock
        # voice language prefix: the acoustic model supplies a female timbre,
        # while the custom G2P supplies Polish phonemes.  Do not accept an
        # arbitrary external voice/path here; only known stock female voices
        # are safe to use with the shared Kokoro checkpoint.
        selected_voices = [part.strip().lower() for part in selected.split(",") if part.strip()]
        if not selected_voices or selected.lower() in GENERIC_KOKORO_VOICES:
            return KOKORO_DEFAULT_VOICES[KOKORO_POLISH_CODE]
        if all(part in KOKORO_POLISH_EXPERIMENTAL_VOICES for part in selected_voices):
            return selected
        return None

    current_code = kokoro_language_for_voice(selected)
    if current_code == language_code:
        return selected or KOKORO_DEFAULT_VOICES.get(language_code)
    if current_code is None and selected.lower() not in GENERIC_KOKORO_VOICES:
        # Keep explicit local voice paths/ids intact; Kokoro will validate them.
        return selected or KOKORO_DEFAULT_VOICES.get(language_code)
    if selected.lower() in GENERIC_KOKORO_VOICES:
        return KOKORO_DEFAULT_VOICES.get(language_code)
    # An explicitly selected voice from another language should not be
    # silently mispronounced.  Let the caller use the local pronunciation
    # fallback (or its configured cloud fallback) instead.
    return None


# Kokoro's 178-symbol vocabulary does not contain every Polish phoneme.  These
# substitutions mirror the small, tested mapping used by the community
# ``kokoro-pl`` experiment: affricates are handled first, then the one Polish
# fricative that has no direct symbol.  The acoustic model remains Kokoro, so
# this is still an approximation rather than a Polish-trained voice.
_POLISH_KOKORO_PHONEME_MAP = (
    ("dʑ", "ʥ"),
    ("tɕ", "ʨ"),
    ("dʒ", "ʤ"),
    ("tʃ", "ʧ"),
    ("dz", "ʣ"),
    ("ts", "ʦ"),
    ("ʑ", "ʒʲ"),
)


def _map_polish_kokoro_phonemes(phonemes: str) -> str:
    """Map espeak-ng Polish IPA to symbols present in Kokoro's vocabulary."""
    mapped = phonemes
    for source, replacement in _POLISH_KOKORO_PHONEME_MAP:
        mapped = mapped.replace(source, replacement)
    return mapped


def _piper_model_id() -> str:
    return str(os.getenv(PIPER_MODEL_ID_ENV, PIPER_POLISH_MODEL_ID) or PIPER_POLISH_MODEL_ID).strip()


def _piper_model_path() -> Path:
    configured = str(os.getenv(PIPER_MODEL_PATH_ENV, "") or "").strip()
    if configured:
        return Path(configured)
    model_dir = str(
        os.getenv(
            PIPER_MODEL_DIR_ENV,
            str(Path(TTS_CACHE_DIR).parent / "tts" / "piper"),
        )
        or str(Path(TTS_CACHE_DIR).parent / "tts" / "piper")
    )
    return Path(model_dir) / f"{_piper_model_id()}.onnx"


def _piper_auto_download() -> bool:
    value = str(os.getenv(PIPER_AUTO_DOWNLOAD_ENV, "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _piper_use_cuda() -> bool:
    value = str(os.getenv(PIPER_USE_CUDA_ENV, "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


_PIPER_DOWNLOAD_LOCK = threading.Lock()


def _piper_voice_urls(model_id: str) -> tuple[str, str]:
    """Build the official Piper voice URLs from a voice id."""
    parts = str(model_id or "").split("-")
    if len(parts) < 3 or "_" not in parts[0]:
        raise ValueError(f"Unsupported Piper model id: {model_id!r}")
    locale, voice_name, quality = parts[0], parts[1], "-".join(parts[2:])
    language = locale.split("_", 1)[0]
    relative = f"{language}/{locale}/{voice_name}/{quality}/{model_id}"
    return (
        f"{PIPER_VOICES_BASE_URL}/{relative}.onnx",
        f"{PIPER_VOICES_BASE_URL}/{relative}.onnx.json",
    )


class _PiperPipeline:
    """Lazy local Piper renderer for a pronunciation-correct Polish voice."""

    def __init__(self):
        self.voice = None
        self.model_path = _piper_model_path()
        self.available = False
        self._init()

    def _download_model(self) -> bool:
        model_id = _piper_model_id()
        if not model_id.lower().startswith("pl_"):
            logger.warning(
                "Piper model %r is not a Polish voice; refusing it for Polish TTS",
                model_id,
            )
            return False
        try:
            model_url, config_url = _piper_voice_urls(model_id)
        except ValueError as exc:
            logger.warning("Piper model configuration is invalid: %s", exc)
            return False

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        config_path = Path(f"{self.model_path}.json")
        with _PIPER_DOWNLOAD_LOCK:
            if self.model_path.exists() and config_path.exists():
                return True
            logger.info("Downloading Piper voice %s (about 63 MB)...", model_id)
            try:
                for url, destination in (
                    (model_url, self.model_path),
                    (config_url, config_path),
                ):
                    if destination.exists():
                        continue
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        prefix=f".{destination.name}.",
                        suffix=".download",
                        dir=str(destination.parent),
                        delete=False,
                    ) as temporary:
                        temporary_path = Path(temporary.name)
                        total = 0
                        with httpx.stream(
                            "GET",
                            url,
                            follow_redirects=True,
                            timeout=httpx.Timeout(180.0, connect=20.0),
                        ) as response:
                            response.raise_for_status()
                            for chunk in response.iter_bytes(1024 * 1024):
                                total += len(chunk)
                                if total > 300 * 1024 * 1024:
                                    raise RuntimeError("Piper voice download exceeded the safety limit")
                                temporary.write(chunk)
                    temporary_path.replace(destination)
            except Exception as exc:
                logger.warning("Piper voice download failed: %s", exc)
                for partial in self.model_path.parent.glob(f".{self.model_path.name}.*.download"):
                    try:
                        partial.unlink()
                    except OSError:
                        pass
                config_partial = self.model_path.parent / f".{config_path.name}.*.download"
                for partial in self.model_path.parent.glob(config_partial.name):
                    try:
                        partial.unlink()
                    except OSError:
                        pass
                return False
        return self.model_path.exists() and config_path.exists()

    def _init(self):
        try:
            from piper import PiperVoice
        except ImportError as exc:
            logger.info("Piper TTS is not installed: %s", exc)
            return

        if not _piper_model_id().lower().startswith("pl_"):
            logger.warning(
                "Piper model %r is not a Polish voice; local Polish TTS is disabled",
                _piper_model_id(),
            )
            return

        if not self.model_path.exists() or not Path(f"{self.model_path}.json").exists():
            if not _piper_auto_download() or not self._download_model():
                logger.info(
                    "Piper Polish voice is not present at %s; using another local fallback",
                    self.model_path,
                )
                return

        try:
            try:
                self.voice = PiperVoice.load(
                    str(self.model_path),
                    use_cuda=_piper_use_cuda(),
                )
            except TypeError:
                # Compatibility with older piper-tts releases.
                self.voice = PiperVoice.load(str(self.model_path))
            self.available = self.voice is not None
            if self.available:
                logger.info("Piper Polish voice loaded: %s", self.model_path)
        except Exception as exc:
            logger.warning("Piper Polish voice failed to load: %s", exc)
            self.voice = None

    def synthesize_raw(self, text: str, speed: float = 1.0) -> Optional[bytes]:
        if not self.available or self.voice is None:
            return None
        try:
            from piper.config import SynthesisConfig

            # Piper's length_scale is inverse speed: lower values speak faster.
            synthesis_config = SynthesisConfig(
                length_scale=max(0.5, min(2.0, 1.0 / max(0.5, float(speed))))
            )
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as output:
                self.voice.synthesize_wav(
                    str(text)[:5000],
                    output,
                    syn_config=synthesis_config,
                )
            return buffer.getvalue()
        except Exception as exc:
            logger.warning("Piper Polish synthesis failed: %s", exc)
            return None


class _PolishKokoroG2P:
    """Polish espeak-ng G2P with the Kokoro vocabulary compatibility map."""

    def __init__(self):
        from misaki.espeak import EspeakG2P

        self.backend = EspeakG2P(language="pl")

    def __call__(self, text):
        phonemes, tokens = self.backend(text)
        return _map_polish_kokoro_phonemes(phonemes), tokens


def _register_polish_kokoro_language() -> None:
    """Register the private one-letter language code used by KPipeline."""
    from kokoro.pipeline import ALIASES, LANG_CODES

    LANG_CODES.setdefault(KOKORO_POLISH_CODE, "pl")
    ALIASES.setdefault("pl", KOKORO_POLISH_CODE)
    ALIASES.setdefault("pl-pl", KOKORO_POLISH_CODE)


def _safe_speed(value, default: float = 1.0) -> float:
    """Parse the stored tts_speed defensively. The settings layer tolerates
    corrupt/agent-written config, so a non-numeric or empty value (e.g. an agent
    setting "speech speed" = "fast", or a hand-edited settings.json) must not
    crash synthesis or the stats endpoint with a ValueError."""
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return default
    return speed if speed > 0 else default


class TTSService:
    """Multi-provider TTS service.

    Reads provider config from data/settings.json on each call.
    Providers:
      "disabled"        — no TTS
      "browser"         — client-side Web Speech API (no server synthesis)
      "local"           — Piper Polish voice, Kokoro for supported languages,
                          and espeak-ng as a pronunciation-safe fallback
      "endpoint:<id>"   — OpenAI-compatible /audio/speech via ModelEndpoint
    """

    def __init__(self, cache_dir: str = TTS_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._kokoro = None  # lazy-init
        self._piper = None  # lazy-init; loaded only for Polish synthesis

        try:
            self.max_cache_bytes = int(os.getenv("ODYSSEUS_TTS_CACHE_MAX_BYTES", 500 * 1024 * 1024))
        except ValueError:
            self.max_cache_bytes = 500 * 1024 * 1024

    # ── Settings ──

    def _load_settings(self) -> dict:
        from src.settings import load_settings
        saved = load_settings()
        provider = str(saved.get("tts_provider", "disabled") or "disabled").strip().lower()
        model = str(saved.get("tts_model", "tts-1") or "tts-1").strip()
        voice = str(saved.get("tts_voice", "alloy") or "alloy").strip()
        language = normalize_tts_language(saved.get("tts_language", "auto"))

        # Profiles written by the earlier Kokoro Polish experiment commonly
        # contain local + auto + af_heart. Treat that exact legacy shape as
        # Polish so a short ASCII reply cannot fall back to English G2P after
        # the upgrade. Users can still select another language explicitly.
        if (
            provider == "local"
            and language == "auto"
            and voice.lower() in KOKORO_POLISH_EXPERIMENTAL_VOICES
        ):
            model = "Piper"
            voice = PIPER_POLISH_MODEL_ID
            language = "pl"
        return {
            "tts_enabled": saved.get("tts_enabled", True),
            "tts_provider": provider,
            "tts_model": model,
            "tts_voice": voice,
            "tts_speed": saved.get("tts_speed", "1"),
            # ``auto`` follows an explicit language when supplied and otherwise
            # uses high-confidence text detection (Polish diacritics/scripts).
            "tts_language": language,
        }

    @property
    def available(self) -> bool:
        settings = self._load_settings()
        if settings.get("tts_enabled") is False:
            return False
        provider = settings["tts_provider"]
        if provider == "disabled":
            return False
        if provider == "browser":
            return True  # handled client-side
        if provider == "local":
            # The actual Piper model is loaded on first synthesis. Reporting
            # the package as capable here keeps the voice channel enabled
            # without downloading a 63 MB model from a status endpoint.
            piper_installed = importlib.util.find_spec("piper") is not None
            if piper_installed:
                return True
            kokoro = self._get_kokoro()
            # Polish (and other languages without a Kokoro voice) can still be
            # rendered locally through the image's espeak-ng fallback.
            return (
                piper_installed
                or (kokoro is not None and kokoro.available)
                or bool(shutil.which("espeak-ng"))
            )
        if isinstance(provider, str) and provider.startswith("endpoint:"):
            return True  # assume reachable; errors surface at synthesis time
        return False

    # ── Cache ──

    def _cache_key(
        self,
        text: str,
        provider: str,
        model: str,
        voice: str,
        speed: float = 1.0,
        language: str = "auto",
    ) -> str:
        # Language is part of the audio identity.  Without it, a Polish
        # fallback could reuse an earlier English rendering of the same text.
        # Version the key because older builds did not include language and
        # could have cached a Polish sentence rendered by English Kokoro.
        # Include the Polish mode as well so switching between the experimental
        # neural path and espeak cannot return stale audio from the other path.
        raw = (
            f"v4|{provider}|{model}|{voice}|{speed}|{language}|"
            f"{_kokoro_polish_mode()}|{_piper_model_id()}|{text}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[bytes]:
        for ext in (".mp3", ".wav"):
            path = self.cache_dir / f"{key}{ext}"
            if path.exists():
                return path.read_bytes()
        return None

    def _put_cache(self, key: str, data: bytes):
        ext = ".mp3" if (len(data) >= 3 and (data[:3] == b'ID3' or (data[0] == 0xff and (data[1] & 0xe0) == 0xe0))) else ".wav"
        (self.cache_dir / f"{key}{ext}").write_bytes(data)

        self._enforce_cache_limit()

    def _enforce_cache_limit(self):
            """Evicts oldest files if the cache exceeds the configured byte limit."""
            if self.max_cache_bytes <= 0:
                return

            try:
                files = []
                total_size = 0

                # Safely scan files and sum sizes, ignoring files deleted mid-scan
                for f in self.cache_dir.iterdir():
                    try:
                        if f.is_file() and f.suffix.lower() in (".mp3", ".wav"):
                            files.append(f)
                            total_size += f.stat().st_size
                    except OSError:
                        continue

                if total_size > self.max_cache_bytes:
                    logger.info(
                        f"TTS cache ({total_size} bytes) exceeded limit ({self.max_cache_bytes} bytes). Evicting oldest files."
                    )

                    # Sort files by modification time (oldest first)
                    try:
                        files.sort(key=lambda f: f.stat().st_mtime)
                    except OSError as e:
                        logger.warning(f"Failed to sort cache files by mtime: {e}")

                    # Trim down to 80% of max capacity
                    target_size = self.max_cache_bytes * 0.8

                    while files and total_size > target_size:
                        f = files.pop(0)
                        try:
                            size = f.stat().st_size
                            f.unlink()
                            total_size -= size
                        except OSError as e:
                            logger.warning(f"Failed to evict cache file {f}: {e}")
                            continue

            except Exception as e:
                logger.warning(f"Error enforcing TTS cache limit: {e}", exc_info=True)

    def clear_cache(self):
        count = 0
        for f in self.cache_dir.glob("*.*"):
            f.unlink()
            count += 1
        logger.info(f"Cleared {count} cached TTS files")

    # ── Kokoro (local) ──

    def _get_kokoro(self):
        if self._kokoro is None:
            self._kokoro = _KokoroPipeline()
        return self._kokoro

    def _get_piper(self):
        if self._piper is None:
            self._piper = _PiperPipeline()
        return self._piper

    # ── API endpoint ──

    def _synthesize_api(self, text: str, endpoint_id: str, model: str, voice: str, speed: float = 1.0) -> Optional[bytes]:
        from src.database import SessionLocal, ModelEndpoint

        db = SessionLocal()
        try:
            ep = db.query(ModelEndpoint).filter(ModelEndpoint.id == endpoint_id).first()
            if not ep:
                logger.error(f"TTS endpoint {endpoint_id} not found")
                return None
            base_url = ep.base_url.rstrip("/")
            api_key = ep.api_key
        finally:
            db.close()

        url = base_url + "/audio/speech"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": "mp3",
            "speed": speed,
        }

        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            logger.info(f"API TTS: {len(r.content)} bytes from {base_url}")
            return r.content
        except Exception as e:
            logger.error(f"API TTS synthesis failed: {e}")
            return None

    # ── Public interface ──

    def _resolve_language(self, text: str, requested: Optional[str], voice: str) -> str:
        configured = normalize_tts_language(requested)
        if configured != "auto":
            if configured == "pl-pl":
                return "pl"
            return configured

        detected = detect_text_language(text)
        if detected != "auto":
            return detected

        # For ASCII-only text there is no safe statistical guess.  Keep the
        # configured Kokoro voice as the source of truth in that case.
        # A Piper locale is not a Kokoro language prefix (``pl`` would
        # otherwise be mistaken for Portuguese because Kokoro uses ``p``).
        if str(voice or "").lower().startswith("pl_pl-"):
            return "pl"
        return kokoro_language_for_voice(voice) or "auto"

    @staticmethod
    def _resample_wav_to_24khz(audio: bytes) -> Optional[bytes]:
        """Normalize an espeak WAV to the 24 kHz mono PCM contract."""
        try:
            with wave.open(io.BytesIO(audio), "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                source_rate = source.getframerate()
                frames = source.readframes(source.getnframes())
            if channels != 1 or sample_width != 2 or not frames:
                return None

            try:
                import numpy as np
            except ImportError:
                # espeak-ng is deliberately usable without the heavyweight
                # neural-TTS dependencies. Python 3.11 has audioop, but it
                # was removed in Python 3.13, so keep a small standard-library
                # linear resampler for newer/minimal installations too.
                try:
                    import audioop
                except ImportError:
                    from array import array

                    samples = array("h")
                    samples.frombytes(frames)
                    if sys.byteorder != "little":
                        samples.byteswap()
                    target_len = max(1, int(round(len(samples) * 24_000 / source_rate)))
                    resampled = array("h", [0]) * target_len
                    source_last = len(samples) - 1
                    for index in range(target_len):
                        position = index * source_rate / 24_000
                        left = min(source_last, int(position))
                        right = min(source_last, left + 1)
                        fraction = position - left
                        value = round(
                            samples[left] + (samples[right] - samples[left]) * fraction
                        )
                        resampled[index] = max(-32768, min(32767, value))
                    if sys.byteorder != "little":
                        resampled.byteswap()
                    frames = resampled.tobytes()
                else:
                    if source_rate != 24_000:
                        frames, _ = audioop.ratecv(
                            frames,
                            sample_width,
                            channels,
                            source_rate,
                            24_000,
                            None,
                        )
            else:
                samples = np.frombuffer(frames, dtype=np.int16)
                if source_rate != 24_000:
                    target_len = max(1, int(round(len(samples) * 24_000 / source_rate)))
                    old_x = np.linspace(0.0, 1.0, len(samples), endpoint=False)
                    new_x = np.linspace(0.0, 1.0, target_len, endpoint=False)
                    frames = np.interp(new_x, old_x, samples).astype(np.int16).tobytes()

            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24_000)
                output.writeframes(frames)
            return buffer.getvalue()
        except (ImportError, ValueError, OSError, wave.Error):
            return None

    def _synthesize_with_espeak(
        self,
        text: str,
        language: str,
        speed: float,
    ) -> Optional[bytes]:
        """Render a pronunciation-correct local fallback for unsupported languages."""
        executable = shutil.which("espeak-ng") or shutil.which("espeak")
        voice = _espeak_voice(language)
        if not executable or not voice:
            return None

        words_per_minute = max(80, min(450, int(round(175 * speed))))
        try:
            result = subprocess.run(
                [
                    executable,
                    "-v",
                    voice,
                    "-s",
                    str(words_per_minute),
                    "--stdout",
                    str(text)[:5000],
                ],
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("espeak-ng TTS fallback failed to start: %s", exc)
            return None

        if result.returncode != 0 or not result.stdout:
            logger.warning(
                "espeak-ng TTS fallback failed for %s: %s",
                language,
                result.stderr.decode("utf-8", errors="replace").strip(),
            )
            return None

        audio = self._resample_wav_to_24khz(result.stdout)
        if audio:
            logger.info("Local espeak-ng TTS fallback used for language=%s", language)
        return audio

    def synthesize(
        self,
        text: str,
        use_cache: bool = True,
        language: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Optional[bytes]:
        settings = self._load_settings()
        if settings.get("tts_enabled") is False:
            return None
        provider = str(provider or settings["tts_provider"] or "disabled").strip().lower()
        model = settings["tts_model"]
        voice = settings["tts_voice"]
        speed = _safe_speed(settings.get("tts_speed", "1"))
        selected_language = self._resolve_language(
            text,
            language if language is not None else settings.get("tts_language", "auto"),
            voice,
        )

        if provider in ("disabled", "browser"):
            return None

        if len(text) > 5000:
            text = text[:5000]

        if use_cache:
            key = self._cache_key(text, provider, model, voice, speed, selected_language)
            cached = self._get_cached(key)
            if cached:
                logger.info(f"TTS cache hit ({len(text)} chars)")
                return cached

        audio_data = None

        if provider == "local":
            # Use a model trained for Polish before considering any
            # cross-language acoustic approximation. Piper's Gosia voice
            # keeps a distinctly feminine timbre while its Polish
            # phonemizer handles Polish letters and word stress natively.
            if selected_language == "pl" and importlib.util.find_spec("piper") is not None:
                piper = self._get_piper()
                if piper and piper.available:
                    piper_audio = piper.synthesize_raw(text, speed)
                    audio_data = (
                        self._resample_wav_to_24khz(piper_audio)
                        if piper_audio
                        else None
                    )

            # Do not initialize the heavyweight English Kokoro pipeline on
            # the normal Polish fallback path. It cannot improve Polish
            # pronunciation unless the experimental mode was explicitly
            # requested.
            if not audio_data and (
                selected_language != "pl" or _kokoro_polish_mode() == "experimental"
            ):
                kokoro = self._get_kokoro()
                if kokoro and kokoro.available:
                    audio_data = kokoro.synthesize_raw(
                        text,
                        voice,
                        language=selected_language,
                    )
                else:
                    logger.warning("Kokoro TTS not available")

            # The experimental Polish path is attempted above.  If it is
            # disabled or fails, do not send Polish through an English voice;
            # use the installed pronunciation fallback instead.
            if not audio_data and _espeak_voice(selected_language):
                audio_data = self._synthesize_with_espeak(text, selected_language, speed)
        elif provider.startswith("endpoint:"):
            endpoint_id = provider.split(":", 1)[1]
            audio_data = self._synthesize_api(text, endpoint_id, model, voice, speed)
        else:
            logger.error(f"Unknown TTS provider: {provider}")
            return None

        if audio_data and use_cache:
            key = self._cache_key(text, provider, model, voice, speed, selected_language)
            self._put_cache(key, audio_data)

        return audio_data

    def synthesize_to_base64(
        self,
        text: str,
        language: Optional[str] = None,
    ) -> Optional[str]:
        import base64
        audio = self.synthesize(text, language=language)
        if audio:
            return base64.b64encode(audio).decode("utf-8")
        return None

    def set_voice(self, voice: str):
        """Legacy no-op — voice is now managed via admin settings."""

    def get_stats(self) -> Dict[str, Any]:
        settings = self._load_settings()
        provider = settings["tts_provider"]
        tts_enabled = settings.get("tts_enabled", True)

        cache_files = list(self.cache_dir.glob("*.wav")) + list(self.cache_dir.glob("*.mp3"))
        cache_size = sum(f.stat().st_size for f in cache_files)

        is_available = self.available and tts_enabled
        stats = {
            "available": is_available,
            "ready": is_available,
            "provider": provider,
            "model": settings["tts_model"],
            "voice": settings["tts_voice"],
            "language": normalize_tts_language(settings.get("tts_language", "auto")),
            "speed": _safe_speed(settings.get("tts_speed", "1")),
            "cache_entries": len(cache_files),
            "cache_size_mb": round(cache_size / (1024 * 1024), 2),
        }

        if provider == "local":
            piper_installed = importlib.util.find_spec("piper") is not None
            kokoro = None if piper_installed else self._get_kokoro()
            stats["model"] = (
                f"Piper ({_piper_model_id()})"
                if piper_installed
                else (
                    "Kokoro-82M (GPU)"
                    if (kokoro and kokoro.available)
                    else (
                        "espeak-ng (Polish fallback)"
                        if shutil.which("espeak-ng") or shutil.which("espeak")
                        else "Kokoro (not loaded)"
                    )
                )
            )
            stats["piper_installed"] = piper_installed
            stats["piper_model"] = _piper_model_id()
            stats["piper_model_path"] = str(_piper_model_path())
            stats["piper_auto_download"] = _piper_auto_download()
            stats["kokoro_languages"] = KOKORO_LANGUAGE_CODES
            stats["kokoro_experimental_languages"] = (
                KOKORO_EXPERIMENTAL_LANGUAGE_CODES
                if _kokoro_polish_mode() == "experimental"
                else {}
            )
            stats["polish_kokoro_mode"] = _kokoro_polish_mode()
            stats["polish_kokoro_voices"] = sorted(KOKORO_POLISH_EXPERIMENTAL_VOICES)
            stats["espeak_fallback"] = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
        elif provider == "browser":
            stats["model"] = "Browser (Web Speech API)"
        elif provider.startswith("endpoint:"):
            stats["endpoint_id"] = provider.split(":", 1)[1]

        return stats


class _KokoroPipeline:
    """Encapsulates the Kokoro-82M local pipeline.

    ``KPipeline`` can run on either CUDA or CPU.  The container normally gets
    the NVIDIA GPU, but keeping an explicit CPU fallback makes the provider
    useful during diagnostics and on machines without the NVIDIA runtime.
    """

    def __init__(self):
        self.pipeline = None
        self.pipelines: Dict[str, Any] = {}
        self._pipeline_factory = None
        self._model = None
        self.available = False
        self.device = None
        self.device_name = None
        self._init()

    def _init(self):
        try:
            import torch
            from kokoro import KPipeline

            configured_device = os.getenv("KOKORO_DEVICE", "auto").strip().lower()
            if configured_device in {"", "auto"}:
                self.device_name = "cuda" if torch.cuda.is_available() else "cpu"
            elif configured_device in {"cuda", "cuda:0"}:
                if not torch.cuda.is_available():
                    raise RuntimeError(
                        "KOKORO_DEVICE=cuda, but CUDA is not available in the container"
                    )
                self.device_name = "cuda"
            elif configured_device == "cpu":
                self.device_name = "cpu"
            else:
                raise ValueError(
                    f"Unsupported KOKORO_DEVICE={configured_device!r}; use auto, cuda, or cpu"
                )

            self.device = torch.device(self.device_name)
            self._pipeline_factory = KPipeline
            # Keep the existing English pipeline as the eagerly loaded default
            # (and share its KModel with all lazily-created language pipelines).
            self.pipeline = KPipeline(lang_code="a", device=self.device_name)
            self.pipelines["a"] = self.pipeline
            self._model = getattr(self.pipeline, "model", None)
            self.available = True
            logger.info("Kokoro-82M TTS pipeline loaded on %s", self.device)
        except ImportError as e:
            logger.warning(f"Kokoro TTS not available: {e}")
            logger.warning("Install with: pip install kokoro soundfile")
        except Exception as e:
            logger.error(f"Kokoro init failed: {e}", exc_info=True)

    def _get_pipeline(self, language_code: str):
        if language_code in self.pipelines:
            return self.pipelines[language_code]
        if self._pipeline_factory is None:
            return None

        if language_code == KOKORO_POLISH_CODE:
            try:
                _register_polish_kokoro_language()
                kwargs = {
                    "lang_code": KOKORO_POLISH_CODE,
                    "device": self.device_name,
                }
                if self._model is not None:
                    kwargs["model"] = self._model
                pipeline = self._pipeline_factory(**kwargs)
                pipeline.g2p = _PolishKokoroG2P()
                self.pipelines[language_code] = pipeline
                logger.info("Kokoro experimental Polish G2P pipeline loaded on %s", self.device)
                return pipeline
            except Exception as exc:
                logger.error(
                    "Kokoro experimental Polish pipeline init failed: %s",
                    exc,
                    exc_info=True,
                )
                return None

        if language_code not in KOKORO_LANGUAGE_CODES:
            return None

        try:
            kwargs = {
                "lang_code": language_code,
                "device": self.device_name,
            }
            # KPipeline accepts a shared KModel.  This avoids loading a full
            # 82M parameter model once per language.
            if self._model is not None:
                kwargs["model"] = self._model
            pipeline = self._pipeline_factory(**kwargs)
            self.pipelines[language_code] = pipeline
            return pipeline
        except Exception as exc:
            logger.error(
                "Kokoro language pipeline init failed for %s: %s",
                language_code,
                exc,
                exc_info=True,
            )
            return None

    def synthesize_raw(
        self,
        text: str,
        voice: str = "af_heart",
        *,
        language: Optional[str] = None,
    ) -> Optional[bytes]:
        if not self.available:
            return None
        try:
            import torch
            import numpy as np

            requested_language = normalize_tts_language(language)
            if requested_language == "auto":
                language_code = kokoro_language_for_voice(voice) or "a"
            else:
                language_code = _kokoro_code(requested_language)
                if language_code is None:
                    logger.info(
                        "Kokoro has no voice/G2P for language=%s; caller will use fallback",
                        requested_language,
                    )
                    return None
            if language_code not in KOKORO_LANGUAGE_CODES and language_code not in KOKORO_EXPERIMENTAL_LANGUAGE_CODES:
                logger.info(
                    "Kokoro has no voice/G2P for language=%s; caller will use fallback",
                    requested_language,
                )
                return None

            selected_voice = _voice_for_kokoro_language(voice, language_code)
            if not selected_voice:
                logger.warning(
                    "Kokoro voice %r does not match language=%s; refusing an English pronunciation fallback",
                    voice,
                    language_code,
                )
                return None

            pipeline = self._get_pipeline(language_code)
            if pipeline is None:
                return None

            with torch.inference_mode():
                chunks = []
                for _, _, audio in pipeline(text, voice=selected_voice):
                    if audio is None:
                        continue
                    if isinstance(audio, torch.Tensor):
                        audio = audio.detach().cpu().numpy()
                    chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))

            if not chunks:
                return None

            full = np.clip(np.concatenate(chunks), -1.0, 1.0)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes((full * 32767).astype(np.int16).tobytes())
            return buf.getvalue()
        except Exception as e:
            logger.error(f"Kokoro synthesis failed: {e}", exc_info=True)
            return None


# Module-level singleton
_tts_service = None

def get_tts_service() -> TTSService:
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
