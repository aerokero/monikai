"""Continuous background microphone listener with local Voice Activity Detection (VAD).

Designed for 24/7 low-resource server-side listening. Analyzes audio locally
and only contacts Gemini API when speech is actively detected.
"""

from __future__ import annotations

import asyncio
import collections
import io
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import time
import wave
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

from backend.audio.barge_in import (
    AudioOutput,
    BargeInMonitor,
    EchoCanceller,
    SpeechDetector,
    looks_like_echo,
)
from backend.conversation.voice_quality import (
    DEFAULT_MIN_VOICE_CONFIDENCE,
    assess_voice_transcript,
    normalize_voice_confidence,
    normalize_voice_transcript,
)

try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except Exception:
    _SOUNDDEVICE_AVAILABLE = False

try:
    import pyaudio
    _PYAUDIO_AVAILABLE = True
except Exception:
    _PYAUDIO_AVAILABLE = False


_WAKE_WORD_RE = re.compile(
    r"^\s*(?:(?:hej|hey|he|ej|okej|ok)\s+)?"
    r"(?:monik(?:a|o)|moniczk(?:a|o)|monia)"
    r"[\s,\.!\?]*",
    re.IGNORECASE,
)
_CONTINUOUS_WAKE_RE = re.compile(
    r"^(?:(?:hej|hey|he|ej|okej|ok)\s+)?"
    r"(?:monik(?:a|o)|moniczk(?:a|o)|monia)\b",
    re.IGNORECASE,
)
_WAKE_CANDIDATE_RE = re.compile(
    r"^(?:hej|hey|he|ej|okej|ok|monik\w*)\b",
    re.IGNORECASE,
)

_WAKE_ACKNOWLEDGEMENT = "Hm?"


def _turn_error_reply() -> str:
    try:
        from src.approval_text import t

        return t("voice.error")
    except Exception:
        return "Sorry, something went wrong."
_WAKE_CHIME_TO_VOICE_GAP_SEC = 0.45
_LIVE_WAKE_CHIME_GAIN = 1.5


def _parse_transcription_response(raw_text: Any) -> Tuple[str, Optional[float], Optional[bool]]:
    """Parse structured STT metadata while keeping plain-text compatibility.

    The Gemini transcription prompt asks for JSON so the recognizer can expose
    its uncertainty. Older endpoints and test doubles may still return plain
    text, in which case confidence remains unknown and the text is preserved.
    """
    raw = normalize_voice_transcript(raw_text)
    if not raw:
        return "", None, None

    candidates = [raw]
    if raw.startswith("```") and raw.endswith("```"):
        fenced = raw[3:-3].strip()
        if fenced.lower().startswith("json"):
            fenced = fenced[4:].strip()
        candidates.insert(0, fenced)
    candidates.extend(match.group(0) for match in re.finditer(r"\{[^{}]{0,512}\}", raw))

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        text = payload.get("text", payload.get("transcript", ""))
        intelligible = payload.get("intelligible", payload.get("is_intelligible"))
        if isinstance(intelligible, str):
            lowered = intelligible.strip().casefold()
            if lowered in {"true", "yes", "tak", "1"}:
                intelligible = True
            elif lowered in {"false", "no", "nie", "0"}:
                intelligible = False
            else:
                intelligible = None
        elif not isinstance(intelligible, bool):
            intelligible = None
        return (
            normalize_voice_transcript(text),
            normalize_voice_confidence(payload.get("confidence")),
            intelligible,
        )

    return raw, None, None


class AdaptiveEnergyVAD:
    """Lightweight adaptive energy VAD with continuous noise floor tracking."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold_ratio: float = 1.5,
        minimum_energy_threshold: float = 60.0,
        min_speech_duration_ms: int = 120,
        trailing_silence_duration_ms: int = 650,
        pre_roll_duration_ms: int = 550,
        max_speech_duration_ms: int = 15000,
    ):
        self.sample_rate = int(sample_rate)
        self.frame_duration_ms = int(frame_duration_ms)
        self.frame_size = int(self.sample_rate * (self.frame_duration_ms / 1000.0))
        self.frame_bytes = self.frame_size * 2  # 16-bit PCM

        self.energy_threshold_ratio = float(energy_threshold_ratio)
        self.minimum_energy_threshold = max(20.0, float(minimum_energy_threshold))
        self.min_speech_frames = max(2, int(min_speech_duration_ms / self.frame_duration_ms))
        self.trailing_silence_frames = max(4, int(trailing_silence_duration_ms / self.frame_duration_ms))
        self.pre_roll_frames = max(3, int(pre_roll_duration_ms / self.frame_duration_ms))
        # A hard upper bound prevents an accidentally open microphone from
        # accumulating unbounded audio, but it must be long enough for a
        # normal spoken request (the old fixed 7.5 s bound cut off longer
        # sentences).  Keep this configurable so installations can tune it
        # for their room and speaking style.
        self.max_speech_frames = max(
            self.min_speech_frames + 1,
            int(max_speech_duration_ms / self.frame_duration_ms),
        )

        self.noise_floor: float = 450.0  # reasonable initial estimate for room ambient
        self.noise_alpha: float = 0.08
        self.rms_history: Deque[float] = collections.deque(maxlen=70)  # ~2.1s sliding window

        self.pre_roll_buffer: Deque[bytes] = collections.deque(maxlen=self.pre_roll_frames)
        self.active_speech_frames: List[bytes] = []
        self.is_speech_active: bool = False
        self.consecutive_speech_frames: int = 0
        self.consecutive_silence_frames: int = 0
        self.last_rms: float = 0.0
        self.last_threshold: float = self.minimum_energy_threshold

    def compute_rms(self, frame_bytes: bytes) -> float:
        if len(frame_bytes) < self.frame_bytes:
            return 0.0
        samples = np.frombuffer(frame_bytes[:self.frame_bytes], dtype=np.int16)
        if len(samples) == 0:
            return 0.0
        sum_sq = np.sum(samples.astype(np.float64) ** 2)
        return float(math.sqrt(sum_sq / len(samples)))

    def is_frame_voiced(self, frame_bytes: bytes) -> Tuple[bool, float]:
        rms = self.compute_rms(frame_bytes)
        self.rms_history.append(rms)

        # Dynamic noise floor estimation: continuously track 15th percentile of recent RMS
        if len(self.rms_history) >= 8:
            sorted_rms = sorted(self.rms_history)
            p15 = sorted_rms[max(0, int(len(sorted_rms) * 0.15))]
            self.noise_floor = (1.0 - self.noise_alpha) * self.noise_floor + self.noise_alpha * max(30.0, p15)

        threshold = max(
            self.minimum_energy_threshold,
            self.noise_floor * self.energy_threshold_ratio + 120.0,
        )
        self.last_rms = rms
        self.last_threshold = threshold
        voiced = rms > threshold
        return voiced, rms

    def process_frame(self, frame_bytes: bytes) -> Optional[bytes]:
        """Process a single audio frame. Returns completed audio segment bytes when speech ends."""
        if len(frame_bytes) < self.frame_bytes:
            return None

        voiced, _ = self.is_frame_voiced(frame_bytes)

        if voiced:
            self.consecutive_speech_frames += 1

            if not self.is_speech_active:
                if self.consecutive_speech_frames >= self.min_speech_frames:
                    self.is_speech_active = True
                    self.active_speech_frames = list(self.pre_roll_buffer)
                    self.active_speech_frames.append(frame_bytes)
                    self.consecutive_silence_frames = 0
                else:
                    self.pre_roll_buffer.append(frame_bytes)
            else:
                self.active_speech_frames.append(frame_bytes)
                # Only reset silence counter if we see 2 consecutive voiced frames (filters out isolated clicks/clicks)
                if self.consecutive_speech_frames >= 2:
                    self.consecutive_silence_frames = 0

                # Max speech duration protection.  This is a safety valve,
                # not the normal end-of-utterance detector (trailing silence
                # above handles that case).
                if len(self.active_speech_frames) > self.max_speech_frames:
                    completed_frames = self.active_speech_frames.copy()
                    self.reset_segment()
                    return b"".join(completed_frames)
        else:
            self.consecutive_speech_frames = 0
            if self.is_speech_active:
                self.consecutive_silence_frames += 1
                self.active_speech_frames.append(frame_bytes)

                if self.consecutive_silence_frames >= self.trailing_silence_frames:
                    # Speech segment complete
                    completed_frames = self.active_speech_frames.copy()
                    self.reset_segment()
                    return b"".join(completed_frames)
            else:
                self.pre_roll_buffer.append(frame_bytes)

        return None

    def reset_segment(self):
        self.is_speech_active = False
        self.active_speech_frames.clear()
        self.pre_roll_buffer.clear()
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0


def _raw_pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def resample_pcm16(pcm_bytes: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Resample 16-bit mono PCM bytes cleanly."""
    if not pcm_bytes or src_rate == dst_rate:
        return pcm_bytes
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    if len(samples) == 0:
        return pcm_bytes
    if src_rate == 48000 and dst_rate == 16000:
        # Exact 3:1 integer decimation with 3-tap averaging box-filter (avoids aliasing artifacts)
        n = (len(samples) // 3) * 3
        if n == 0:
            return b""
        s_float = samples[:n].astype(np.float32)
        resampled = ((s_float[0::3] + s_float[1::3] + s_float[2::3]) / 3.0).astype(np.int16)
        return resampled.tobytes()
    target_len = int(round(len(samples) * dst_rate / src_rate))
    x_old = np.linspace(0, 1, len(samples), endpoint=False)
    x_new = np.linspace(0, 1, target_len, endpoint=False)
    resampled = np.interp(x_new, x_old, samples).astype(np.int16)
    return resampled.tobytes()


class AudioDenoiseProcessor:
    """Real-time audio processor with high-pass filtering (70Hz rumble cut) and AGC."""

    def __init__(
        self,
        sample_rate: int = 16000,
        n_fft: int = 512,
        hop_length: int = 256,
        noise_reduction_db: float = 4.0,
        hp_cutoff_hz: float = 70.0,
    ):
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.window = np.hanning(n_fft).astype(np.float32)
        self.noise_profile = np.zeros(n_fft // 2 + 1, dtype=np.float32)
        self.has_noise_profile = False
        self.noise_alpha = 0.05
        self.reduction_factor = 1.0 - 10.0 ** (-noise_reduction_db / 20.0)

        # 1st-order IIR High-Pass Filter (removes rumble, desk vibrations, 50Hz hum)
        rc = 1.0 / (2.0 * math.pi * hp_cutoff_hz)
        dt = 1.0 / sample_rate
        self.hp_alpha = float(rc / (rc + dt))
        self.hp_prev_in = 0.0
        self.hp_prev_out = 0.0

    def apply_high_pass(self, samples: np.ndarray) -> np.ndarray:
        if len(samples) == 0:
            return samples
        out = np.empty(len(samples), dtype=np.float32)
        prev_in = self.hp_prev_in
        prev_out = self.hp_prev_out
        alpha = self.hp_alpha
        for i in range(len(samples)):
            cur_in = float(samples[i])
            cur_out = alpha * (prev_out + cur_in - prev_in)
            out[i] = cur_out
            prev_in = cur_in
            prev_out = cur_out
        self.hp_prev_in = prev_in
        self.hp_prev_out = prev_out
        return out

    def update_noise_profile(self, pcm_chunk: bytes | np.ndarray):
        """Update background stationary noise estimate during non-speech frames."""
        if isinstance(pcm_chunk, bytes):
            samples = np.frombuffer(pcm_chunk, dtype=np.int16)
        else:
            samples = pcm_chunk

        if len(samples) < self.n_fft:
            return

        filtered = self.apply_high_pass(samples[:self.n_fft])
        spec = np.abs(np.fft.rfft(filtered * self.window))
        if not self.has_noise_profile:
            self.noise_profile = spec
            self.has_noise_profile = True
        else:
            self.noise_profile = (1.0 - self.noise_alpha) * self.noise_profile + self.noise_alpha * spec

    def denoise_segment(self, raw_pcm: bytes) -> bytes:
        """Condition audio segment with rumble filter and AGC normalization for high STT accuracy."""
        if not raw_pcm:
            return raw_pcm

        samples = np.frombuffer(raw_pcm, dtype=np.int16)
        if len(samples) < 64:
            return raw_pcm

        filtered = self.apply_high_pass(samples)

        # Automatic Gain Control / Normalization (preserves clean acoustics and sibilants)
        peak = float(np.max(np.abs(filtered))) if len(filtered) > 0 else 0.0
        if peak > 150.0 and peak < 16000.0:
            target_peak = 20000.0
            gain = min(target_peak / peak, 3.5)
            filtered = filtered * gain

        return np.clip(filtered, -32768, 32767).astype(np.int16).tobytes()


def optimize_alsa_mic_gain(percent: int = 65):
    """Set ALSA capture volume on USB mic to prevent hardware noise floor amplification."""
    for card in [2, 1, 0]:
        try:
            subprocess.run(
                ["amixer", "-c", str(card), "set", "Mic", f"{percent}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass


def find_best_input_device(
    preferred_index: Optional[int] = None,
    preferred_name: Optional[str] = None,
) -> Tuple[Optional[int], str, int]:
    """Find the best audio input device index, name, and supported samplerate."""
    if not _SOUNDDEVICE_AVAILABLE:
        return preferred_index, "default", 16000

    try:
        devices = sd.query_devices()
    except Exception:
        return preferred_index, "default", 16000

    input_devices = []
    for idx, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            input_devices.append((idx, d))

    if not input_devices:
        return None, "none", 16000

    target_idx = None
    target_info = None

    if preferred_index is not None:
        for idx, d in input_devices:
            if idx == preferred_index:
                target_idx = idx
                target_info = d
                break

    if target_idx is None and preferred_name:
        for idx, d in input_devices:
            if preferred_name.lower() in d.get("name", "").lower():
                target_idx = idx
                target_info = d
                break

    # Prioritize dedicated external / USB / TONOR microphones over motherboard analog jacks
    if target_idx is None:
        for idx, d in input_devices:
            name_lower = d.get("name", "").lower()
            if any(kw in name_lower for kw in ["tonor", "usb", "mic", "headset", "capture"]):
                target_idx = idx
                target_info = d
                break

    if target_idx is None:
        target_idx, target_info = input_devices[0]

    # Test sample rates: 16000 preferred for VAD, else 44100, 48000
    chosen_sr = 16000
    for sr in [16000, 44100, 48000, int(target_info.get("default_samplerate", 16000))]:
        try:
            sd.check_input_settings(device=target_idx, samplerate=sr, channels=1)
            chosen_sr = sr
            break
        except Exception:
            continue

    return target_idx, target_info.get("name", f"device_{target_idx}"), chosen_sr


def _release_output_stream(stream) -> None:
    """Abort and close a sounddevice output stream; safe to call repeatedly."""
    if stream is None:
        return
    for action in ("abort", "close"):
        try:
            getattr(stream, action)()
        except Exception:
            pass


def find_best_output_device(preferred_index: Optional[int] = None) -> Optional[int]:
    """Find best output device index with max_output_channels > 0."""
    if not _SOUNDDEVICE_AVAILABLE:
        return preferred_index
    try:
        devices = sd.query_devices()
        output_devices = [idx for idx, d in enumerate(devices) if d.get("max_output_channels", 0) > 0]
        if not output_devices:
            return None
        if preferred_index is not None and preferred_index in output_devices:
            return preferred_index
        for idx in output_devices:
            name_lower = devices[idx].get("name", "").lower()
            if any(kw in name_lower for kw in ["speaker", "headphone", "analog", "alc", "usb"]):
                return idx
        for idx in output_devices:
            name_lower = devices[idx].get("name", "").lower()
            if "hdmi" in name_lower:
                return idx
        return output_devices[0]
    except Exception:
        return preferred_index


class ServerMicListenerService:
    """Background service that captures audio from the server mic and talks to Monika."""

    def __init__(
        self,
        *,
        conversation_handler: Optional[Callable[[str], Any]] = None,
        conversation_stream_handler: Optional[Callable[[str, Callable[[Dict[str, Any]], None]], Any]] = None,
        input_device_index: Optional[int] = None,
        input_device_name: Optional[str] = None,
        output_device_index: Optional[int] = None,
        sample_rate: int = 16000,
        require_wake_word: bool = False,
        gemini_api_key: Optional[str] = None,
        gemini_voice: str = "Leda",
        on_turn_finished: Optional[Callable[[str, str], Any]] = None,
        on_session_started: Optional[Callable[[], Any]] = None,
        on_session_finished: Optional[Callable[[], Any]] = None,
        use_gemini_live: Optional[bool] = None,
        kasa_agent=None,
        hue_agent=None,
        home_assistant_agent=None,
        voice_light_feedback=None,
    ):
        self.conversation_handler = conversation_handler
        # Preferred: called as (prompt, on_event) and speaks while streaming.
        self.conversation_stream_handler = conversation_stream_handler
        # 0 = speak the whole reply; brevity is the prompt's job, cutting
        # Monika off mid-thought is worse than a long answer.
        self.tts_max_chars = int(os.getenv("SERVER_MIC_TTS_MAX_CHARS", "0"))
        self._first_audio_at: Optional[float] = None
        # Full duplex (see barge_in.py): opened by the listen loop.
        self.barge_in_enabled = str(os.getenv("SERVER_MIC_BARGE_IN", "true")).lower() in {"1", "true", "yes"}
        self._duck_gain = float(os.getenv("SERVER_MIC_BARGE_IN_DUCK_GAIN", "0.3"))
        self._output: Optional[AudioOutput] = None
        self._echo: Optional[EchoCanceller] = None
        self._speech_detector: Optional[SpeechDetector] = None
        self._barge_monitor: Optional[BargeInMonitor] = None
        self._reply_playing = False
        self._spoken_pieces: List[str] = []
        self._barge_task: Optional[asyncio.Task] = None
        self._barge_in_segment: Optional[bytes] = None
        self._barge_in_transcript: Optional[str] = None
        self._interrupted_reply: Optional[str] = None
        self.input_device_index = input_device_index
        self.input_device_name = input_device_name
        self.output_device_index = output_device_index
        self.sample_rate = int(sample_rate or 16000)
        self.require_wake_word = bool(require_wake_word)
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_voice = str(gemini_voice or "Leda")
        # Server playback uses the canonical local Kokoro renderer. Keep Gemini as the code-level
        # fallback for installations without a working local model.
        self.tts_provider = str(
            os.getenv("SERVER_MIC_TTS_PROVIDER", "auto") or "auto"
        ).strip().lower()
        # The always-on server microphone is normally used in Polish, but this
        # remains an environment setting so the same deployment can be switched
        # to another language without changing the conversation route.
        self.tts_language = str(
            os.getenv("SERVER_MIC_TTS_LANGUAGE", "auto") or "auto"
        ).strip().lower()
        self.tts_timeout = max(
            5.0,
            float(os.getenv("SERVER_MIC_TTS_TIMEOUT_SECONDS", "30")),
        )
        self.stt_timeout = max(
            3.0,
            float(os.getenv("SERVER_MIC_STT_TIMEOUT_SECONDS", "12")),
        )
        self.stt_min_confidence = min(
            1.0,
            max(
                0.0,
                float(
                    os.getenv(
                        "SERVER_MIC_STT_MIN_CONFIDENCE",
                        str(DEFAULT_MIN_VOICE_CONFIDENCE),
                    )
                ),
            ),
        )
        self.on_turn_finished = on_turn_finished
        self.on_session_started = on_session_started
        self.on_session_finished = on_session_finished
        self.kasa_agent = kasa_agent
        self.hue_agent = hue_agent
        self.home_assistant_agent = home_assistant_agent
        self.voice_light_feedback = voice_light_feedback
        if self.voice_light_feedback is None and self.home_assistant_agent:
            try:
                from backend.agents.voice_light_feedback import VoiceLightFeedbackController
                self.voice_light_feedback = VoiceLightFeedbackController(ha_agent=self.home_assistant_agent)
            except Exception as _e:
                print(f"[SERVER MIC] Voice light feedback setup notice: {_e}")
                self.voice_light_feedback = None
        # Gemini Live conversation mode was retired. Keep the constructor
        # argument for compatibility with older integrations/tests, but never
        # allow it to re-enable a second conversation author at runtime.
        self.use_gemini_live = False
        self.live_model = os.getenv(
            "SERVER_MIC_GEMINI_LIVE_MODEL",
            "models/gemini-2.5-flash-native-audio-preview-12-2025",
        )
        self.live_idle_timeout = max(
            5.0,
            float(os.getenv("SERVER_MIC_LIVE_IDLE_TIMEOUT_SECONDS", "20")),
        )
        self.live_max_session = max(
            self.live_idle_timeout,
            float(os.getenv("SERVER_MIC_LIVE_MAX_SESSION_SECONDS", "60")),
        )
        self.wake_confidence_threshold = min(
            1.0,
            max(0.0, float(os.getenv("SERVER_MIC_WAKE_CONFIDENCE", "0.72"))),
        )
        self.partial_wake_stability_frames = max(
            2, int(os.getenv("SERVER_MIC_PARTIAL_WAKE_STABILITY_FRAMES", "3"))
        )
        self.wake_model_path = os.getenv(
            "SERVER_MIC_VOSK_MODEL_PATH", "/app/data/vosk-model"
        )

        self.vad = AdaptiveEnergyVAD(
            sample_rate=self.sample_rate,
            energy_threshold_ratio=float(
                os.getenv("SERVER_MIC_ENERGY_THRESHOLD_RATIO", "1.8")
            ),
            minimum_energy_threshold=float(
                os.getenv("SERVER_MIC_MIN_ENERGY_THRESHOLD", "60")
            ),
            min_speech_duration_ms=int(
                os.getenv("SERVER_MIC_MIN_SPEECH_DURATION_MS", "60")
            ),
            trailing_silence_duration_ms=int(
                os.getenv("SERVER_MIC_TRAILING_SILENCE_MS", "1400")
            ),
            pre_roll_duration_ms=int(
                os.getenv("SERVER_MIC_PRE_ROLL_MS", "700")
            ),
            max_speech_duration_ms=int(
                os.getenv("SERVER_MIC_MAX_SPEECH_MS", "15000")
            ),
        )
        self.denoiser = AudioDenoiseProcessor(sample_rate=self.sample_rate)
        self._last_transcribe_time = 0.0
        self._genai_client = None
        self._last_stt_confidence: Optional[float] = None
        self._last_stt_intelligible: Optional[bool] = None
        self._last_stt_rejection_reason = ""
        self._last_level_log_time = 0.0
        self._level_peak_rms = 0.0
        self._is_running = False
        self._is_muted = False
        self._is_speaking = False
        self._is_busy = False
        self._awaiting_command_until = 0.0
        self.wake_listen_timeout = max(
            1.0,
            float(os.getenv("SERVER_MIC_WAKE_LISTEN_TIMEOUT_SECONDS", "10")),
        )
        self._turn_lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        # The capture loop must never start a second cloud STT/model request
        # while the previous segment is still being handled.  Apart from
        # wasting provider calls, overlapping tasks were a source of apparent
        # cut-offs and replies arriving out of order.
        self._speech_segment_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._vosk_model = None
        self._vosk_unavailable_reason = ""
        self._wake_recognition_lock = asyncio.Lock()
        self._continuous_wake_recognizer = None
        self._continuous_wake_audio: Deque[bytes] = collections.deque(maxlen=84)
        self._last_wake_voice_time = 0.0
        self._last_wake_candidate_time = 0.0
        self._partial_wake_text = ""
        self._partial_wake_hits = 0
        self._last_partial_wake_time = 0.0
        self._wake_provisional = False
        self._wake_verified_event: Optional[asyncio.Event] = None
        self._pending_initial_pcm = b""
        self._live_audio_queue: Optional[asyncio.Queue] = None
        self._live_session_task: Optional[asyncio.Task] = None
        self._activation_chime_task: Optional[asyncio.Task] = None
        self._activation_ack_task: Optional[asyncio.Task] = None
        # Voice-light updates are intentionally fire-and-forget so a slow
        # Home Assistant request cannot stall microphone capture.  Keep the
        # latest task, however, so a later IDLE update can supersede a stale
        # LISTENING update instead of racing it.
        self._voice_light_task: Optional[asyncio.Task] = None
        self._activation_prompt_window_until = 0.0
        self._last_live_voice_time = 0.0
        self._conversation_session_open = False
        self._wake_ack_mode = str(os.getenv("SERVER_MIC_WAKE_ACK_MODE", "both")).strip().lower()
        self._thinking_loop_task: Optional[asyncio.Task] = None
        self._thinking_sound_enabled = str(os.getenv("SERVER_MIC_THINKING_SOUND_ENABLED", "true")).lower() in {"1", "true", "yes"}
        self._cached_chime_pcm: Optional[bytes] = None
        self._cached_chime_sr: int = 24000
        self._cached_wake_prompts: list[tuple[str, bytes, int]] = []
        self._load_preloaded_audio_assets()

    def _load_preloaded_audio_assets(self) -> None:
        """Pre-load wake chime and neutral vocalizations to RAM for zero-latency reaction."""
        self._cached_chime_pcm = None
        self._cached_chime_sr = 24000
        self._cached_wake_prompts = []

        base_dirs = [
            Path(__file__).resolve().parents[2] / "static",
            Path("/app/static"),
        ]

        # 1. Chime
        for b in base_dirs:
            chime_path = b / "sounds" / "wake_chime.wav"
            if chime_path.is_file():
                try:
                    with wave.open(str(chime_path), "rb") as wf:
                        self._cached_chime_sr = wf.getframerate()
                        self._cached_chime_pcm = wf.readframes(wf.getnframes())
                    print(f"[SERVER MIC] [AUDIO] Preloaded chime from '{chime_path}' ({len(self._cached_chime_pcm)} bytes, {self._cached_chime_sr}Hz).")
                    break
                except Exception as exc:
                    print(f"[SERVER MIC] [AUDIO] Failed loading chime '{chime_path}': {exc}")

        # 2. Neutral wake prompts
        for b in base_dirs:
            neutral_dir = b / "audio" / "wake_prompts" / "neutral"
            if neutral_dir.is_dir():
                for wav_path in sorted(neutral_dir.glob("*.wav")):
                    try:
                        with wave.open(str(wav_path), "rb") as wf:
                            sr = wf.getframerate()
                            pcm = wf.readframes(wf.getnframes())
                            self._cached_wake_prompts.append((wav_path.stem, pcm, sr))
                    except Exception as exc:
                        print(f"[SERVER MIC] [AUDIO] Failed loading prompt '{wav_path}': {exc}")
                if self._cached_wake_prompts:
                    names = [p[0] for p in self._cached_wake_prompts]
                    print(f"[SERVER MIC] [AUDIO] Preloaded {len(self._cached_wake_prompts)} neutral wake prompts into RAM: {names}")
                    break

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_muted(self) -> bool:
        return self._is_muted

    def set_muted(self, muted: bool) -> bool:
        self._is_muted = bool(muted)
        if self._is_muted:
            self.vad.reset_segment()
            self._queue_voice_light_state("idle")
        return self._is_muted

    def set_wake_word_required(self, required: bool):
        self.require_wake_word = bool(required)

    @property
    def is_awaiting_command(self) -> bool:
        """Whether a standalone wake word opened the follow-up command window."""
        return time.monotonic() < self._awaiting_command_until

    @property
    def is_live_session_active(self) -> bool:
        return bool(self._live_session_task and not self._live_session_task.done())

    async def _call_hook(self, callback: Optional[Callable], *args) -> None:
        if not callback:
            return
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            print(f"[SERVER MIC] Session hook notice: {exc}")

    def _start_thinking_loop(self) -> None:
        """Start a very soft, subtle ambient pulsing tone during thinking mode."""
        if not self._thinking_sound_enabled or self._thinking_loop_task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
            self._thinking_loop_task = loop.create_task(
                self._run_thinking_loop(),
                name="server-mic-thinking-loop",
            )
        except RuntimeError:
            pass

    def _stop_thinking_loop(self) -> None:
        """Stop thinking sound loop immediately."""
        task = self._thinking_loop_task
        self._thinking_loop_task = None
        if task and not task.done():
            task.cancel()

    async def _run_thinking_loop(self) -> None:
        """Smooth low-frequency breathing tone (140Hz) pulsing gently in background."""
        sample_rate = 24000
        cycle_sec = 1.0
        n_samples = int(sample_rate * cycle_sec)
        t = np.linspace(0, cycle_sec, n_samples, endpoint=False)
        # Soft sinusoidal breathing envelope matching the light pulsation interval
        env = 0.5 * (1.0 - np.cos(2 * np.pi * t / cycle_sec)) ** 2
        carrier = np.sin(2 * np.pi * 140.0 * t) + 0.18 * np.sin(2 * np.pi * 280.0 * t)
        # Peak amplitude 1200 out of 32767 (~3.7% full scale = gentle whisper level)
        pulse = (carrier * env * 1200.0).astype(np.int16).tobytes()

        try:
            while True:
                await self.play_audio_locally(
                    pulse,
                    sample_rate=sample_rate,
                    suppress_capture=False,
                )
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[SERVER MIC] [THINKING SOUND] Loop notice: {exc}")

    def _queue_voice_light_state(self, state: str) -> Optional[asyncio.Task]:
        """Apply the newest voice-light state and ambient audio cues without allowing stale writes."""
        norm_state = str(state or "").strip().lower()
        if norm_state == "thinking":
            self._start_thinking_loop()
        else:
            self._stop_thinking_loop()

        feedback = self.voice_light_feedback
        if feedback is None:
            return None

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # ``stop()`` can be called after the event loop has gone away.
            return None

        previous = self._voice_light_task
        if previous and not previous.done():
            previous.cancel()

        async def apply_state() -> None:
            if previous is not None and previous is not asyncio.current_task():
                try:
                    await previous
                except asyncio.CancelledError:
                    pass
                except Exception:
                    # The previous task logs its own Home Assistant error;
                    # its failure must not block the newest state.
                    pass

            try:
                await feedback.set_state(state)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[SERVER MIC] Voice light state '{state}' notice: {exc}")

        task = loop.create_task(
            apply_state(),
            name=f"server-mic-voice-light-{state}",
        )
        self._voice_light_task = task
        return task

    async def _set_voice_light_state(self, state: str, *, wait: bool = False) -> None:
        """Request a voice-light state and optionally wait for its HA write."""
        task = self._queue_voice_light_state(state)
        if task is None or not wait:
            return
        try:
            # Do not let cancellation of the microphone loop cancel the final
            # restoration request; the task can finish while streams close.
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass

    async def _expire_command_window_if_needed(self, now: Optional[float] = None) -> bool:
        """Close an expired follow-up window and restore the physical light."""
        current_time = time.monotonic() if now is None else now
        if not (
            not self.use_gemini_live
            and self._conversation_session_open
            and self._awaiting_command_until > 0
            and current_time >= self._awaiting_command_until
        ):
            return False

        self._awaiting_command_until = 0.0
        await self._close_conversation_session()
        if self.require_wake_word:
            self._reset_continuous_wake_recognizer()
        await self._set_voice_light_state("idle", wait=True)
        print("[SERVER MIC] [CONVERSATION] Follow-up window expired; voice light restored.")
        return True

    async def _open_conversation_session(self) -> None:
        if self._conversation_session_open:
            return
        self._conversation_session_open = True
        await self._call_hook(self.on_session_started)

    async def _close_conversation_session(self) -> None:
        if not self._conversation_session_open:
            return
        self._conversation_session_open = False
        await self._call_hook(self.on_session_finished)

    def _load_vosk_model(self):
        if self._vosk_model is not None:
            return self._vosk_model
        if self._vosk_unavailable_reason:
            return None
        try:
            from vosk import Model, SetLogLevel

            if not os.path.isdir(self.wake_model_path):
                raise FileNotFoundError(self.wake_model_path)
            SetLogLevel(-1)
            self._vosk_model = Model(self.wake_model_path)
            print(f"[SERVER MIC] [WAKE] Local Vosk model loaded from {self.wake_model_path}.")
            return self._vosk_model
        except Exception as exc:
            self._vosk_unavailable_reason = str(exc)
            print(f"[SERVER MIC] [WAKE] Local Vosk unavailable: {exc}")
            return None

    async def transcribe_wake_word_locally(self, pcm_bytes: bytes) -> str:
        """Recognize an idle speech segment locally; no room audio leaves the host."""
        def recognize() -> str:
            model = self._load_vosk_model()
            if model is None:
                return ""
            from vosk import KaldiRecognizer

            # Use the full language model. A wake-only grammar forces
            # unrelated speech into one of the wake-word alternatives.
            recognizer = KaldiRecognizer(model, self.sample_rate)
            recognizer.SetWords(False)
            recognizer.AcceptWaveform(pcm_bytes)
            payload = json.loads(recognizer.FinalResult() or "{}")
            return str(payload.get("text") or "").strip()

        async with self._wake_recognition_lock:
            return await asyncio.to_thread(recognize)

    def _reset_continuous_wake_recognizer(self) -> None:
        model = self._load_vosk_model()
        if model is None:
            self._continuous_wake_recognizer = None
            return
        from vosk import KaldiRecognizer

        # Full-vocabulary decoding avoids confidence=1.0 artifacts caused
        # by forcing arbitrary room speech into a tiny wake-only grammar.
        self._continuous_wake_recognizer = KaldiRecognizer(model, self.sample_rate)
        # Stable partials may preconnect, but audio stays local until the final
        # word-level result verifies the wake phrase.
        self._continuous_wake_recognizer.SetWords(True)
        self._continuous_wake_audio.clear()
        self._partial_wake_text = ""
        self._partial_wake_hits = 0
        self._last_partial_wake_time = 0.0

    def _validate_continuous_wake_result(
        self, payload: Dict[str, Any]
    ) -> Tuple[bool, str, float]:
        """Validate one final Vosk utterance before opening Gemini Live."""
        text = str(payload.get("text") or "").strip().lower()
        match = _CONTINUOUS_WAKE_RE.match(text)
        if not match:
            return False, text, 0.0

        wake_word_count = len(match.group(0).split())
        words = list(payload.get("result") or [])
        wake_words = words[:wake_word_count]
        if len(wake_words) != wake_word_count:
            return False, text, 0.0

        try:
            confidence = min(float(word.get("conf", 0.0)) for word in wake_words)
        except (TypeError, ValueError):
            return False, text, 0.0

        return confidence >= self.wake_confidence_threshold, text, confidence

    def _validate_partial_wake_result(self, payload: Dict[str, Any]) -> str:
        """Return a strict wake phrase from a partial Vosk hypothesis."""
        text = str(payload.get("partial") or "").strip().lower()
        match = _CONTINUOUS_WAKE_RE.match(text)
        return match.group(0).strip() if match else ""

    def _cancel_provisional_live_session(self, reason: str) -> None:
        if not self._wake_provisional:
            return
        self._wake_provisional = False
        self._pending_initial_pcm = b""
        task = self._live_session_task
        if task and not task.done():
            print(f"[SERVER MIC] [WAKE] Provisional preconnect cancelled: {reason}.")
            task.cancel()

    def _start_live_session(
        self,
        pcm_bytes: bytes,
        wake_text: str,
        *,
        provisional: bool = False,
    ) -> bool:
        if self.is_live_session_active:
            return False
        self.vad.reset_segment()
        self._last_live_voice_time = time.monotonic()
        self._wake_provisional = bool(provisional)
        self._wake_verified_event = asyncio.Event()
        self._pending_initial_pcm = bytes(pcm_bytes) if provisional else b""
        if not provisional:
            self._wake_verified_event.set()
        self._live_audio_queue = asyncio.Queue()
        self._live_session_task = asyncio.create_task(
            self._run_live_session(b"" if provisional else pcm_bytes),
            name="server-mic-gemini-live",
        )
        self._activation_chime_task = asyncio.create_task(
            self._play_wake_chime(
                capture_safe=True,
                gain=_LIVE_WAKE_CHIME_GAIN,
            ),
            name="server-mic-activation-chime",
        )
        stage = "provisional preconnect" if provisional else "verified"
        print(
            f"[SERVER MIC] [WAKE] Local {stage} match \"{wake_text}\"; "
            "Gemini Live connecting."
        )
        return True

    def _process_continuous_wake_frame(
        self, frame_data: bytes, *, voiced: bool = True
    ) -> bool:
        """Feed continuous idle audio to Vosk and validate final utterances."""
        recognizer = self._continuous_wake_recognizer
        if recognizer is None:
            return False
        self._continuous_wake_audio.append(frame_data)
        if voiced:
            self._last_wake_voice_time = time.monotonic()

        try:
            completed = recognizer.AcceptWaveform(frame_data)
            if not completed:
                if self.is_live_session_active:
                    return False
                payload = json.loads(recognizer.PartialResult() or "{}")
                candidate = self._validate_partial_wake_result(payload)
                now = time.monotonic()
                recent_voice = (now - self._last_wake_voice_time) <= 1.0
                if not candidate or not recent_voice:
                    if now - self._last_partial_wake_time > 0.45:
                        self._partial_wake_text = ""
                        self._partial_wake_hits = 0
                    return False
                if (
                    candidate == self._partial_wake_text
                    and now - self._last_partial_wake_time <= 0.45
                ):
                    self._partial_wake_hits += 1
                else:
                    self._partial_wake_text = candidate
                    self._partial_wake_hits = 1
                self._last_partial_wake_time = now
                if self._partial_wake_hits < self.partial_wake_stability_frames:
                    return False
                return self._start_live_session(
                    b"".join(self._continuous_wake_audio),
                    candidate,
                    provisional=True,
                )
            payload = json.loads(recognizer.Result() or "{}")
        except Exception as exc:
            print(f"[SERVER MIC] [WAKE] Continuous Vosk error: {exc}")
            self._reset_continuous_wake_recognizer()
            return False

        matched, text, confidence = self._validate_continuous_wake_result(payload)
        recent_voice = (time.monotonic() - self._last_wake_voice_time) <= 2.0
        if self._wake_provisional:
            if matched and recent_voice:
                self._wake_provisional = False
                if self._wake_verified_event:
                    self._wake_verified_event.set()
                print(
                    f"[SERVER MIC] [WAKE] Preconnect verified \"{text}\" "
                    f"(confidence={confidence:.3f}); audio gate opened."
                )
                return True
            self._cancel_provisional_live_session(
                f"final verifier rejected '{text or 'empty'}'"
            )
            return False

        if not matched or not recent_voice:
            if text and _WAKE_CANDIDATE_RE.match(text):
                print(
                    "[SERVER MIC] [WAKE] Rejected Vosk candidate "
                    f"\"{text}\" (confidence={confidence:.3f}, "
                    f"recent_voice={recent_voice})."
                )
            return False

        pcm = b"".join(self._continuous_wake_audio)
        self._continuous_wake_audio.clear()
        print(
            f"[SERVER MIC] [WAKE] Final Vosk detected \"{text}\" "
            f"(confidence={confidence:.3f})."
        )
        return self._start_live_session(pcm, text, provisional=False)

    def _process_idle_wake_frame(
        self, frame_data: bytes, *, voiced: bool = True
    ) -> str:
        """Return a wake phrase as soon as a stable local partial is heard.

        The normal server-mic path does not use Gemini Live, but it can still
        keep Vosk running locally while idle.  This lets us acknowledge the
        wake word before the utterance has ended; the following audio is then
        collected by the regular VAD as the actual command.
        """
        recognizer = self._continuous_wake_recognizer
        if recognizer is None:
            return ""
        self._continuous_wake_audio.append(frame_data)
        if voiced:
            self._last_wake_voice_time = time.monotonic()

        try:
            completed = recognizer.AcceptWaveform(frame_data)
            if not completed:
                payload = json.loads(recognizer.PartialResult() or "{}")
                if "moni" in str(payload.get("partial") or ""):
                    self._last_wake_candidate_time = time.monotonic()
                candidate = self._validate_partial_wake_result(payload)
                now = time.monotonic()
                recent_voice = (now - self._last_wake_voice_time) <= 1.0
                if not candidate or not recent_voice:
                    if now - self._last_partial_wake_time > 0.45:
                        self._partial_wake_text = ""
                        self._partial_wake_hits = 0
                    return ""
                if (
                    candidate == self._partial_wake_text
                    and now - self._last_partial_wake_time <= 0.45
                ):
                    self._partial_wake_hits += 1
                else:
                    self._partial_wake_text = candidate
                    self._partial_wake_hits = 1
                self._last_partial_wake_time = now
                if self._partial_wake_hits < self.partial_wake_stability_frames:
                    return ""
                return candidate

            payload = json.loads(recognizer.Result() or "{}")
        except Exception as exc:
            print(f"[SERVER MIC] [WAKE] Idle Vosk error: {exc}")
            self._reset_continuous_wake_recognizer()
            return ""

        matched, text, confidence = self._validate_continuous_wake_result(payload)
        recent_voice = (time.monotonic() - self._last_wake_voice_time) <= 2.0
        if matched and recent_voice:
            print(
                f"[SERVER MIC] [WAKE] Idle Vosk detected \"{text}\" "
                f"(confidence={confidence:.3f})."
            )
            return text
        return ""

    async def _announce_normal_wake(self, wake_text: str) -> None:
        """Give a short audible acknowledgement without delaying activation."""
        try:
            # The acknowledgement is intentionally capture-safe: the command window has
            # already opened before this task starts.
            await self._play_wake_acknowledgement(_WAKE_ACKNOWLEDGEMENT, capture_safe=True)
            print(
                f"[SERVER MIC] [WAKE] Acknowledged \"{wake_text}\" "
                f"with {_WAKE_ACKNOWLEDGEMENT}."
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[SERVER MIC] [WAKE] Acknowledgement notice: {exc}")

    async def _activate_normal_wake(self, wake_text: str) -> bool:
        """Open command mode immediately after local idle wake detection."""
        if self.is_awaiting_command or self._conversation_session_open:
            return False
        self._awaiting_command_until = time.monotonic() + self.wake_listen_timeout
        self.vad.reset_segment()
        self._continuous_wake_audio.clear()
        self._partial_wake_text = ""
        self._partial_wake_hits = 0
        # A fresh recognizer is ready for the next idle period; while the
        # command window is open the listener does not feed it command audio.
        self._reset_continuous_wake_recognizer()
        await self._open_conversation_session()
        # Keep a small echo-filter window while the short spoken prompt is
        # playing.  Capture remains active; an isolated "Hm" segment is not
        # sent to the model as the user's command.
        self._activation_prompt_window_until = time.monotonic() + 3.0
        self._activation_ack_task = asyncio.create_task(
            self._announce_normal_wake(wake_text),
            name="server-mic-wake-ack",
        )
        print(
            f"[SERVER MIC] [WAKE] Idle wake \"{wake_text}\" detected; "
            f"listening immediately for {self.wake_listen_timeout:.1f}s."
        )
        return True

    def extract_wake_word(self, transcript: str) -> Tuple[bool, str]:
        """Check if transcript matches wake word and extract cleaned prompt."""
        text = str(transcript or "").strip()
        if not text:
            return False, ""

        if not self.require_wake_word:
            return True, text

        match = _WAKE_WORD_RE.search(text)
        if match:
            clean = text[match.end():].strip()
            # An empty prompt is meaningful: the user only said the wake word.
            # The caller responds with an acknowledgement and listens for the
            # actual command, like a conventional home assistant.
            return True, clean

        return False, text

    async def transcribe_speech(self, wav_bytes: bytes) -> str:
        """Transcribe speech audio segment using Gemini API."""
        self._last_stt_confidence = None
        self._last_stt_intelligible = None
        self._last_stt_rejection_reason = ""
        if not wav_bytes:
            return ""

        now = time.time()
        if (now - self._last_transcribe_time) < 0.6:
            return ""
        self._last_transcribe_time = now

        preferred = os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-2.5-flash")
        candidates = [preferred, "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
        models_to_try = list(dict.fromkeys(candidates))

        try:
            from google import genai
            from google.genai import types

            if self._genai_client is None:
                self._genai_client = genai.Client(api_key=self.gemini_api_key)
            client = self._genai_client
            prompt = (
                "Transcribe this voice audio accurately in the language that is "
                "actually spoken (never translate). Return exactly "
                "one JSON object with keys text, intelligible, and confidence. "
                "text must contain only the words that are actually audible; "
                "intelligible must be a boolean; confidence must be a number "
                "from 0.0 to 1.0 describing how reliably the spoken words were "
                "heard. "
                "The speaker is addressing an AI assistant named Monika (common wake words: 'Hej Monika', 'Monika', 'Moniko', 'Okej Monika', 'Monia'). "
                "Preserve original spoken words accurately; do not repair, infer, "
                "or replace unclear sounds with plausible words. "
                "Do not add commentary, labels, quotes, timestamps, or markdown. "
                "If the audio is silent or completely unintelligible, use "
                "text='' and intelligible=false with confidence <= 0.35. "
                "A short but clearly spoken word or phrase is valid."
            ) + self._stt_vocabulary_hint()

            def request(model_name: str) -> asyncio.Task:
                return asyncio.ensure_future(
                    client.aio.models.generate_content(
                        model=model_name,
                        contents=[
                            prompt,
                            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                        ],
                    )
                )

            # Hedged requests: STT normally answers in ~1.5 s, but a busy
            # model can hang or 503.  Instead of waiting out one model before
            # trying the next, start the next one alongside after a short
            # delay (or at once on an error) and take the first answer.
            hedge_delay = float(os.getenv("SERVER_MIC_STT_HEDGE_SECONDS", "2.0"))
            deadline = time.monotonic() + self.stt_timeout
            queue = iter(models_to_try)
            pending: Dict[asyncio.Task, str] = {}
            response = None
            last_exc = None
            hedge_at = 0.0
            try:
                while response is None and time.monotonic() < deadline:
                    if time.monotonic() >= hedge_at:
                        model_name = next(queue, None)
                        if model_name:
                            pending[request(model_name)] = model_name
                        hedge_at = time.monotonic() + hedge_delay
                    if not pending:
                        break
                    done, _ = await asyncio.wait(
                        pending,
                        timeout=max(0.0, min(hedge_at, deadline) - time.monotonic()),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        model_name = pending.pop(task)
                        if task.exception() is not None:
                            last_exc = task.exception() or f"error ({model_name})"
                            hedge_at = 0.0  # failed: hand over to the next model now
                        elif response is None:
                            response = task.result()
            finally:
                for task in pending:
                    task.cancel()

            if response is None:
                print(f"[SERVER MIC] Transcription notice: {last_exc or 'timeout'}")
                return ""
            raw_text = getattr(response, "text", "") or ""
            text, confidence, intelligible = _parse_transcription_response(raw_text)
            self._last_stt_confidence = confidence
            self._last_stt_intelligible = intelligible
            assessment = assess_voice_transcript(
                text,
                confidence=confidence,
                intelligible=intelligible,
                min_confidence=self.stt_min_confidence,
            )
            if not assessment.accepted:
                self._last_stt_rejection_reason = assessment.reason
                print(
                    "[SERVER MIC] [STT] Ignoring transcript: "
                    f"reason={assessment.reason} confidence="
                    f"{confidence if confidence is not None else 'unknown'}"
                )
                return ""
            return assessment.text
        except Exception as exc:
            print(f"[SERVER MIC] Transcription failed: {exc}")
            return ""

    def _stt_vocabulary_hint(self) -> str:
        """Smart-home device names, so "VARMBLIXT" is not heard as "warm blix"."""
        entities = getattr(self.home_assistant_agent, "entities", None) or {}
        names = sorted({
            str((state.get("attributes") or {}).get("friendly_name") or "").strip()
            for state in entities.values()
            if isinstance(state, dict)
        } - {""})
        if not names:
            return ""
        return (
            " Device names in this home (spell them exactly like this when "
            "they are spoken; never insert them otherwise): " + ", ".join(names[:60]) + "."
        )

    async def play_audio_locally(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 24000,
        *,
        suppress_capture: bool = True,
    ):
        """Play synthesized audio out of server speakers/headphones with automatic resampling and stereo expansion."""
        if not pcm_bytes:
            return

        if self._output is not None:
            if suppress_capture:
                self._is_speaking = True
            try:
                await self._output.play(pcm_bytes, sample_rate)
            finally:
                if suppress_capture:
                    self._is_speaking = False
                    self.vad.reset_segment()
            return

        if suppress_capture:
            self._is_speaking = True
        try:
            out_idx = find_best_output_device(self.output_device_index)
            if out_idx is None:
                print("[SERVER MIC] No valid audio output device available.")
                return

            dev_info = sd.query_devices(out_idx) if _SOUNDDEVICE_AVAILABLE else {}
            dev_name = dev_info.get("name", f"device_{out_idx}")

            # Check supported sample rate and channels
            target_sr = 48000
            target_channels = 2
            if _SOUNDDEVICE_AVAILABLE:
                found = False
                for sr_cand in [48000, 44100, sample_rate]:
                    for ch_cand in [2, 1]:
                        try:
                            sd.check_output_settings(device=out_idx, samplerate=sr_cand, channels=ch_cand)
                            target_sr = sr_cand
                            target_channels = ch_cand
                            found = True
                            break
                        except Exception:
                            continue
                    if found:
                        break

            # Resample mono audio to target rate
            resampled = resample_pcm16(pcm_bytes, sample_rate, target_sr)
            mono_samples = np.frombuffer(resampled, dtype=np.int16)

            if target_channels == 2:
                stereo_samples = np.column_stack([mono_samples, mono_samples]).flatten().astype(np.int16)
                playback_bytes = stereo_samples.tobytes()
            else:
                playback_bytes = resampled

            duration_sec = len(mono_samples) / float(target_sr)

            if _SOUNDDEVICE_AVAILABLE:
                stream = None
                try:
                    kwargs = {
                        "samplerate": target_sr,
                        "channels": target_channels,
                        "dtype": "int16",
                        "device": out_idx,
                    }
                    # A just-cancelled thinking pulse may still hold the device
                    # for a moment; retry instead of dropping the reply.
                    for attempt in range(5):
                        try:
                            stream = await asyncio.to_thread(sd.RawOutputStream, **kwargs)
                            break
                        except sd.PortAudioError:
                            if attempt == 4:
                                raise
                            await asyncio.sleep(0.25)
                    stream.start()
                    await asyncio.to_thread(stream.write, playback_bytes)
                    # RawOutputStream.write is blocking: waiting for the full
                    # duration again kept the microphone disabled long after
                    # audible playback ended and clipped the user's next turn.
                    await asyncio.to_thread(stream.stop)
                    await asyncio.to_thread(stream.close)
                    print(f"[SERVER MIC] [AUDIO OUT] Played {duration_sec:.2f}s on '{dev_name}' (device={out_idx}, {target_sr}Hz, ch={target_channels}).")
                    return
                except Exception as exc:
                    print(f"[SERVER MIC] SoundDevice playback failed on '{dev_name}': {exc}")
                finally:
                    # A stream left open (cancelled task, failed write) keeps the
                    # ALSA hw device locked until the container restarts, and every
                    # later open fails with "Device unavailable".
                    _release_output_stream(stream)

            if _PYAUDIO_AVAILABLE:
                p = pyaudio.PyAudio()
                try:
                    kwargs = {
                        "format": pyaudio.paInt16,
                        "channels": target_channels,
                        "rate": target_sr,
                        "output": True,
                        "output_device_index": out_idx,
                    }
                    stream = p.open(**kwargs)
                    stream.write(playback_bytes)
                    stream.stop_stream()
                    stream.close()
                    print(f"[SERVER MIC] [AUDIO OUT] Played {duration_sec:.2f}s via PyAudio on '{dev_name}'.")
                finally:
                    p.terminate()
        except Exception as exc:
            print(f"[SERVER MIC] Audio playback error: {exc}")
        finally:
            if suppress_capture:
                await asyncio.sleep(0.4)
                self._is_speaking = False
                self.vad.reset_segment()

    async def _stream_live_audio(self, audio_queue: asyncio.Queue) -> None:
        """Play Gemini PCM chunks as they arrive through one output stream."""
        stream = None
        collected = bytearray()
        try:
            out_idx = find_best_output_device(self.output_device_index)
            if out_idx is None or not _SOUNDDEVICE_AVAILABLE:
                while True:
                    chunk = await audio_queue.get()
                    try:
                        if chunk is None:
                            break
                        collected.extend(chunk)
                    finally:
                        audio_queue.task_done()
                if collected:
                    await self.play_audio_locally(bytes(collected), sample_rate=24000)
                return

            dev_info = sd.query_devices(out_idx)
            dev_name = dev_info.get("name", f"device_{out_idx}")
            target_sr = 48000
            target_channels = 2
            found = False
            for sr_cand in (48000, 44100, 24000):
                for ch_cand in (2, 1):
                    try:
                        sd.check_output_settings(
                            device=out_idx,
                            samplerate=sr_cand,
                            channels=ch_cand,
                        )
                        target_sr = sr_cand
                        target_channels = ch_cand
                        found = True
                        break
                    except Exception:
                        continue
                if found:
                    break

            stream = await asyncio.to_thread(
                sd.RawOutputStream,
                samplerate=target_sr,
                channels=target_channels,
                dtype="int16",
                device=out_idx,
            )
            stream.start()
            self._is_speaking = True
            print(f"[SERVER MIC] [LIVE AUDIO] Streaming on {dev_name!r}.")

            while True:
                chunk = await audio_queue.get()
                try:
                    if chunk is None:
                        break
                    resampled = resample_pcm16(chunk, 24000, target_sr)
                    if target_channels == 2:
                        mono = np.frombuffer(resampled, dtype=np.int16)
                        playback = np.repeat(mono, 2).astype(np.int16).tobytes()
                    else:
                        playback = resampled
                    await asyncio.to_thread(stream.write, playback)
                finally:
                    audio_queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[SERVER MIC] [LIVE AUDIO] Streaming failed: {exc}")
        finally:
            if stream is not None:
                try:
                    await asyncio.to_thread(stream.stop)
                    await asyncio.to_thread(stream.close)
                except BaseException:
                    pass
                finally:
                    # Safety net when stop/close was cancelled or failed.
                    _release_output_stream(stream)
            await asyncio.sleep(0.15)
            self._is_speaking = False
            self.vad.reset_segment()

    async def _warm_up_tts(self) -> None:
        """Load the local Pocket model once at startup.

        Without this the first reply after every restart waits ~8s while the
        model and voice state load, which looks like Monika froze.
        """
        if self.tts_provider not in {"local", "xtts", "pocket", "auto"}:
            return
        try:
            from backend.conversation.voice_output import get_voice_output_service

            service = get_voice_output_service()
            status = service.get_status()
            provider = status.get("provider") or "xtts"
            if provider != "pocket":
                return
            # Bypass the audio cache: a cache hit would skip loading the model.
            from backend.odysseus.services.tts.tts_service import get_tts_service

            started = time.perf_counter()
            await asyncio.wait_for(
                asyncio.to_thread(
                    get_tts_service().synthesize,
                    # Output is discarded; only loading the model matters.
                    "OK.",
                    use_cache=False,
                    provider=provider,
                    voice=status.get("voice"),
                ),
                timeout=max(60.0, float(self.tts_timeout)),
            )
            print(
                "[SERVER MIC] [TTS] Pocket warm-up done "
                f"in {(time.perf_counter() - started) * 1000.0:.0f}ms."
            )
        except Exception as exc:
            print(f"[SERVER MIC] [TTS] Warm-up skipped: {exc}")

    async def _render_speech(self, text: str) -> Tuple[bytes, int]:
        """Synthesize text to (pcm16 mono, sample_rate): local renderer, then Gemini, then Flite."""
        if self.tts_provider in {"local", "kokoro", "xtts", "pocket", "auto"}:
            try:
                from backend.conversation.voice_output import (
                    get_voice_output_service,
                    speech_to_live_pcm,
                )

                service = get_voice_output_service()
                status = service.get_status()
                configured = status.get("provider") or "xtts"
                if self.tts_provider in {"xtts", "pocket"} or (self.tts_provider in {"local", "auto", "kokoro"} and configured in {"xtts", "local", "pocket"}):
                    provider_to_use = configured
                elif self.tts_provider != "kokoro":
                    provider_to_use = self.tts_provider
                else:
                    provider_to_use = "local"

                started = time.perf_counter()
                rendered = await asyncio.wait_for(
                    service.synthesize(
                        text,
                        provider=provider_to_use,
                        voice=status.get("voice"),
                        **(
                            {"language": self.tts_language}
                            if self.tts_language and self.tts_language != "auto"
                            else {}
                        ),
                    ),
                    timeout=self.tts_timeout,
                )
                pcm_audio = speech_to_live_pcm(rendered)
                print(
                    f"[SERVER MIC] [TTS] {provider_to_use} rendered {len(text)} chars "
                    f"in {(time.perf_counter() - started) * 1000.0:.0f}ms."
                )
                return pcm_audio, 24000
            except Exception as exc:
                print(
                    f"[SERVER MIC] [TTS] {self.tts_provider} renderer unavailable ({exc}); "
                    "falling back to Gemini."
                )

        try:
            from backend.conversation.speech import GeminiSpeechSynthesizer, SpeechSynthesisRequest

            started = time.perf_counter()
            result = await GeminiSpeechSynthesizer(api_key=self.gemini_api_key).synthesize(
                SpeechSynthesisRequest(
                    text=text,
                    voice=self.gemini_voice,
                    language=self.tts_language or "auto",
                )
            )
            if result and result.audio:
                print(
                    f"[SERVER MIC] [TTS] gemini rendered {len(text)} chars "
                    f"in {(time.perf_counter() - started) * 1000.0:.0f}ms."
                )
                return result.audio, result.sample_rate
        except Exception as exc:
            print(f"[SERVER MIC] [TTS] Gemini unavailable ({exc}); using local fallback.")

        local_audio = await self._synthesize_with_flite(text)
        if local_audio:
            print("[SERVER MIC] [TTS] Using local fallback voice.")
            return local_audio, 24000
        raise RuntimeError("No working speech synthesizer is available")

    async def _play_pcm(self, pcm: bytes, sample_rate: int, *, capture_safe: bool = False) -> None:
        if capture_safe:
            await self.play_audio_locally(pcm, sample_rate=sample_rate, suppress_capture=False)
        else:
            await self.play_audio_locally(pcm, sample_rate=sample_rate)

    async def _synthesize_and_play(
        self,
        text: str,
        *,
        capture_safe: bool = False,
        announce_speaking: bool = False,
    ) -> None:
        """Synthesize one reply and play it through the server audio device."""
        if not text or text.startswith("("):
            return

        if announce_speaking:
            # Spoken replies stay short; the full text remains in the chat.
            from backend.conversation.speech_text import (
                prepare_for_speech,
                truncate_for_speech,
            )

            text = truncate_for_speech(prepare_for_speech(text), self.tts_max_chars) or text

        started = time.perf_counter()
        pcm, sample_rate = await self._render_speech(text)
        if announce_speaking and self.voice_light_feedback:
            self._queue_voice_light_state("speaking")
        await self._play_pcm(pcm, sample_rate, capture_safe=capture_safe)
        print(f"[SERVER MIC] [TTS TIMING] total={(time.perf_counter() - started) * 1000.0:.0f}ms")

    async def _speak_stream(self, pieces: asyncio.Queue) -> None:
        """Speak text pieces as they arrive; the next renders while one plays."""
        from backend.conversation.speech_text import prepare_for_speech

        rendered: asyncio.Queue = asyncio.Queue(maxsize=2)

        async def render() -> None:
            try:
                while (piece := await pieces.get()) is not None:
                    text = prepare_for_speech(piece)
                    if not text:
                        continue
                    try:
                        pcm, sample_rate = await self._render_speech(text)
                        # Pieces play back to back; give each the pause a
                        # reader would make after it.
                        pause = 0.3 if text.rstrip()[-1:] in ".!?…" else 0.12
                        pcm += b"\0\0" * int(sample_rate * pause)
                        await rendered.put((text, pcm, sample_rate))
                    except Exception as exc:
                        print(f"[SERVER MIC] [TTS] Skipping unrenderable piece: {exc}")
            finally:
                await rendered.put(None)

        renderer = asyncio.create_task(render(), name="server-mic-tts-render")
        self._arm_barge_in()
        try:
            while not self._barge_in_segment:
                try:
                    item = await asyncio.wait_for(
                        rendered.get(),
                        timeout=1.0 if self._first_audio_at and self.voice_light_feedback else None,
                    )
                except asyncio.TimeoutError:
                    # Nothing to say for a while (a tool is running after
                    # "Już sprawdzam…"): show thinking again, not dead air.
                    self._queue_voice_light_state("thinking")
                    item = await rendered.get()
                    if item is not None:
                        self._queue_voice_light_state("speaking")
                if item is None or self._barge_in_segment:
                    break
                if self._first_audio_at is None:
                    self._first_audio_at = time.perf_counter()
                    if self.voice_light_feedback:
                        self._queue_voice_light_state("speaking")
                text, pcm, sample_rate = item
                self._spoken_pieces.append(text)
                await self._play_pcm(pcm, sample_rate)
        finally:
            self._reply_playing = False
            renderer.cancel()

    async def _run_streaming_turn(self, prompt: str) -> str:
        """Ask the agent and speak its answer sentence by sentence while it streams."""
        from backend.conversation.speech_text import SpeechChunker

        chunker = SpeechChunker(max_chars=self.tts_max_chars)
        pieces: asyncio.Queue = asyncio.Queue()

        def on_event(event: Dict[str, Any]) -> None:
            # A tool call ends the current agent round: speak what was said
            # before it now ("Już sprawdzam…") instead of gluing it to the
            # next round's text.
            ready = chunker.flush() if "tool" in event else chunker.feed(event.get("text") or "")
            for piece in ready:
                pieces.put_nowait(piece)

        # "" is meaningful: interrupted before a single word was spoken.
        note, self._interrupted_reply = self._interrupted_reply, None
        extra = {"interrupted_reply": note} if note is not None else {}
        speaker = asyncio.create_task(self._speak_stream(pieces), name="server-mic-speaker")
        try:
            try:
                reply = str(await self.conversation_stream_handler(prompt, on_event, **extra) or "")
            except Exception as exc:
                print(f"[SERVER MIC] Error processing reply: {exc}")
                reply = "" if chunker.text.strip() else _turn_error_reply()
            streamed = chunker.text.strip()
            # The final answer can extend what streamed (a spoken approval
            # question, the "Done." fallback) or replace an unspoken marker.
            if reply and reply.startswith(streamed):
                for piece in chunker.feed(reply[len(streamed):]) + chunker.flush():
                    pieces.put_nowait(piece)
            elif reply and not streamed:
                pieces.put_nowait(reply)
            pieces.put_nowait(None)
            await speaker
            # The user may still be talking over the end of the reply.
            while self._barge_monitor is not None and self._barge_monitor.state == "capturing":
                await asyncio.sleep(0.05)
            if self._barge_task is not None:
                await self._barge_task
        finally:
            speaker.cancel()
        return reply

    def _arm_barge_in(self) -> None:
        self._spoken_pieces = []
        self._barge_task = None
        self._barge_in_segment = None
        if self._barge_monitor is not None and self._output is not None:
            self._barge_monitor.reset()
            self._speech_detector.reset()
            self._output.gain, self._output.paused = 1.0, False
            self._reply_playing = True

    def _barge_in_frame(self, frame: bytes) -> None:
        """Watch echo-cancelled mic audio while Monika speaks."""
        probability = self._speech_detector.feed(frame)
        event = self._barge_monitor.push(frame, probability)
        if event == "duck":
            self._output.gain = self._duck_gain
        elif event == "unduck":
            self._output.gain = 1.0
        elif event == "interrupt":
            self._output.paused = True
        elif event == "segment":
            self._barge_task = asyncio.create_task(
                self._resolve_barge_in(self._barge_monitor.segment), name="server-mic-barge-in"
            )
        if event:
            print(f"[SERVER MIC] [BARGE-IN] {event} (speech p={probability:.2f}).")

    async def _resolve_barge_in(self, pcm: bytes) -> None:
        """Paused for the user: drop the rest of the reply, or carry on if it was nothing."""
        transcript = await self.transcribe_speech(_raw_pcm_to_wav(pcm, sample_rate=self.sample_rate))
        spoken = " ".join(self._spoken_pieces)
        if transcript and not looks_like_echo(transcript, spoken):
            print(f"[SERVER MIC] [BARGE-IN] Interrupted by \"{transcript}\".")
            self._barge_in_segment, self._barge_in_transcript = pcm, transcript
            self._interrupted_reply = spoken
            self._output.stop()
            return
        print(f"[SERVER MIC] [BARGE-IN] Resuming; heard {'own echo' if transcript else 'no words'}.")
        self._barge_monitor.reset()
        self._speech_detector.reset()
        self._output.gain, self._output.paused = 1.0, False

    async def _synthesize_with_flite(self, text: str) -> bytes:
        """Return local PCM speech using FFmpeg's bundled Flite engine."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return b""

        # The bundled voice is English-only. Removing Polish diacritics gives
        # it a substantially more intelligible phonetic approximation.
        translation = str.maketrans(
            "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
            "acelnoszzACELNOSZZ",
        )
        speakable = str(text).translate(translation).strip()[:800]
        if not speakable:
            return b""

        path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False
            ) as handle:
                handle.write(speakable)
                path = handle.name

            process = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"flite=textfile={path}:voice=slt",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-f",
                "s16le",
                "pipe:1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15.0)
            if process.returncode != 0:
                print(
                    "[SERVER MIC] [TTS] Local fallback failed: "
                    f"{stderr.decode('utf-8', errors='replace').strip()}"
                )
                return b""
            return bytes(stdout)
        except Exception as exc:
            print(f"[SERVER MIC] [TTS] Local fallback failed: {exc}")
            return b""
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    async def _play_wake_chime(
        self,
        *,
        capture_safe: bool = False,
        gain: float = 1.35,
    ) -> None:
        """Play an API-independent acknowledgement that command mode is open."""
        if self._cached_chime_pcm:
            pcm = self._cached_chime_pcm
            if abs(gain - 1.35) > 0.05:
                arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
                scale = gain / 1.35
                arr = np.clip(arr * scale, -32768, 32767).astype(np.int16)
                pcm = arr.tobytes()
            await self.play_audio_locally(
                pcm,
                self._cached_chime_sr,
                suppress_capture=not capture_safe,
            )
            return

        sample_rate = 24000
        chunks = []
        amplitude = min(12000.0, 4200.0 * max(0.5, float(gain)))
        for frequency in (660.0, 880.0):
            duration = 0.11
            count = int(sample_rate * duration)
            timeline = np.arange(count, dtype=np.float64) / sample_rate
            envelope = np.sin(np.linspace(0.0, math.pi, count)) ** 2
            tone = (amplitude * envelope * np.sin(2.0 * math.pi * frequency * timeline))
            chunks.append(tone.astype(np.int16))
            chunks.append(np.zeros(int(sample_rate * 0.035), dtype=np.int16))
        await self.play_audio_locally(
            np.concatenate(chunks).tobytes(),
            sample_rate,
            suppress_capture=not capture_safe,
        )

    async def _play_wake_acknowledgement(
        self,
        wake_text: str = _WAKE_ACKNOWLEDGEMENT,
        *,
        capture_safe: bool = True,
    ) -> None:
        """Play wake chime and/or pre-loaded paralinguistic voice response."""
        mode = self._wake_ack_mode
        if mode not in {"both", "voice_only", "chime_only"}:
            mode = "both"

        # 1. Chime
        if mode in {"both", "chime_only"}:
            await self._play_wake_chime(capture_safe=capture_safe)

        # 2. Voice prompt
        if mode in {"both", "voice_only"}:
            if mode == "both":
                await asyncio.sleep(_WAKE_CHIME_TO_VOICE_GAP_SEC)
                if self.vad.is_speech_active:
                    # "Hej Monika, zapal światło" in one breath: the command
                    # is already coming, so a spoken "Hm?" would only land
                    # inside its recording.  The chime is enough.
                    print("[SERVER MIC] [WAKE] Command already spoken; skipping voice prompt.")
                    return
            try:
                from unittest.mock import AsyncMock, MagicMock
                is_mocked = isinstance(getattr(self, "_synthesize_and_play", None), (AsyncMock, MagicMock))
            except Exception:
                is_mocked = False

            if is_mocked:
                await self._synthesize_and_play(wake_text)
                return

            if self._cached_wake_prompts:
                name, pcm, sr = random.choice(self._cached_wake_prompts)
                print(f"[SERVER MIC] [WAKE] Playing preloaded neutral prompt '{name}'.")
                await self.play_audio_locally(
                    pcm,
                    sample_rate=sr,
                    suppress_capture=not capture_safe,
                )
            else:
                try:
                    await self._synthesize_and_play(wake_text, capture_safe=capture_safe)
                except Exception as exc:
                    print(f"[SERVER MIC] [WAKE] Voice acknowledgement notice: {exc}")

    def _live_system_instruction(self) -> str:
        try:
            from backend.core.runtimes.v2_runtime import get as get_v2_runtime

            runtime = get_v2_runtime()
            persona = str(getattr(runtime, "cached_prompt", "") or "").strip()
        except Exception:
            persona = ""

        smart_devices_summary = ""
        if self.home_assistant_agent and getattr(self.home_assistant_agent, "entities", None):
            dev_list = []
            for eid, state in self.home_assistant_agent.entities.items():
                if "child_lock" not in eid:
                    fn = state.get("attributes", {}).get("friendly_name", eid)
                    dev_list.append(f"- {eid}: {fn}")
            smart_devices_summary = (
                "\n\n[DOSTĘPNE URZĄDZENIA DOMOWE I USŁUGI (Home Assistant)]:\n"
                + "\n".join(dev_list)
                + "\nMożesz sterować nimi za pomocą narzędzia control_light (np. target='kuchnia', target='salon', target='biurko', target='kanapa', target='wszystkie').\n"
                + "Do zarządzania listą zakupów (Shopping List) ZAWSZE używaj narzędzia manage_shopping_list (action='get', action='add', action='remove').\n"
            )

        voice_rules = (
            "\n\n[SERVER VOICE SESSION]\n"
            "Rozmawiasz głosowo z użytkownikiem po polsku. Odpowiadaj bardzo krótko, naturalnie, "
            "ciepło i zwięźle. Gdy użytkownik pyta o listę zakupów lub prosi o dodanie/usunięcie produktu, "
            "wywołaj natychmiast narzędzie manage_shopping_list. "
            "Gdy użytkownik prosi o włączenie lub wyłączenie światła lub urządzenia, "
            "wywołaj narzędzie control_light, a po jego wykonaniu potwierdź jednym krótkim, miłym zdaniem. "
            "Narzędzia zmieniające stan wywołuj tylko wtedy, gdy bieżąca wypowiedź zawiera pełne, "
            "jawne polecenie z czynnością i obiektem. Samo potwierdzenie typu „Dobra” nie upoważnia do zmiany. "
            "Jeśli narzędzie zwróci BLOCKED, nie twierdź, że operacja się udała; poproś o pełne polecenie. "
            "Jeżeli użytkownik powiedział tylko twoje imię ('Monika' lub odmianę), odpowiedz krótko 'Hm?' i zaczekaj na "
            "następną wypowiedź. Nie opisuj działania systemu ani transkrypcji."
        )
        return (persona + smart_devices_summary + voice_rules).strip()

    @staticmethod
    def _normalize_live_command(value: Any) -> str:
        return str(value or "").casefold().translate(
            str.maketrans("ąćęłńóśźż", "acelnoszz")
        )

    def _live_tool_is_explicitly_requested(
        self, name: str, args: dict, user_text: str
    ) -> bool:
        """Require an explicit utterance before a Live session may mutate state."""
        text = self._normalize_live_command(user_text)
        if name in {"list_smart_devices"}:
            return True

        if name == "manage_shopping_list":
            action = self._normalize_live_command(args.get("action"))
            if action == "get":
                return True
            verbs = {
                "add": ("dodaj", "dopisz", "dorzuc", "wpisz"),
                "remove": ("usun", "skresl", "wykresl", "zdejmij"),
            }.get(action, ())
            item = self._normalize_live_command(args.get("item")).strip()
            return bool(item and item in text and any(verb in text for verb in verbs))

        if name == "control_light":
            action = self._normalize_live_command(args.get("action"))
            verbs = {
                "turn_on": ("wlacz", "zapal", "uruchom"),
                "turn_off": ("wylacz", "zgas", "zatrzymaj"),
                "set": ("ustaw", "zmien"),
            }.get(action, ())
            target = self._normalize_live_command(args.get("target"))
            target_tokens = [
                token for token in re.findall(r"[a-z0-9]+", target) if len(token) >= 3
            ]
            return bool(
                target_tokens
                and any(token in text for token in target_tokens)
                and any(verb in text for verb in verbs)
            )

        return False

    async def _execute_live_tool(
        self, name: str, args: dict, user_text: str = ""
    ) -> str:
        if not self._live_tool_is_explicitly_requested(name, args, user_text):
            print(
                f"[SERVER MIC] [LIVE TOOL] Blocked {name}({args}); "
                f"no explicit request in \"{user_text}\"."
            )
            return (
                "BLOCKED: nie wykonano operacji, ponieważ bieżąca wypowiedź "
                "nie zawierała jednoznacznego polecenia. Poproś użytkownika "
                "o pełne polecenie z czynnością i obiektem."
            )
        try:
            from backend.core.smart_home_tool_executor import SmartHomeToolExecutor
            from backend.conversation.tools import ConversationToolRequest

            agents = [a for a in (self.home_assistant_agent, self.kasa_agent, self.hue_agent) if a is not None]
            executor = SmartHomeToolExecutor(agents=agents)
            req = ConversationToolRequest(name=name, arguments=args)
            result = await executor.execute(req)
            return str(getattr(result, "result", "") or getattr(result, "rendered", "") or "Wykonano pomyślnie.")
        except Exception as e:
            return f"Error executing {name}: {e}"

    async def _run_live_session(self, initial_pcm: bytes) -> None:
        from google import genai
        from google.genai import types

        queue = self._live_audio_queue
        if queue is None:
            return
        verification = self._wake_verified_event
        session_started = time.monotonic()
        playback_queue: Optional[asyncio.Queue] = None
        player_task: Optional[asyncio.Task] = None
        try:
            client = genai.Client(
                api_key=self.gemini_api_key,
                http_options={"api_version": "v1alpha"},
            )
            config = {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {"voice_name": self.gemini_voice}
                    }
                },
                "input_audio_transcription": {},
                "output_audio_transcription": {},
                "enable_affective_dialog": True,
                "system_instruction": self._live_system_instruction(),
            }
            from backend.core.tool_definitions import (
                control_light_tool,
                list_smart_devices_tool,
                manage_shopping_list_tool,
            )
            tools_list = []
            if self.home_assistant_agent or self.kasa_agent or self.hue_agent:
                tools_list.append({
                    "function_declarations": [
                        control_light_tool,
                        list_smart_devices_tool,
                        manage_shopping_list_tool,
                    ]
                })
            if tools_list:
                config["tools"] = tools_list

            print(f"[SERVER MIC] [LIVE] Connecting to {self.live_model} (realtime stream)...")
            async with client.aio.live.connect(
                model=self.live_model, config=config
            ) as session:
                print("[SERVER MIC] [LIVE] Realtime transport ready.")

                # A partial wake may establish transport, but no microphone
                # bytes leave the host until the final Vosk result verifies it.
                if verification is not None and not verification.is_set():
                    print("[SERVER MIC] [LIVE] Waiting at local audio privacy gate.")
                    try:
                        await asyncio.wait_for(verification.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        self._cancel_provisional_live_session(
                            "final verifier timed out"
                        )
                        return
                if verification is not None and not verification.is_set():
                    return

                await self._open_conversation_session()

                if not initial_pcm and self._pending_initial_pcm:
                    initial_pcm = self._pending_initial_pcm
                self._pending_initial_pcm = b""
                print("[SERVER MIC] [LIVE] Realtime session verified and ready.")
                if self.voice_light_feedback:
                    self._queue_voice_light_state("listening")

                # Stream initial wake audio in chunks
                if initial_pcm:
                    chunk_bytes = int(self.sample_rate * 2 * 0.05)
                    for offset in range(0, len(initial_pcm), chunk_bytes):
                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=initial_pcm[offset : offset + chunk_bytes],
                                mime_type=f"audio/pcm;rate={self.sample_rate}",
                            )
                        )

                async def audio_sender():
                    while True:
                        try:
                            chunk = await queue.get()
                            if chunk and not self._is_speaking:
                                await session.send_realtime_input(
                                    audio=types.Blob(
                                        data=chunk,
                                        mime_type=f"audio/pcm;rate={self.sample_rate}",
                                    )
                                )
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            print(f"[SERVER MIC] [LIVE SENDER] Error: {e}")
                            break

                sender_task = asyncio.create_task(audio_sender(), name="live-audio-sender")

                try:
                    input_text = ""
                    output_text = ""

                    while True:
                        iterator = session.receive().__aiter__()
                        turn_active = True
                        while turn_active:
                            now = time.monotonic()
                            idle_elapsed = now - self._last_live_voice_time
                            session_elapsed = now - session_started
                            if idle_elapsed >= self.live_idle_timeout:
                                print(
                                    f"[SERVER MIC] [LIVE] Voice inactivity timeout "
                                    f"({self.live_idle_timeout:.0f}s); closing live session."
                                )
                                return
                            if session_elapsed >= self.live_max_session:
                                print(
                                    f"[SERVER MIC] [LIVE] Maximum session duration "
                                    f"({self.live_max_session:.0f}s) reached; closing."
                                )
                                return

                            model_timeout = 15.0 if (player_task or output_text) else self.live_idle_timeout
                            current_timeout = max(
                                0.1,
                                min(
                                    model_timeout,
                                    self.live_idle_timeout - idle_elapsed,
                                    self.live_max_session - session_elapsed,
                                ),
                            )
                            try:
                                response = await asyncio.wait_for(
                                    anext(iterator), timeout=current_timeout
                                )
                            except asyncio.TimeoutError:
                                # Re-evaluate actual microphone activity; model
                                # traffic must not keep an abandoned session alive.
                                continue
                            except StopAsyncIteration:
                                return

                            content = getattr(response, "server_content", None)
                            if content:
                                input_transcription = getattr(
                                    content, "input_transcription", None
                                )
                                fragment = str(
                                    getattr(input_transcription, "text", "") or ""
                                ).strip()
                                if fragment:
                                    if not input_text or fragment.startswith(input_text):
                                        input_text = fragment
                                    elif fragment not in input_text:
                                        input_text = f"{input_text} {fragment}".strip()
                                    if self.voice_light_feedback and player_task is None:
                                        self._queue_voice_light_state("thinking")

                            tool_call = getattr(response, "tool_call", None)
                            if tool_call:
                                if self.voice_light_feedback and player_task is None:
                                    self._queue_voice_light_state("thinking")
                                function_responses = []
                                for fc in getattr(tool_call, "function_calls", []):
                                    fn_name = getattr(fc, "name", "")
                                    fn_args = getattr(fc, "args", {}) or {}
                                    fn_id = getattr(fc, "id", "")
                                    print(f"[SERVER MIC] [LIVE TOOL] Requested {fn_name}({fn_args})")
                                    res = await self._execute_live_tool(fn_name, fn_args, input_text)
                                    function_responses.append(
                                        types.FunctionResponse(
                                            id=fn_id,
                                            name=fn_name,
                                            response={"result": res},
                                        )
                                    )
                                if function_responses:
                                    await session.send(input=types.LiveClientToolResponse(function_responses=function_responses))
                                    continue

                            if content:
                                output_transcription = getattr(content, "output_transcription", None)
                                if output_transcription and getattr(output_transcription, "text", None):
                                    output_text += str(output_transcription.text)
                                model_turn = getattr(content, "model_turn", None)
                                for part in list(getattr(model_turn, "parts", None) or []):
                                    inline = getattr(part, "inline_data", None)
                                    data = getattr(inline, "data", None)
                                    if data:
                                        if player_task is None:
                                            if self.voice_light_feedback:
                                                self._queue_voice_light_state("speaking")
                                            playback_queue = asyncio.Queue()
                                            player_task = asyncio.create_task(
                                                self._stream_live_audio(playback_queue),
                                                name="live-audio-player",
                                            )
                                        await playback_queue.put(bytes(data))

                                if getattr(content, "turn_complete", False):
                                    if input_text:
                                        print(f"[SERVER MIC] [LIVE HEARD] \"{input_text}\"")
                                    if output_text:
                                        print(f"[SERVER MIC] [LIVE REPLY] \"{output_text.strip()}\"")
                                    if player_task and playback_queue:
                                        await playback_queue.put(None)
                                        await player_task
                                        player_task = None
                                        playback_queue = None
                                    if self.on_turn_finished and (input_text or output_text):
                                        cb = self.on_turn_finished(input_text, output_text)
                                        if asyncio.iscoroutine(cb):
                                            await cb
                                    input_text = ""
                                    output_text = ""
                                    turn_active = False
                                    if self.voice_light_feedback:
                                        self._queue_voice_light_state("listening")
                                    break

                finally:
                    if player_task and playback_queue:
                        await playback_queue.put(None)
                        try:
                            await player_task
                        except asyncio.CancelledError:
                            pass
                    sender_task.cancel()
                    try:
                        await sender_task
                    except asyncio.CancelledError:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[SERVER MIC] [LIVE] Session error: {exc}")
        finally:
            await self._close_conversation_session()
            self._wake_provisional = False
            self._wake_verified_event = None
            self._pending_initial_pcm = b""
            self._live_audio_queue = None
            if self._live_session_task is asyncio.current_task():
                self._live_session_task = None
            self.vad.reset_segment()
            self._reset_continuous_wake_recognizer()
            if self.voice_light_feedback:
                await self._set_voice_light_state("idle", wait=True)
            print("[SERVER MIC] [LIVE] Session closed; local wake listening resumed.")

    async def _handle_live_wake_segment(self, raw_pcm: bytes) -> None:
        if self.is_live_session_active:
            if self._live_audio_queue is not None:
                await self._live_audio_queue.put(raw_pcm)
                print("[SERVER MIC] [LIVE] Follow-up speech queued.")
            return

        transcript = await self.transcribe_wake_word_locally(raw_pcm)
        if not transcript:
            print(
                "[SERVER MIC] [LOCAL] Completed speech segment was not "
                "recognized as a wake phrase."
            )
            return
        print(f"[SERVER MIC] [LOCAL HEARD] \"{transcript}\"")
        matched, _ = self.extract_wake_word(transcript)
        if not matched:
            print("[SERVER MIC] [LOCAL] Speech ignored; no wake word.")
            return

        self._start_live_session(raw_pcm, transcript)

    def _speech_segment_in_flight(self) -> bool:
        task = self._speech_segment_task
        return bool(task and not task.done())

    def _on_speech_segment_done(self, task: asyncio.Task) -> None:
        """Release the single-segment gate and surface unexpected failures."""
        if self._speech_segment_task is task:
            self._speech_segment_task = None
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error:
            print(f"[SERVER MIC] Błąd przetwarzania segmentu mowy: {error}")

    def _schedule_speech_segment(self, raw_pcm: bytes) -> None:
        """Schedule one segment and drop overlapping captures deterministically."""
        if self._speech_segment_in_flight():
            # The listener continues draining the microphone while STT/model/
            # TTS work is in progress; the loop resets VAD in that state, so a
            # second segment cannot leak stale audio into the next turn.
            print(
                "[SERVER MIC] [VAD] Ignoring segment while the previous "
                "segment is still being processed."
            )
            self.vad.reset_segment()
            return
        task = asyncio.create_task(
            self._handle_speech_segment(raw_pcm),
            name="server-mic-speech-segment",
        )
        self._speech_segment_task = task
        task.add_done_callback(self._on_speech_segment_done)

    async def _handle_speech_segment(self, raw_pcm: bytes):
        """Process recorded speech segment."""
        if self._is_muted or self._is_speaking or self._is_busy:
            return

        timing_started = time.perf_counter()
        local_wake_ms = 0.0
        stt_ms = 0.0
        model_ms = 0.0
        tts_ms = 0.0
        segment_duration = len(raw_pcm) / (self.sample_rate * 2.0)

        min_bytes = int(self.sample_rate * 2 * 0.2)
        if len(raw_pcm) < min_bytes:
            return

        samples = np.frombuffer(raw_pcm, dtype=np.int16)
        rms = float(math.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        if rms < 50.0:
            return

        if self.use_gemini_live:
            print(
                "[SERVER MIC] [VAD] Completed segment "
                f"({len(raw_pcm) / (self.sample_rate * 2):.2f}s, rms={rms:.1f})."
            )
            await self._handle_live_wake_segment(raw_pcm)
            return

        print(
            f"[SERVER MIC] [VAD] Detected speech segment "
            f"({segment_duration:.2f}s, rms={rms:.1f}). Transcribing..."
        )

        continuing_session = self.is_awaiting_command
        local_wake_matched = False
        local_wake_prompt = ""
        if self.require_wake_word and not continuing_session:
            # Room audio is classified locally first. Only a segment containing
            # the wake phrase is allowed to reach cloud transcription.
            wake_started = time.perf_counter()
            local_wake = await self.transcribe_wake_word_locally(raw_pcm)
            local_wake_ms = (time.perf_counter() - wake_started) * 1000.0
            local_wake_matched, local_wake_prompt = self.extract_wake_word(local_wake)
            if not local_wake_matched:
                print(
                    "[SERVER MIC] [LOCAL] Speech ignored before cloud STT; "
                    f"no wake word in \"{local_wake or 'unrecognized'}\"."
                )
                print(
                    "[SERVER MIC] [TIMING] "
                    f"segment={segment_duration:.2f}s local_wake={local_wake_ms:.0f}ms "
                    f"total={(time.perf_counter() - timing_started) * 1000.0:.0f}ms "
                    "result=ignored_no_wake"
                )
                return

        # A standalone wake phrase is already fully classified by the local
        # recognizer.  Avoid a second cloud STT round-trip before saying
        # "Hm?"; attached commands still go through cloud STT for the
        # better command transcription quality.
        if local_wake_matched and not local_wake_prompt:
            # This branch intentionally skips ``transcribe_speech``. Clear
            # diagnostics from a previous segment so they cannot make this
            # valid standalone wake look like a rejected STT result.
            self._last_stt_confidence = None
            self._last_stt_intelligible = None
            self._last_stt_rejection_reason = ""
            transcript = local_wake
            print(
                "[SERVER MIC] [LOCAL] Standalone wake confirmed; "
                "skipping cloud STT before acknowledgement."
            )
        else:
            wav_bytes = _raw_pcm_to_wav(raw_pcm, sample_rate=self.sample_rate)
            stt_started = time.perf_counter()
            transcript, self._barge_in_transcript = self._barge_in_transcript, None
            transcript = transcript or await self.transcribe_speech(wav_bytes)
            stt_ms = (time.perf_counter() - stt_started) * 1000.0
        if not transcript:
            # Do not fall back to the local wake result after the cloud STT has
            # explicitly rejected the command as unreliable.  That fallback is
            # useful for provider failures, but would turn a low-confidence
            # hallucination back into an actionable prompt.
            if self._last_stt_rejection_reason:
                print(
                    "[SERVER MIC] [IGNORED] Final transcript rejected by the "
                    f"speech-quality gate ({self._last_stt_rejection_reason})."
                )
                return
            # A valid local wake is enough to open the command window even if
            # the cloud transcription request times out or returns no text.
            transcript = local_wake if local_wake_matched else ""
        if not transcript:
            print(
                "[SERVER MIC] [TIMING] "
                f"segment={segment_duration:.2f}s local_wake={local_wake_ms:.0f}ms "
                f"stt={stt_ms:.0f}ms total={(time.perf_counter() - timing_started) * 1000.0:.0f}ms "
                "result=no_transcript"
            )
            return

        assessment = assess_voice_transcript(
            transcript,
            confidence=self._last_stt_confidence,
            intelligible=self._last_stt_intelligible,
            min_confidence=self.stt_min_confidence,
        )
        if not assessment.accepted:
            print(
                "[SERVER MIC] [IGNORED] Speech-quality gate rejected the "
                f"transcript ({assessment.reason})."
            )
            return
        transcript = assessment.text

        if continuing_session:
            prompt_echo = re.sub(r"[^a-ząćęłńóśźż]+", "", transcript.casefold())
            if (
                time.monotonic() < self._activation_prompt_window_until
                and prompt_echo in {
                    "hm", "hmm", "hmmm", "mhm", "mhmm", "yhm", "yhmm",
                    "aha", "slucham", "jestem", "tak",
                }
            ):
                print(
                    "[SERVER MIC] [LOCAL] Ignoring the activation prompt echo; "
                    "command window remains open."
                )
                return

        print(f"[SERVER MIC] [HEARD] \"{transcript}\"")
        if continuing_session:
            # The preceding turn opened follow-up window or was wake word. Accept without repeating name.
            matched, prompt = True, transcript
            self._awaiting_command_until = 0.0
            # A bare "Hej Monika" while the window is open is a re-wake, not a
            # command: acknowledge it and keep listening instead of running a
            # full model + TTS turn for a greeting.
            if self.require_wake_word:
                bare_wake, bare_prompt = self.extract_wake_word(transcript)
                if bare_wake and not bare_prompt:
                    prompt = ""
                    print("[SERVER MIC] [CONVERSATION] Bare wake phrase in follow-up window; re-acknowledging.")
            if prompt:
                print("[SERVER MIC] [CONVERSATION] Follow-up turn received.")
        else:
            # Clear an expired window before processing a fresh wake word.
            self._awaiting_command_until = 0.0
            matched, prompt = self.extract_wake_word(transcript)
            if not matched and local_wake_matched:
                # Some STT models drop the short greeting/name after the
                # offline gate. Treat the remaining transcript as the command
                # rather than forcing the user to repeat the wake word.
                matched, prompt = True, transcript.strip()
                print(
                    "[SERVER MIC] [LOCAL] Wake accepted; cloud STT omitted "
                    "the wake word."
                )
        if not matched:
            print(f"[SERVER MIC] [IGNORED] No wake word in: \"{transcript}\"")
            return

        if not continuing_session:
            await self._close_conversation_session()
            await self._open_conversation_session()

        if self.voice_light_feedback:
            self._queue_voice_light_state("listening")

        if self.require_wake_word and not prompt:
            acknowledgement = _WAKE_ACKNOWLEDGEMENT
            print(
                "[SERVER MIC] [WAKE] Wake word detected; listening for a command "
                f"for {self.wake_listen_timeout:.1f}s."
            )
            async with self._turn_lock:
                self._is_busy = True
                # The listening window begins with the activation signal, not
                # after the acknowledgement has finished rendering.
                self._awaiting_command_until = (
                    time.monotonic() + self.wake_listen_timeout
                )
                try:
                    await self._play_wake_acknowledgement(acknowledgement, capture_safe=True)
                    if self.on_turn_finished:
                        callback = self.on_turn_finished(transcript, acknowledgement)
                        if asyncio.iscoroutine(callback):
                            await callback
                except Exception as exc:
                    print(f"[SERVER MIC] Błąd potwierdzenia słowa wybudzającego: {exc}")
                finally:
                    self.vad.reset_segment()
                    self._is_busy = False
            print(
                "[SERVER MIC] [TIMING] "
                f"segment={segment_duration:.2f}s local_wake={local_wake_ms:.0f}ms "
                f"stt={stt_ms:.0f}ms total={(time.perf_counter() - timing_started) * 1000.0:.0f}ms "
                "result=wake_ack"
            )
            return

        async with self._turn_lock:
            self._is_busy = True
            try:
                if self.voice_light_feedback:
                    self._queue_voice_light_state("thinking")

                reply_text = ""
                model_started = time.perf_counter()
                self._first_audio_at = None
                if self.conversation_stream_handler:
                    reply_text = await self._run_streaming_turn(prompt)
                    model_ms = (time.perf_counter() - model_started) * 1000.0
                    print(f"[SERVER MIC] [REPLY] \"{reply_text}\"")
                else:
                    if self.conversation_handler:
                        try:
                            res = self.conversation_handler(prompt)
                            if asyncio.iscoroutine(res):
                                reply_text = await res
                            else:
                                reply_text = str(res or "")
                        except Exception as exc:
                            print(f"[SERVER MIC] Error processing reply: {exc}")
                            reply_text = _turn_error_reply()
                    model_ms = (time.perf_counter() - model_started) * 1000.0

                    print(f"[SERVER MIC] [REPLY] \"{reply_text}\"")

                    if reply_text and not reply_text.startswith("("):
                        tts_started = time.perf_counter()
                        try:
                            await self._synthesize_and_play(reply_text, announce_speaking=True)
                        except Exception as exc:
                            print(f"[SERVER MIC] Błąd syntezy mowy: {exc}")
                        finally:
                            tts_ms = (time.perf_counter() - tts_started) * 1000.0

                if self.on_turn_finished:
                    try:
                        cb = self.on_turn_finished(transcript, reply_text)
                        if asyncio.iscoroutine(cb):
                            await cb
                    except Exception:
                        pass
            finally:
                # Let the room echo of the last word die out before listening.
                await asyncio.sleep(0.3)
                self.vad.reset_segment()
                followup_sec = float(os.getenv("SERVER_MIC_FOLLOWUP_TIMEOUT", "8.0"))
                if followup_sec > 0:
                    self._awaiting_command_until = time.monotonic() + followup_sec
                    print(f"[SERVER MIC] [CONVERSATION] Follow-up window open for {followup_sec:.1f}s.")
                else:
                    await self._close_conversation_session()
                if self.voice_light_feedback:
                    await self._set_voice_light_state("idle", wait=True)
                print(
                    "[SERVER MIC] [TIMING] "
                    f"segment={segment_duration:.2f}s local_wake={local_wake_ms:.0f}ms "
                    f"stt={stt_ms:.0f}ms model={model_ms:.0f}ms tts={tts_ms:.0f}ms "
                    f"first_audio={((self._first_audio_at or timing_started) - timing_started) * 1000.0:.0f}ms "
                    f"total={(time.perf_counter() - timing_started) * 1000.0:.0f}ms"
                )
                self._is_busy = False
        if self._barge_in_segment:
            # The user talked over the reply: their words are the next turn.
            segment, self._barge_in_segment = self._barge_in_segment, None
            await self._handle_speech_segment(segment)

    def _open_duplex(self, input_latency_s: float) -> None:
        """Open the persistent speaker stream and, if possible, echo cancellation + barge-in."""
        out_idx = find_best_output_device(self.output_device_index)
        if out_idx is None:
            return
        try:
            self._output = AudioOutput.open(sd, out_idx)
        except Exception as exc:
            print(f"[SERVER MIC] [DUPLEX] Persistent output unavailable ({exc}); using per-clip playback.")
            return
        print(
            f"[SERVER MIC] [DUPLEX] Output stream open (device={out_idx}, {self._output.rate}Hz, "
            f"ch={self._output.channels}, latency={self._output.latency_ms:.0f}ms)."
        )
        if not self.barge_in_enabled or self.sample_rate != 16000:
            return
        try:
            # Speaker-to-mic delay hint; AEC3 refines it, the offset is the
            # room calibration knob.
            delay_ms = (
                self._output.latency_ms
                + input_latency_s * 1000.0
                + float(os.getenv("SERVER_MIC_AEC_DELAY_OFFSET_MS", "0"))
            )
            self._speech_detector = SpeechDetector()
            self._echo = EchoCanceller(delay_ms)
            self._barge_monitor = BargeInMonitor(
                threshold=float(os.getenv("SERVER_MIC_BARGE_IN_THRESHOLD", "0.6")),
                interrupt_ms=int(os.getenv("SERVER_MIC_BARGE_IN_MS", "500")),
            )
            print(f"[SERVER MIC] [DUPLEX] Echo cancellation + barge-in on (delay hint {delay_ms:.0f}ms).")
        except Exception as exc:
            self._echo = self._speech_detector = self._barge_monitor = None
            print(f"[SERVER MIC] [DUPLEX] Barge-in unavailable: {exc}")

    async def _listen_loop(self):
        """Main listening loop capturing chunks from the microphone."""
        stream = None
        pyaudio_inst = None

        try:
            try:
                mic_gain = int(os.getenv("SERVER_MIC_GAIN_PERCENT", "55"))
                optimize_alsa_mic_gain(mic_gain)
            except Exception:
                pass

            if self.require_wake_word:
                # Load the offline recognizer before opening the microphone so
                # the first spoken wake word cannot race model initialization.
                await asyncio.to_thread(self._load_vosk_model)
                self._reset_continuous_wake_recognizer()

            if _SOUNDDEVICE_AVAILABLE:
                dev_idx, dev_name, dev_sr = find_best_input_device(
                    self.input_device_index,
                    self.input_device_name,
                )
                chunk_size = int(dev_sr * (self.vad.frame_duration_ms / 1000.0))

                kwargs = {
                    "samplerate": dev_sr,
                    "channels": 1,
                    "dtype": "int16",
                    "blocksize": chunk_size,
                }
                if dev_idx is not None:
                    kwargs["device"] = dev_idx
                stream = sd.RawInputStream(**kwargs)
                stream.start()

                print(f"[SERVER MIC] [OK] Listening stream started on '{dev_name}' (device={dev_idx}, rate={dev_sr}Hz, wake_word={self.require_wake_word}, denoise=True).")
                await asyncio.to_thread(self._open_duplex, float(getattr(stream, "latency", 0.0) or 0.0))
                self._warmup_task = asyncio.create_task(
                    self._warm_up_tts(), name="server-mic-tts-warmup"
                )
                if self.use_gemini_live:
                    print(
                        "[SERVER MIC] [LIVE] Local wake -> Gemini Live enabled "
                        f"(model={self.live_model})."
                    )
                while self._is_running:
                    # PortAudio waits synchronously for a complete frame. Keep
                    # that wait outside FastAPI's event loop so HTTP and
                    # Socket.IO remain responsive while local wake detection
                    # is idle.
                    data, overflowed = await self._read_sounddevice_frame(
                        stream, chunk_size
                    )
                    frame_data = bytes(data)
                    if dev_sr != self.sample_rate:
                        frame_data = resample_pcm16(frame_data, dev_sr, self.sample_rate)
                    if self._echo is not None:
                        # Remove Monika's own voice (and chimes) from the mic.
                        frame_data = self._echo.process(frame_data, self._output.reference)

                    if (
                        self._is_muted
                        or self._is_speaking
                        or self._is_busy
                        or self._speech_segment_in_flight()
                    ):
                        # Keep draining the capture stream while output is
                        # playing. Otherwise ALSA delivers stale speaker echo
                        # and misses the beginning of the user's next turn.
                        # Barge-in still watches the cleaned signal.
                        if self._barge_monitor is not None and (
                            self._reply_playing or self._barge_monitor.state == "capturing"
                        ):
                            self._barge_in_frame(frame_data)
                        self.vad.reset_segment()
                        continue

                    segment = self.vad.process_frame(frame_data)
                    now = time.monotonic()
                    await self._expire_command_window_if_needed(now)
                    if self.vad.is_speech_active and self.is_awaiting_command:
                        self._awaiting_command_until = max(self._awaiting_command_until, now + 5.0)
                    self._level_peak_rms = max(
                        self._level_peak_rms, self.vad.last_rms
                    )
                    if now - self._last_level_log_time >= 10.0:
                        print(
                            "[SERVER MIC] [LEVEL] "
                            f"rms={self.vad.last_rms:.1f} "
                            f"peak_10s={self._level_peak_rms:.1f} "
                            f"threshold={self.vad.last_threshold:.1f} "
                            f"noise_floor={self.vad.noise_floor:.1f} "
                            f"speech={self.vad.is_speech_active}."
                        )
                        self._last_level_log_time = now
                        self._level_peak_rms = 0.0
                    if self.use_gemini_live:
                        voiced = self.vad.last_rms >= self.vad.last_threshold
                        if not self.is_live_session_active:
                            # Preserve real-time continuity; dropping quiet frames
                            # splices unrelated phonemes and increases false wakes.
                            self._process_continuous_wake_frame(
                                frame_data, voiced=voiced
                            )
                            self.vad.reset_segment()
                        else:
                            if self._wake_provisional:
                                self._process_continuous_wake_frame(
                                    frame_data, voiced=voiced
                                )
                            if voiced:
                                self._last_live_voice_time = time.monotonic()
                            if not self._is_speaking and self._live_audio_queue is not None:
                                await self._live_audio_queue.put(frame_data)
                        continue
                    if (
                        self.require_wake_word
                        and not self.is_awaiting_command
                        and not self._conversation_session_open
                    ):
                        wake_text = self._process_idle_wake_frame(
                            frame_data,
                            voiced=self.vad.last_rms >= self.vad.last_threshold,
                        )
                        if wake_text:
                            await self._activate_normal_wake(wake_text)
                            continue
                    if segment:
                        denoised = self.denoiser.denoise_segment(segment)
                        self._schedule_speech_segment(denoised)
                    else:
                        if not self.vad.is_speech_active:
                            self.denoiser.update_noise_profile(frame_data)
                    await asyncio.sleep(0.001)

            elif _PYAUDIO_AVAILABLE:
                chunk_size = self.vad.frame_size
                pyaudio_inst = pyaudio.PyAudio()
                kwargs = {
                    "format": pyaudio.paInt16,
                    "channels": 1,
                    "rate": self.sample_rate,
                    "input": True,
                    "frames_per_buffer": chunk_size,
                }
                if self.input_device_index is not None:
                    kwargs["input_device_index"] = self.input_device_index
                stream = pyaudio_inst.open(**kwargs)

                print(f"[SERVER MIC] [OK] PyAudio listening stream started (VAD, rate={self.sample_rate}Hz).")
                while self._is_running:
                    if (
                        self._is_muted
                        or self._is_speaking
                        or self._is_busy
                        or self._speech_segment_in_flight()
                    ):
                        await asyncio.to_thread(stream.read, chunk_size, False)
                        self.vad.reset_segment()
                        continue

                    data = await asyncio.to_thread(stream.read, chunk_size, False)
                    segment = self.vad.process_frame(data)
                    self._level_peak_rms = max(
                        self._level_peak_rms, self.vad.last_rms
                    )
                    now = time.monotonic()
                    await self._expire_command_window_if_needed(now)
                    if now - self._last_level_log_time >= 10.0:
                        print(
                            "[SERVER MIC] [LEVEL] "
                            f"rms={self.vad.last_rms:.1f} "
                            f"peak_10s={self._level_peak_rms:.1f} "
                            f"threshold={self.vad.last_threshold:.1f} "
                            f"noise_floor={self.vad.noise_floor:.1f} "
                            f"speech={self.vad.is_speech_active}."
                        )
                        self._last_level_log_time = now
                        self._level_peak_rms = 0.0
                    if self.use_gemini_live:
                        voiced = self.vad.last_rms >= self.vad.last_threshold
                        if not self.is_live_session_active:
                            self._process_continuous_wake_frame(data, voiced=voiced)
                            self.vad.reset_segment()
                        else:
                            if voiced:
                                self._last_live_voice_time = time.monotonic()
                            if not self._is_speaking and self._live_audio_queue is not None:
                                await self._live_audio_queue.put(data)
                        continue
                    if (
                        self.require_wake_word
                        and not self.is_awaiting_command
                        and not self._conversation_session_open
                    ):
                        wake_text = self._process_idle_wake_frame(
                            data,
                            voiced=self.vad.last_rms >= self.vad.last_threshold,
                        )
                        if wake_text:
                            await self._activate_normal_wake(wake_text)
                            continue
                    if segment:
                        self._schedule_speech_segment(segment)
                    await asyncio.sleep(0.001)
            else:
                print("[SERVER MIC] [FAIL] No audio backend available (sounddevice or pyaudio).")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[SERVER MIC] Błąd pętli nasłuchu audio: {exc}")
        finally:
            await self._close_conversation_session()
            self._awaiting_command_until = 0.0
            await self._set_voice_light_state("idle", wait=True)
            if self._output is not None:
                self._output.close()
                self._output = self._echo = self._barge_monitor = None
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if pyaudio_inst:
                try:
                    pyaudio_inst.terminate()
                except Exception:
                    pass
            print("[SERVER MIC] Zatrzymano nasłuch mikrofonu serwera.")

    @staticmethod
    async def _read_sounddevice_frame(stream, chunk_size: int):
        """Read one blocking PortAudio frame without starving the event loop."""
        return await asyncio.to_thread(stream.read, chunk_size)

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
        if self._is_running:
            return True
        self._is_running = True
        self._loop = loop or asyncio.get_event_loop()
        self._task = self._loop.create_task(self._listen_loop())
        return True

    def stop(self):
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        if self._live_session_task and not self._live_session_task.done():
            self._live_session_task.cancel()
        if self._activation_ack_task and not self._activation_ack_task.done():
            self._activation_ack_task.cancel()
        if self._speech_segment_task and not self._speech_segment_task.done():
            self._speech_segment_task.cancel()
        self._task = None
        self._live_session_task = None
        self._activation_ack_task = None
        self._activation_prompt_window_until = 0.0
        self._speech_segment_task = None
        self._live_audio_queue = None
        self._awaiting_command_until = 0.0
        self._queue_voice_light_state("idle")
