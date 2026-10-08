"""Full-duplex voice: one persistent speaker stream, echo cancellation and
language-independent barge-in.

Speaker and microphone share a room, so the microphone hears Monika.  We know
exactly what we play, so WebRTC AEC3 subtracts it from the microphone signal;
Silero VAD then tells human speech (in any language) from what is left.  No
stop words: the user simply starts talking, as with a person.
"""

from __future__ import annotations

import asyncio
import collections
import threading
from typing import Deque, List, Optional, Tuple

import numpy as np

REF_RATE = 16000  # echo canceller / VAD rate
_APM_FRAME = REF_RATE // 100  # WebRTC processes 10 ms frames


def _resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or not len(samples):
        return samples
    target = int(round(len(samples) * dst_rate / src_rate))
    positions = np.linspace(0, len(samples) - 1, target)
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.int16)


def pick_output_format(sd, device: int, preferred_rate: int = 48000) -> Tuple[int, int]:
    """First (rate, channels) the device accepts, stereo 48 kHz preferred."""
    for rate in (preferred_rate, 44100, 24000, 16000):
        for channels in (2, 1):
            try:
                sd.check_output_settings(device=device, samplerate=rate, channels=channels)
                return rate, channels
            except Exception:
                continue
    return preferred_rate, 2


class _Clip:
    __slots__ = ("data", "ref", "frames", "pos", "ref_pos", "done", "loop", "cancelled")

    def __init__(self, data: np.ndarray, ref: np.ndarray, frames: int, loop, done):
        self.data, self.ref, self.frames = data, ref, frames
        self.pos = self.ref_pos = 0
        self.loop, self.done = loop, done
        self.cancelled = False


class AudioOutput:
    """One always-open output stream fed from a clip queue.

    Every callback also records what was sent to the speaker, resampled to
    16 kHz mono and including silence, in ``reference``: the echo canceller
    needs a continuous copy of the far-end signal.  ``gain`` ducks the voice
    smoothly, ``paused`` holds the position, ``stop()`` drops everything.
    """

    def __init__(self, rate: int, channels: int, stream_factory=None):
        self.rate, self.channels = rate, channels
        self.gain = 1.0
        self.paused = False
        self.reference: Deque[np.ndarray] = collections.deque(maxlen=500)
        self._applied_gain = 1.0
        self._clips: Deque[_Clip] = collections.deque()
        self._lock = threading.Lock()
        self._ref_carry = 0.0
        self.stream = stream_factory(self._callback) if stream_factory else None

    @classmethod
    def open(cls, sd, device: int) -> "AudioOutput":
        rate, channels = pick_output_format(sd, device)

        def factory(callback):
            stream = sd.RawOutputStream(
                samplerate=rate, channels=channels, dtype="int16", device=device,
                callback=callback, latency=0.1,  # roomy: a Python callback must never underrun
            )
            stream.start()
            return stream

        return cls(rate, channels, factory)

    @property
    def latency_ms(self) -> float:
        return float(getattr(self.stream, "latency", 0.0) or 0.0) * 1000.0

    @property
    def busy(self) -> bool:
        return bool(self._clips)

    async def play(self, pcm: bytes, sample_rate: int) -> None:
        """Queue mono int16 PCM and wait until it has been sent to the speaker."""
        mono = np.frombuffer(pcm, dtype=np.int16)
        data = _resample(mono, sample_rate, self.rate)
        if self.channels == 2:
            data = np.repeat(data, 2)
        loop = asyncio.get_running_loop()
        clip = _Clip(data, _resample(mono, sample_rate, REF_RATE), len(data) // self.channels, loop, loop.create_future())
        with self._lock:
            self._clips.append(clip)
        try:
            await clip.done
        except asyncio.CancelledError:
            clip.cancelled = True
            raise

    def stop(self) -> None:
        with self._lock:
            clips, self._clips = list(self._clips), collections.deque()
        for clip in clips:
            self._finish(clip)

    def close(self) -> None:
        self.stop()
        if self.stream is not None:
            for action in ("abort", "close"):
                try:
                    getattr(self.stream, action)()
                except Exception:
                    pass

    @staticmethod
    def _finish(clip: _Clip) -> None:
        def resolve():
            if not clip.done.done():
                clip.done.set_result(None)

        clip.loop.call_soon_threadsafe(resolve)

    def _callback(self, outdata, frames, time_info, status) -> None:
        out = np.zeros(frames * self.channels, dtype=np.int16)
        ref_parts: List[np.ndarray] = []
        filled = 0
        if not self.paused:
            with self._lock:
                while filled < frames and self._clips:
                    clip = self._clips[0]
                    if clip.cancelled:
                        self._finish(self._clips.popleft())
                        continue
                    n = min(frames - filled, clip.frames - clip.pos)
                    ch = self.channels
                    out[filled * ch:(filled + n) * ch] = clip.data[clip.pos * ch:(clip.pos + n) * ch]
                    clip.pos += n
                    filled += n
                    ref_end = min(len(clip.ref), round(clip.pos * REF_RATE / self.rate))
                    ref_parts.append(clip.ref[clip.ref_pos:ref_end])
                    clip.ref_pos = ref_end
                    if clip.pos >= clip.frames:
                        self._finish(self._clips.popleft())

        # Ramp the gain across the block so ducking never clicks.
        target = 0.0 if self.paused else float(self.gain)
        if filled and (target != 1.0 or self._applied_gain != 1.0):
            ramp = np.linspace(self._applied_gain, target, frames, dtype=np.float32)
            out = (out.reshape(frames, self.channels) * ramp[:, None]).astype(np.int16).reshape(-1)
        self._applied_gain = target
        outdata[:] = out.tobytes()

        # Reference: exactly as many 16 kHz samples as this block lasted.
        self._ref_carry += frames * REF_RATE / self.rate
        count = int(self._ref_carry)
        self._ref_carry -= count
        ref = np.concatenate(ref_parts) if ref_parts else np.zeros(0, dtype=np.int16)
        ref = np.pad(ref[:count], (0, max(0, count - len(ref))))
        if target != 1.0:
            ref = (ref * target).astype(np.int16)
        self.reference.append(ref)


class EchoCanceller:
    """WebRTC AEC3 (via livekit) removing our own playback from the mic signal."""

    def __init__(self, delay_ms: float):
        from livekit import rtc

        self._rtc = rtc
        self._apm = rtc.AudioProcessingModule(echo_cancellation=True, high_pass_filter=True)
        self.delay_ms = int(max(0.0, delay_ms))
        self._ref = np.zeros(0, dtype=np.int16)

    def _frame(self, samples: bytes):
        return self._rtc.AudioFrame(samples, REF_RATE, 1, _APM_FRAME)

    def process(self, mic: bytes, reference: Deque[np.ndarray]) -> bytes:
        """Return ``mic`` (16 kHz mono int16, multiple of 10 ms) minus echo."""
        while reference:
            self._ref = np.concatenate((self._ref, reference.popleft()))
        while len(self._ref) >= _APM_FRAME:
            self._apm.process_reverse_stream(self._frame(self._ref[:_APM_FRAME].tobytes()))
            self._ref = self._ref[_APM_FRAME:]
        out = []
        step = _APM_FRAME * 2
        for start in range(0, len(mic) - step + 1, step):
            frame = self._frame(mic[start:start + step])
            self._apm.set_stream_delay_ms(self.delay_ms)
            self._apm.process_stream(frame)
            out.append(bytes(frame.data))
        return b"".join(out)


class SpeechDetector:
    """Silero VAD: probability that the latest audio is human speech, any language."""

    _CHUNK = 512  # Silero's window at 16 kHz

    def __init__(self):
        import torch
        from silero_vad import load_silero_vad

        self._torch = torch
        self._model = load_silero_vad(onnx=True)
        self._buffer = np.zeros(0, dtype=np.float32)
        self.probability = 0.0

    def feed(self, pcm: bytes) -> float:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._buffer = np.concatenate((self._buffer, samples))
        while len(self._buffer) >= self._CHUNK:
            chunk = self._torch.from_numpy(self._buffer[:self._CHUNK].copy())
            self.probability = float(self._model(chunk, REF_RATE))
            self._buffer = self._buffer[self._CHUNK:]
        return self.probability

    def reset(self) -> None:
        self._model.reset_states()
        self._buffer = np.zeros(0, dtype=np.float32)
        self.probability = 0.0


class BargeInMonitor:
    """Turn per-frame speech probabilities into duck / interrupt / segment.

    Short sounds (a cough, "mhm") only duck the voice and it comes back;
    sustained speech pauses it and the utterance, with its first syllables,
    is collected until the user stops talking.
    """

    def __init__(
        self,
        frame_ms: int = 30,
        duck_ms: int = 200,
        interrupt_ms: int = 500,
        release_ms: int = 400,
        end_silence_ms: int = 700,
        max_ms: int = 15000,
        threshold: float = 0.6,
    ):
        self.frame_ms = frame_ms
        self.duck_frames = max(1, duck_ms // frame_ms)
        self.interrupt_frames = max(self.duck_frames + 1, interrupt_ms // frame_ms)
        self.release_frames = max(1, release_ms // frame_ms)
        self.end_frames = max(1, end_silence_ms // frame_ms)
        self.max_frames = max_ms // frame_ms
        self.threshold = threshold
        self._preroll: Deque[bytes] = collections.deque(maxlen=self.interrupt_frames + 10)
        self.reset()

    def reset(self) -> None:
        self.state = "watching"
        self.segment = b""
        self._frames: List[bytes] = []
        self._preroll.clear()
        self._speech = self._silence = 0

    def push(self, frame: bytes, probability: float) -> Optional[str]:
        voiced = probability >= self.threshold
        if self.state == "done":
            return None
        if self.state == "capturing":
            self._frames.append(frame)
            # Hysteresis: a weak frame inside speech is not yet silence.
            self._silence = 0 if probability >= self.threshold - 0.15 else self._silence + 1
            if self._silence >= self.end_frames or len(self._frames) >= self.max_frames:
                self.state = "done"
                self.segment = b"".join(self._frames)
                return "segment"
            return None

        self._preroll.append(frame)
        if voiced:
            self._speech += 1
            self._silence = 0
        else:
            self._silence += 1
            if self._silence > 1:  # tolerate one weak frame inside a word
                self._speech = 0
        if self._speech >= self.interrupt_frames:
            self.state = "capturing"
            self._frames = list(self._preroll)
            self._silence = 0
            return "interrupt"
        if self.state == "watching" and self._speech >= self.duck_frames:
            self.state = "ducked"
            return "duck"
        if self.state == "ducked" and self._silence >= self.release_frames:
            self.state = "watching"
            return "unduck"
        return None


def looks_like_echo(transcript: str, spoken: str, overlap: float = 0.6) -> bool:
    """True when the 'interruption' is mostly Monika's own words leaking back."""
    def words(text: str) -> set:
        return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(w) > 1}

    heard = words(transcript)
    return bool(heard) and len(heard & words(spoken)) / len(heard) >= overlap
