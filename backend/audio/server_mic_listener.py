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
import re
import shutil
import subprocess
import tempfile
import time
import wave
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np

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
    r"^\s*(?:hej|hey|he|ej|okej|ok)\s+(?:monik(?:a|o)|moniczk(?:a|o))[\s,\.!\?]*",
    re.IGNORECASE,
)
_CONTINUOUS_WAKE_RE = re.compile(
    r"^(?:hej|hey|he|ej|okej|ok)\s+monik(?:a|o)\b",
    re.IGNORECASE,
)
_WAKE_CANDIDATE_RE = re.compile(
    r"^(?:hej|hey|he|ej|okej|ok|monik\w*)\b",
    re.IGNORECASE,
)


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

                # Max speech duration protection (7.5s max)
                if len(self.active_speech_frames) > int(7500 / self.frame_duration_ms):
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
        input_device_index: Optional[int] = None,
        input_device_name: Optional[str] = None,
        output_device_index: Optional[int] = None,
        sample_rate: int = 16000,
        require_wake_word: bool = False,
        gemini_api_key: Optional[str] = None,
        gemini_voice: str = "Leda",
        on_turn_finished: Optional[Callable[[str, str], Any]] = None,
        use_gemini_live: Optional[bool] = None,
        kasa_agent=None,
        home_assistant_agent=None,
        voice_light_feedback=None,
    ):
        self.conversation_handler = conversation_handler
        self.input_device_index = input_device_index
        self.input_device_name = input_device_name
        self.output_device_index = output_device_index
        self.sample_rate = int(sample_rate or 16000)
        self.require_wake_word = bool(require_wake_word)
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_voice = str(gemini_voice or "Leda")
        self.on_turn_finished = on_turn_finished
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
        self.use_gemini_live = (
            str(os.getenv("SERVER_MIC_USE_GEMINI_LIVE", "true")).lower()
            in {"1", "true", "yes", "on"}
            if use_gemini_live is None
            else bool(use_gemini_live)
        )
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
        )
        self.denoiser = AudioDenoiseProcessor(sample_rate=self.sample_rate)
        self._last_transcribe_time = 0.0
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
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._vosk_model = None
        self._vosk_unavailable_reason = ""
        self._wake_recognition_lock = asyncio.Lock()
        self._continuous_wake_recognizer = None
        self._continuous_wake_audio: Deque[bytes] = collections.deque(maxlen=84)
        self._last_wake_voice_time = 0.0
        self._partial_wake_text = ""
        self._partial_wake_hits = 0
        self._last_partial_wake_time = 0.0
        self._wake_provisional = False
        self._wake_verified_event: Optional[asyncio.Event] = None
        self._pending_initial_pcm = b""
        self._live_audio_queue: Optional[asyncio.Queue] = None
        self._live_session_task: Optional[asyncio.Task] = None
        self._activation_chime_task: Optional[asyncio.Task] = None
        self._last_live_voice_time = 0.0

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
            self._play_wake_chime(capture_safe=True),
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
        if not wav_bytes:
            return ""

        now = time.time()
        if (now - self._last_transcribe_time) < 0.6:
            return ""
        self._last_transcribe_time = now

        preferred = os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-2.5-flash")
        candidates = [preferred, "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
        models_to_try = []
        for m in candidates:
            if m not in models_to_try:
                models_to_try.append(m)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.gemini_api_key)
            prompt = (
                "Transcribe this voice audio accurately in Polish as plain text. "
                "The speaker is addressing an AI assistant named Monika (common wake words: 'Hej Monika', 'Monika', 'Moniko', 'Okej Monika', 'Monia'). "
                "Preserve original spoken words accurately. "
                "Do not add commentary, labels, quotes, timestamps, or markdown. "
                "If the audio is completely silent or unintelligible, return an empty string."
            )

            last_exc = None
            for model_name in models_to_try:
                try:
                    response = await client.aio.models.generate_content(
                        model=model_name,
                        contents=[
                            prompt,
                            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                        ],
                    )
                    text = str(getattr(response, "text", "") or "").strip()
                    if text.lower() in {"", "unintelligible", "[unintelligible]"}:
                        return ""
                    return text
                except Exception as exc:
                    last_exc = exc
                    if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                        continue
                    break

            if last_exc:
                print(f"[SERVER MIC] Transcription notice: {last_exc}")
            return ""
        except Exception as exc:
            print(f"[SERVER MIC] Transcription failed: {exc}")
            return ""

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
                try:
                    kwargs = {
                        "samplerate": target_sr,
                        "channels": target_channels,
                        "dtype": "int16",
                        "device": out_idx,
                    }
                    stream = await asyncio.to_thread(sd.RawOutputStream, **kwargs)
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
                except Exception:
                    pass
            await asyncio.sleep(0.15)
            self._is_speaking = False
            self.vad.reset_segment()

    async def _synthesize_and_play(self, text: str) -> None:
        """Synthesize one reply and play it through the server audio device."""
        if not text or text.startswith("("):
            return

        try:
            print(f"[SERVER MIC] [TTS] Synthesizing speech with voice '{self.gemini_voice}'...")
            from backend.conversation.speech import GeminiSpeechSynthesizer, SpeechSynthesisRequest

            synthesizer = GeminiSpeechSynthesizer(api_key=self.gemini_api_key)
            result = await synthesizer.synthesize(
                SpeechSynthesisRequest(text=text, voice=self.gemini_voice)
            )
            if result and result.audio:
                print(
                    f"[SERVER MIC] [TTS] Audio ready ({len(result.audio)} bytes, "
                    f"{result.sample_rate}Hz). Starting playback..."
                )
                await self.play_audio_locally(result.audio, sample_rate=result.sample_rate)
                return
        except Exception as exc:
            print(f"[SERVER MIC] [TTS] Gemini unavailable ({exc}); using local fallback.")

        local_audio = await self._synthesize_with_flite(text)
        if local_audio:
            print("[SERVER MIC] [TTS] Playing local fallback voice.")
            await self.play_audio_locally(local_audio, sample_rate=24000)
            return
        raise RuntimeError("No working speech synthesizer is available")

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

    async def _play_wake_chime(self, *, capture_safe: bool = False) -> None:
        """Play an API-independent acknowledgement that command mode is open."""
        sample_rate = 24000
        chunks = []
        for frequency in (660.0, 880.0):
            duration = 0.11
            count = int(sample_rate * duration)
            timeline = np.arange(count, dtype=np.float64) / sample_rate
            envelope = np.sin(np.linspace(0.0, math.pi, count)) ** 2
            tone = (4200.0 * envelope * np.sin(2.0 * math.pi * frequency * timeline))
            chunks.append(tone.astype(np.int16))
            chunks.append(np.zeros(int(sample_rate * 0.035), dtype=np.int16))
        await self.play_audio_locally(
            np.concatenate(chunks).tobytes(),
            sample_rate,
            suppress_capture=not capture_safe,
        )

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
            "Jeżeli użytkownik powiedział tylko twoje imię ('Monika' lub odmianę), odpowiedz krótko 'Słucham?' i zaczekaj na "
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

                if not initial_pcm and self._pending_initial_pcm:
                    initial_pcm = self._pending_initial_pcm
                self._pending_initial_pcm = b""
                print("[SERVER MIC] [LIVE] Realtime session verified and ready.")
                if self.voice_light_feedback:
                    asyncio.create_task(self.voice_light_feedback.set_state("listening"))

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
                                        asyncio.create_task(self.voice_light_feedback.set_state("thinking"))

                            tool_call = getattr(response, "tool_call", None)
                            if tool_call:
                                if self.voice_light_feedback and player_task is None:
                                    asyncio.create_task(self.voice_light_feedback.set_state("thinking"))
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
                                                asyncio.create_task(self.voice_light_feedback.set_state("speaking"))
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
                                        asyncio.create_task(self.voice_light_feedback.set_state("listening"))
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
            self._wake_provisional = False
            self._wake_verified_event = None
            self._pending_initial_pcm = b""
            self._live_audio_queue = None
            if self._live_session_task is asyncio.current_task():
                self._live_session_task = None
            self.vad.reset_segment()
            self._reset_continuous_wake_recognizer()
            if self.voice_light_feedback:
                try:
                    await self.voice_light_feedback.set_state("idle")
                except Exception as _fe:
                    print(f"[SERVER MIC] Error resetting voice light to idle: {_fe}")
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

    async def _handle_speech_segment(self, raw_pcm: bytes):
        """Process recorded speech segment."""
        if self._is_muted or self._is_speaking or self._is_busy:
            return

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

        print(f"[SERVER MIC] [VAD] Detected speech segment ({len(raw_pcm)/32000.0:.2f}s, rms={rms:.1f}). Transcribing...")

        wav_bytes = _raw_pcm_to_wav(raw_pcm, sample_rate=self.sample_rate)
        transcript = await self.transcribe_speech(wav_bytes)
        if not transcript:
            return

        print(f"[SERVER MIC] [HEARD] \"{transcript}\"")
        if self.is_awaiting_command:
            # The preceding turn opened follow-up window or was wake word. Accept without repeating name.
            matched, prompt = True, transcript
            self._awaiting_command_until = 0.0
            print("[SERVER MIC] [CONVERSATION] Follow-up turn received.")
        else:
            # Clear an expired window before processing a fresh wake word.
            self._awaiting_command_until = 0.0
            matched, prompt = self.extract_wake_word(transcript)
        if not matched:
            print(f"[SERVER MIC] [IGNORED] No wake word in: \"{transcript}\"")
            return

        if self.voice_light_feedback:
            asyncio.create_task(self.voice_light_feedback.set_state("listening"))

        if self.require_wake_word and not prompt:
            acknowledgement = "Słucham?"
            print(
                "[SERVER MIC] [WAKE] Wake word detected; listening for a command "
                f"for {self.wake_listen_timeout:.1f}s."
            )
            async with self._turn_lock:
                self._is_busy = True
                try:
                    await self._play_wake_chime()
                    if self.on_turn_finished:
                        callback = self.on_turn_finished(transcript, acknowledgement)
                        if asyncio.iscoroutine(callback):
                            await callback
                except Exception as exc:
                    print(f"[SERVER MIC] Błąd potwierdzenia słowa wybudzającego: {exc}")
                finally:
                    # Start the full command window after the acknowledgement;
                    # synthesis and playback latency must not consume it.
                    self._awaiting_command_until = (
                        time.monotonic() + self.wake_listen_timeout
                    )
                    self.vad.reset_segment()
                    self._is_busy = False
            return

        async with self._turn_lock:
            self._is_busy = True
            try:
                if self.voice_light_feedback:
                    asyncio.create_task(self.voice_light_feedback.set_state("thinking"))

                reply_text = ""
                if self.conversation_handler:
                    try:
                        res = self.conversation_handler(prompt)
                        if asyncio.iscoroutine(res):
                            reply_text = await res
                        else:
                            reply_text = str(res or "")
                    except Exception as exc:
                        print(f"[SERVER MIC] Error processing reply: {exc}")
                        reply_text = "Przepraszam, coś poszło nie tak przy przetwarzaniu."

                print(f"[SERVER MIC] [REPLY] \"{reply_text}\"")

                # Synthesize and play response
                if reply_text and not reply_text.startswith("("):
                    try:
                        if self.voice_light_feedback:
                            asyncio.create_task(self.voice_light_feedback.set_state("speaking"))
                        await self._synthesize_and_play(reply_text)
                    except Exception as exc:
                        print(f"[SERVER MIC] Błąd syntezy mowy: {exc}")

                if self.on_turn_finished:
                    try:
                        cb = self.on_turn_finished(transcript, reply_text)
                        if asyncio.iscoroutine(cb):
                            await cb
                    except Exception:
                        pass
            finally:
                # Generous echo dissipation delay after full response and playback
                await asyncio.sleep(0.6)
                self.vad.reset_segment()
                followup_sec = float(os.getenv("SERVER_MIC_FOLLOWUP_TIMEOUT", "8.0"))
                if followup_sec > 0:
                    self._awaiting_command_until = time.monotonic() + followup_sec
                    print(f"[SERVER MIC] [CONVERSATION] Follow-up window open for {followup_sec:.1f}s.")
                if self.voice_light_feedback:
                    try:
                        await self.voice_light_feedback.set_state("idle")
                    except Exception:
                        pass
                self._is_busy = False

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

            if self.use_gemini_live:
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
                if self.use_gemini_live:
                    print(
                        "[SERVER MIC] [LIVE] Local wake -> Gemini Live enabled "
                        f"(model={self.live_model})."
                    )
                while self._is_running:
                    if self._is_muted or self._is_speaking or self._is_busy:
                        # Keep draining the capture stream while output is
                        # playing. Otherwise ALSA delivers stale speaker echo
                        # and misses the beginning of the user's next turn.
                        await self._read_sounddevice_frame(stream, chunk_size)
                        self.vad.reset_segment()
                        continue

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

                    segment = self.vad.process_frame(frame_data)
                    now = time.monotonic()
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
                    if segment:
                        denoised = self.denoiser.denoise_segment(segment)
                        asyncio.create_task(self._handle_speech_segment(denoised))
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
                    if self._is_muted or self._is_speaking or self._is_busy:
                        await asyncio.to_thread(stream.read, chunk_size, False)
                        self.vad.reset_segment()
                        continue

                    data = await asyncio.to_thread(stream.read, chunk_size, False)
                    segment = self.vad.process_frame(data)
                    self._level_peak_rms = max(
                        self._level_peak_rms, self.vad.last_rms
                    )
                    now = time.monotonic()
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
                    if segment:
                        asyncio.create_task(self._handle_speech_segment(segment))
                    await asyncio.sleep(0.001)
            else:
                print("[SERVER MIC] [FAIL] No audio backend available (sounddevice or pyaudio).")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[SERVER MIC] Błąd pętli nasłuchu audio: {exc}")
        finally:
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
        self._task = None
        self._live_session_task = None
        self._live_audio_queue = None
