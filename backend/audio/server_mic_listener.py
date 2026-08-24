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
    r"^\s*(?:hej\s+|hey\s+|droga\s+|okej\s+|ok\s+)?monik(?:a|o|e|ą|i)\b[\s,\.!\?]*",
    re.IGNORECASE,
)
_ANYWHERE_WAKE_WORD_RE = re.compile(
    r"\bmonik(?:a|o|e|ą|i)\b",
    re.IGNORECASE,
)


class AdaptiveEnergyVAD:
    """Lightweight adaptive energy and zero-crossing VAD with dynamic noise tracking."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold_ratio: float = 2.4,
        min_speech_duration_ms: int = 180,
        trailing_silence_duration_ms: int = 850,
        pre_roll_duration_ms: int = 350,
    ):
        self.sample_rate = int(sample_rate)
        self.frame_duration_ms = int(frame_duration_ms)
        self.frame_size = int(self.sample_rate * (self.frame_duration_ms / 1000.0))
        self.frame_bytes = self.frame_size * 2  # 16-bit PCM

        self.energy_threshold_ratio = float(energy_threshold_ratio)
        self.min_speech_frames = max(2, int(min_speech_duration_ms / self.frame_duration_ms))
        self.trailing_silence_frames = max(4, int(trailing_silence_duration_ms / self.frame_duration_ms))
        self.pre_roll_frames = max(3, int(pre_roll_duration_ms / self.frame_duration_ms))

        self.noise_floor: float = 120.0
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
        threshold = max(200.0, self.noise_floor * self.energy_threshold_ratio)
        voiced = rms > threshold

        if not voiced and not self.is_speech_active:
            # Update ambient noise floor estimate
            self.noise_floor = (1.0 - self.noise_alpha) * self.noise_floor + self.noise_alpha * max(40.0, rms)

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
        self._is_running = False
        self._is_muted = False
        self._is_speaking = False
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
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.gemini_api_key)
            prompt = (
                "Transcribe this voice audio as plain text. "
                "Preserve the original language. "
                "Do not add commentary, labels, quotes, timestamps, or markdown. "
                "If the audio is unintelligible, return an empty string."
            )
            response = await client.aio.models.generate_content(
                model=os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-2.5-flash"),
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
            print(f"[SERVER MIC] Transcription failed: {exc}")
            return ""

    async def play_audio_locally(self, pcm_bytes: bytes, sample_rate: int = 24000):
        """Play synthesized audio out of server speakers/headphones."""
        if not pcm_bytes:
            return

        self._is_speaking = True
        try:
            if _SOUNDDEVICE_AVAILABLE:
                try:
                    kwargs = {
                        "samplerate": sample_rate,
                        "channels": 1,
                        "dtype": "int16",
                    }
                    if self.output_device_index is not None:
                        kwargs["device"] = self.output_device_index
                    stream = await asyncio.to_thread(sd.RawOutputStream, **kwargs)
                    stream.start()
                    await asyncio.to_thread(stream.write, pcm_bytes)
                    await asyncio.sleep(len(pcm_bytes) / (sample_rate * 2.0) + 0.1)
                    stream.stop()
                    stream.close()
                    return
                except Exception as exc:
                    print(f"[SERVER MIC] SoundDevice playback failed, falling back: {exc}")

            if _PYAUDIO_AVAILABLE:
                p = pyaudio.PyAudio()
                try:
                    kwargs = {
                        "format": pyaudio.paInt16,
                        "channels": 1,
                        "rate": sample_rate,
                        "output": True,
                    }
                    if self.output_device_index is not None:
                        kwargs["output_device_index"] = self.output_device_index
                    stream = p.open(**kwargs)
                    stream.write(pcm_bytes)
                    stream.stop_stream()
                    stream.close()
                finally:
                    p.terminate()
        except Exception as exc:
            print(f"[SERVER MIC] Audio playback error: {exc}")
        finally:
            # Short grace period for echo tail dissipation
            await asyncio.sleep(0.35)
            self._is_speaking = False
            self.vad.reset_segment()

    async def _handle_speech_segment(self, raw_pcm: bytes):
        """Process recorded speech segment."""
        if self._is_muted or self._is_speaking:
            return

        wav_bytes = _raw_pcm_to_wav(raw_pcm, sample_rate=self.sample_rate)
        transcript = await self.transcribe_speech(wav_bytes)
        if not transcript:
            return

        print(f"[SERVER MIC] [HEARD] \"{transcript}\"")
        matched, prompt = self.extract_wake_word(transcript)
        if not matched:
            print(f"[SERVER MIC] [IGNORED] No wake word in: \"{transcript}\"")
            return

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
                from backend.conversation.speech import GeminiSpeechSynthesizer, SpeechSynthesisRequest
                synthesizer = GeminiSpeechSynthesizer(api_key=self.gemini_api_key)
                res = await synthesizer.synthesize(SpeechSynthesisRequest(text=reply_text, voice=self.gemini_voice))
                if res and res.audio:
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

    async def _listen_loop(self):
        """Main listening loop capturing chunks from the microphone."""
        chunk_size = self.vad.frame_size
        stream = None
        pyaudio_inst = None

        try:
            if _SOUNDDEVICE_AVAILABLE:
                kwargs = {
                    "samplerate": self.sample_rate,
                    "channels": 1,
                    "dtype": "int16",
                    "blocksize": chunk_size,
                }
                if self.input_device_index is not None:
                    kwargs["device"] = self.input_device_index
                stream = sd.RawInputStream(**kwargs)
                stream.start()

                print(f"[SERVER MIC] [OK] Listening stream started (VAD, rate={self.sample_rate}Hz).")
                while self._is_running:
                    if self._is_muted or self._is_speaking:
                        await asyncio.sleep(0.05)
                        continue

                    data, overflowed = stream.read(chunk_size)
                    segment = self.vad.process_frame(bytes(data))
                    if segment:
                        asyncio.create_task(self._handle_speech_segment(segment))
                    await asyncio.sleep(0.001)

            elif _PYAUDIO_AVAILABLE:
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
                    if self._is_muted or self._is_speaking:
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

