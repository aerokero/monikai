import os
import re
import sys

import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Audio constants
# ---------------------------------------------------------------------------
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024
SEND_AUDIO_MIME = f"audio/pcm;rate={SEND_SAMPLE_RATE}"

# ---------------------------------------------------------------------------
# Gemini model settings
# ---------------------------------------------------------------------------
MODEL = os.getenv("GEMINI_LIVE_MODEL", "models/gemini-2.5-flash-native-audio-preview-12-2025")
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Sulafat")

try:
    GEMINI_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "-1"))
except Exception:
    GEMINI_THINKING_BUDGET = -1

GEMINI_INCLUDE_THOUGHTS = _env_flag("GEMINI_INCLUDE_THOUGHTS", False)
GEMINI_EMIT_NATIVE_THOUGHT_EVENTS = _env_flag("GEMINI_EMIT_NATIVE_THOUGHT_EVENTS", False)
if not GEMINI_EMIT_NATIVE_THOUGHT_EVENTS:
    GEMINI_INCLUDE_THOUGHTS = False

GEMINI_AFFECTIVE_DIALOG = _env_flag("GEMINI_AFFECTIVE_DIALOG", True)
GEMINI_PROACTIVE_AUDIO = _env_flag("GEMINI_PROACTIVE_AUDIO", True)
GEMINI_CONTEXT_WINDOW_COMPRESSION = _env_flag("GEMINI_CONTEXT_WINDOW_COMPRESSION", True)

try:
    GEMINI_CONTEXT_COMPRESSION_TRIGGER_TOKENS = int(os.getenv("GEMINI_CONTEXT_COMPRESSION_TRIGGER_TOKENS", "0"))
except Exception:
    GEMINI_CONTEXT_COMPRESSION_TRIGGER_TOKENS = 0

try:
    GEMINI_CONTEXT_COMPRESSION_TARGET_TOKENS = int(os.getenv("GEMINI_CONTEXT_COMPRESSION_TARGET_TOKENS", "0"))
except Exception:
    GEMINI_CONTEXT_COMPRESSION_TARGET_TOKENS = 0

GEMINI_SESSION_RESUMPTION = _env_flag("GEMINI_SESSION_RESUMPTION", False)

try:
    GEMINI_VAD_PREFIX_PADDING_MS = int(os.getenv("GEMINI_VAD_PREFIX_PADDING_MS", "60"))
except Exception:
    GEMINI_VAD_PREFIX_PADDING_MS = 60

try:
    GEMINI_VAD_SILENCE_DURATION_MS = int(os.getenv("GEMINI_VAD_SILENCE_DURATION_MS", "3000"))
except Exception:
    GEMINI_VAD_SILENCE_DURATION_MS = 3000

_default_api_version = "v1alpha" if (GEMINI_AFFECTIVE_DIALOG or GEMINI_PROACTIVE_AUDIO) else "v1beta"
GEMINI_API_VERSION = os.getenv("GEMINI_API_VERSION", _default_api_version)

# ---------------------------------------------------------------------------
# Dream / proactivity settings
# ---------------------------------------------------------------------------
try:
    DREAM_SLEEP_GAP_HOURS = float(os.getenv("DREAM_SLEEP_GAP_HOURS", "6"))
except Exception:
    DREAM_SLEEP_GAP_HOURS = 6.0

try:
    DREAM_MORNING_START_HOUR = int(os.getenv("DREAM_MORNING_START_HOUR", "5"))
except Exception:
    DREAM_MORNING_START_HOUR = 5

try:
    DREAM_MORNING_END_HOUR = int(os.getenv("DREAM_MORNING_END_HOUR", "13"))
except Exception:
    DREAM_MORNING_END_HOUR = 13

try:
    DREAM_CONTEXT_HISTORY_LIMIT = int(os.getenv("DREAM_CONTEXT_HISTORY_LIMIT", "20"))
except Exception:
    DREAM_CONTEXT_HISTORY_LIMIT = 20

DEFAULT_MODE = "camera"

# ---------------------------------------------------------------------------
# Gemini client (module-level singleton)
# ---------------------------------------------------------------------------
client = genai.Client(
    http_options={"api_version": GEMINI_API_VERSION},
    api_key=os.getenv("GEMINI_API_KEY"),
)

# ---------------------------------------------------------------------------
# Base session config objects
# ---------------------------------------------------------------------------

def _build_context_window_compression_config():
    if not GEMINI_CONTEXT_WINDOW_COMPRESSION:
        return None
    trigger = int(GEMINI_CONTEXT_COMPRESSION_TRIGGER_TOKENS or 0)
    target = int(GEMINI_CONTEXT_COMPRESSION_TARGET_TOKENS or 0)
    sliding = types.SlidingWindow(target_tokens=target) if target > 0 else types.SlidingWindow()
    if trigger > 0:
        return types.ContextWindowCompressionConfig(
            trigger_tokens=trigger,
            sliding_window=sliding,
        )
    return types.ContextWindowCompressionConfig(sliding_window=sliding)


BASE_CONTEXT_WINDOW_COMPRESSION = _build_context_window_compression_config()

BASE_REALTIME_INPUT_CONFIG = types.RealtimeInputConfig(
    automatic_activity_detection=types.AutomaticActivityDetection(
        disabled=False,
        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
        prefix_padding_ms=GEMINI_VAD_PREFIX_PADDING_MS,
        silence_duration_ms=GEMINI_VAD_SILENCE_DURATION_MS,
    ),
    activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
    turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
)

BASE_PROACTIVITY_CONFIG = types.ProactivityConfig(
    proactive_audio=GEMINI_PROACTIVE_AUDIO,
)

# ---------------------------------------------------------------------------
# Internal thought helpers
# ---------------------------------------------------------------------------
MAX_INTERNAL_THOUGHT_CHARS = 280


def _sanitize_internal_thought(text: str, max_chars: int = MAX_INTERNAL_THOUGHT_CHARS) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return ""
    if max_chars and len(cleaned) > max_chars:
        return cleaned[: max_chars - 3].rstrip() + "..."
    return cleaned
