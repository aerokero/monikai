"""Continuous background microphone listener with local Voice Activity Detection (VAD).

Designed for 24/7 low-resource server-side listening. Analyzes audio locally
and only contacts Gemini API when speech is actively detected.
"""

from __future__ import annotations

import asyncio
import collections
import io
import math
import os
import re
import shutil
import subprocess
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
    r"^\s*(?:hej\s+|hey\s+|droga\s+|okej\s+|ok\s+)?(?:monik(?:a|o|e|ą|i|ę|u)|moni(?:a|o|e|ą|i|ę|ś|u)|moniczk(?:a|o|e|ą|i|ę)|helk(?:a|o|e|ą|i)|kocha\b)[\s,\.!\?]*",
    re.IGNORECASE,
)
_ANYWHERE_WAKE_WORD_RE = re.compile(
    r"\b(?:monik(?:a|o|e|ą|i|ę|u)|moni(?:a|o|e|ą|i|ę|ś|u)|moniczk(?:a|o|e|ą|i|ę)|helk(?:a|o))\b",
    re.IGNORECASE,
)


class AdaptiveEnergyVAD:
    """Lightweight adaptive energy and zero-crossing VAD with dynamic noise tracking."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold_ratio: float = 2.2,
        min_speech_duration_ms: int = 200,
        trailing_silence_duration_ms: int = 800,
        pre_roll_duration_ms: int = 550,
    ):
        self.sample_rate = int(sample_rate)
        self.frame_duration_ms = int(frame_duration_ms)
        self.frame_size = int(self.sample_rate * (self.frame_duration_ms / 1000.0))
        self.frame_bytes = self.frame_size * 2  # 16-bit PCM

        self.energy_threshold_ratio = float(energy_threshold_ratio)
        self.min_speech_frames = max(2, int(min_speech_duration_ms / self.frame_duration_ms))
        self.trailing_silence_frames = max(4, int(trailing_silence_duration_ms / self.frame_duration_ms))
        self.pre_roll_frames = max(3, int(pre_roll_duration_ms / self.frame_duration_ms))

        self.noise_floor: float = 80.0
        self.noise_alpha: float = 0.05

        self.pre_roll_buffer: Deque[bytes] = collections.deque(maxlen=self.pre_roll_frames)
        self.active_speech_frames: List[bytes] = []
        self.is_speech_active: bool = False
        self.consecutive_speech_frames: int = 0
        self.consecutive_silence_frames: int = 0

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
        threshold = max(180.0, self.noise_floor * self.energy_threshold_ratio)
        voiced = rms > threshold

        if not voiced and not self.is_speech_active:
            # Update ambient noise floor estimate
            self.noise_floor = (1.0 - self.noise_alpha) * self.noise_floor + self.noise_alpha * max(30.0, rms)

        return voiced, rms

    def process_frame(self, frame_bytes: bytes) -> Optional[bytes]:
        """Process a single audio frame. Returns completed audio segment bytes when speech ends."""
        if len(frame_bytes) < self.frame_bytes:
            return None

        voiced, _ = self.is_frame_voiced(frame_bytes)

        if voiced:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0

            if not self.is_speech_active:
                if self.consecutive_speech_frames >= self.min_speech_frames:
                    self.is_speech_active = True
                    self.active_speech_frames = list(self.pre_roll_buffer)
                    self.active_speech_frames.append(frame_bytes)
                else:
                    self.pre_roll_buffer.append(frame_bytes)
            else:
                self.active_speech_frames.append(frame_bytes)
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
    """Resample 16-bit mono PCM bytes from src_rate to dst_rate."""
    if not pcm_bytes or src_rate == dst_rate:
        return pcm_bytes
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    if len(samples) == 0:
        return pcm_bytes
    target_len = int(round(len(samples) * dst_rate / src_rate))
    x_old = np.linspace(0, 1, len(samples), endpoint=False)
    x_new = np.linspace(0, 1, target_len, endpoint=False)
    resampled = np.interp(x_new, x_old, samples).astype(np.int16)
    return resampled.tobytes()


class AudioDenoiseProcessor:
    """Real-time audio denoiser with high-pass filtering, dynamic spectral subtraction, and AGC."""

    def __init__(
        self,
        sample_rate: int = 16000,
        n_fft: int = 512,
        hop_length: int = 256,
        noise_reduction_db: float = 9.0,
        hp_cutoff_hz: float = 90.0,
    ):
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.window = np.hanning(n_fft).astype(np.float32)
        self.noise_profile = np.zeros(n_fft // 2 + 1, dtype=np.float32)
        self.has_noise_profile = False
        self.noise_alpha = 0.08
        self.reduction_factor = 1.0 - 10.0 ** (-noise_reduction_db / 20.0)

        # 1st-order IIR High-Pass Filter (removes rumble, desk vibrations, fan 50Hz hum)
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
        """Denoise a complete speech segment and normalize volume for crisp transcription."""
        if not raw_pcm:
            return raw_pcm

        samples = np.frombuffer(raw_pcm, dtype=np.int16)
        if len(samples) < self.n_fft:
            return raw_pcm

        filtered = self.apply_high_pass(samples)
        if not self.has_noise_profile:
            return np.clip(filtered, -32768, 32767).astype(np.int16).tobytes()

        num_frames = max(1, (len(filtered) - self.n_fft) // self.hop_length + 1)
        out_len = (num_frames - 1) * self.hop_length + self.n_fft
        out = np.zeros(out_len, dtype=np.float32)
        window_sum = np.zeros(out_len, dtype=np.float32)

        for i in range(num_frames):
            start = i * self.hop_length
            end = start + self.n_fft
            frame = filtered[start:end]
            if len(frame) < self.n_fft:
                break

            fft_frame = np.fft.rfft(frame * self.window)
            magnitude = np.abs(fft_frame)
            phase = np.angle(fft_frame)

            # Spectral subtraction with soft spectral floor to prevent musical noise
            noise_est = self.noise_profile * self.reduction_factor
            subtracted = np.maximum(magnitude - (noise_est * 1.0), 0.25 * magnitude)
            clean_fft = subtracted * np.exp(1j * phase)
            reconstructed = np.fft.irfft(clean_fft) * self.window

            out[start:end] += reconstructed
            window_sum[start:end] += self.window ** 2

        mask = window_sum > 1e-4
        out[mask] /= window_sum[mask]
        clean_samples = out[:len(samples)]

        # Automatic Gain Control / Normalization
        peak = float(np.max(np.abs(clean_samples))) if len(clean_samples) > 0 else 0.0
        if peak > 200.0:
            target_peak = 22000.0
            gain = min(target_peak / peak, 4.0)
            clean_samples = clean_samples * gain

        return np.clip(clean_samples, -32768, 32767).astype(np.int16).tobytes()


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

        self.vad = AdaptiveEnergyVAD(sample_rate=self.sample_rate)
        self.denoiser = AudioDenoiseProcessor(sample_rate=self.sample_rate)
        self._last_transcribe_time = 0.0
        self._is_running = False
        self._is_muted = False
        self._is_speaking = False
        self._is_busy = False
        self._turn_lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

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
            return True, clean or text

        if _ANYWHERE_WAKE_WORD_RE.search(text):
            return True, text

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

    async def play_audio_locally(self, pcm_bytes: bytes, sample_rate: int = 24000):
        """Play synthesized audio out of server speakers/headphones with automatic resampling and stereo expansion."""
        if not pcm_bytes:
            return

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
                    await asyncio.sleep(duration_sec + 0.1)
                    stream.stop()
                    stream.close()
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
            # Short grace period for echo tail dissipation
            await asyncio.sleep(0.4)
            self._is_speaking = False
            self.vad.reset_segment()

    async def _handle_speech_segment(self, raw_pcm: bytes):
        """Process recorded speech segment."""
        if self._is_muted or self._is_speaking or self._is_busy:
            return

        min_bytes = int(self.sample_rate * 2 * 0.4)
        if len(raw_pcm) < min_bytes:
            return

        samples = np.frombuffer(raw_pcm, dtype=np.int16)
        rms = float(math.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        if rms < 160.0:
            return

        print(f"[SERVER MIC] [VAD] Detected speech segment ({len(raw_pcm)/32000.0:.2f}s, rms={rms:.1f}). Transcribing...")

        wav_bytes = _raw_pcm_to_wav(raw_pcm, sample_rate=self.sample_rate)
        transcript = await self.transcribe_speech(wav_bytes)
        if not transcript:
            return

        print(f"[SERVER MIC] [HEARD] \"{transcript}\"")
        matched, prompt = self.extract_wake_word(transcript)
        if not matched:
            print(f"[SERVER MIC] [IGNORED] No wake word in: \"{transcript}\"")
            return

        async with self._turn_lock:
            self._is_busy = True
            try:
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
                        print(f"[SERVER MIC] [TTS] Synthesizing speech with voice '{self.gemini_voice}'...")
                        from backend.conversation.speech import GeminiSpeechSynthesizer, SpeechSynthesisRequest
                        synthesizer = GeminiSpeechSynthesizer(api_key=self.gemini_api_key)
                        res = await synthesizer.synthesize(SpeechSynthesisRequest(text=reply_text, voice=self.gemini_voice))
                        if res and res.audio:
                            print(f"[SERVER MIC] [TTS] Audio ready ({len(res.audio)} bytes, {res.sample_rate}Hz). Starting playback...")
                            await self.play_audio_locally(res.audio, sample_rate=res.sample_rate)
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
                await asyncio.sleep(0.8)
                self.vad.reset_segment()
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
                while self._is_running:
                    if self._is_muted or self._is_speaking or self._is_busy:
                        await asyncio.sleep(0.05)
                        continue

                    data, overflowed = stream.read(chunk_size)
                    frame_data = bytes(data)
                    if dev_sr != self.sample_rate:
                        samples = np.frombuffer(frame_data, dtype=np.int16)
                        target_len = self.vad.frame_size
                        x_old = np.linspace(0, 1, len(samples), endpoint=False)
                        x_new = np.linspace(0, 1, target_len, endpoint=False)
                        resampled = np.interp(x_new, x_old, samples).astype(np.int16)
                        frame_data = resampled.tobytes()

                    segment = self.vad.process_frame(frame_data)
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
                        await asyncio.sleep(0.05)
                        continue

                    data = await asyncio.to_thread(stream.read, chunk_size, False)
                    segment = self.vad.process_frame(data)
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
        self._task = None

