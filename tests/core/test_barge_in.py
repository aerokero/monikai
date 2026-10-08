import asyncio
import collections

import numpy as np
import pytest

from backend.audio.barge_in import (
    REF_RATE,
    AudioOutput,
    BargeInMonitor,
    looks_like_echo,
)


def _pump(output: AudioOutput, frames: int) -> np.ndarray:
    buf = bytearray(frames * output.channels * 2)
    output._callback(buf, frames, None, None)
    return np.frombuffer(bytes(buf), dtype=np.int16)


@pytest.mark.asyncio
async def test_audio_output_plays_queued_clip_and_records_reference():
    output = AudioOutput(rate=48000, channels=2)
    pcm = (np.arange(2400, dtype=np.int16) % 100).tobytes()  # 100 ms at 24 kHz
    play = asyncio.create_task(output.play(pcm, 24000))
    await asyncio.sleep(0)

    first = _pump(output, 2400)  # 50 ms
    assert first.any() and not play.done()
    _pump(output, 2400)
    await asyncio.wait_for(play, 1)
    # The reference is continuous 16 kHz mono, silence included.
    _pump(output, 480)
    assert sum(len(r) for r in output.reference) == round((2400 + 2400 + 480) * REF_RATE / 48000)


@pytest.mark.asyncio
async def test_audio_output_pause_holds_position_and_stop_releases_players():
    output = AudioOutput(rate=16000, channels=1)
    play = asyncio.create_task(output.play(np.full(1600, 1000, np.int16).tobytes(), 16000))
    await asyncio.sleep(0)

    output.paused = True
    assert not _pump(output, 800).any()
    output.paused = False
    resumed = _pump(output, 800)
    assert resumed[-1] == 1000  # fades back in from silence, then full level
    assert not play.done()

    output.stop()
    await asyncio.wait_for(play, 1)


@pytest.mark.asyncio
async def test_audio_output_ducks_smoothly():
    output = AudioOutput(rate=16000, channels=1)
    asyncio.create_task(output.play(np.full(3200, 10000, np.int16).tobytes(), 16000))
    await asyncio.sleep(0)
    output.gain = 0.3
    ramp = _pump(output, 800)
    assert ramp[0] > 9000 and abs(int(ramp[-1]) - 3000) < 50
    assert abs(int(_pump(output, 800)[0]) - 3000) < 50


def test_barge_in_monitor_ducks_for_short_sounds_and_interrupts_for_speech():
    monitor = BargeInMonitor(frame_ms=30, duck_ms=90, interrupt_ms=300, release_ms=90, end_silence_ms=90)
    frame = b"\x01\x00" * 480
    events = [monitor.push(frame, 0.9) for _ in range(4)]  # a cough: 120 ms
    events += [monitor.push(frame, 0.1) for _ in range(4)]
    assert [e for e in events if e] == ["duck", "unduck"]

    events = [monitor.push(frame, 0.9) for _ in range(12)]
    events += [monitor.push(frame, 0.05) for _ in range(5)]
    assert [e for e in events if e] == ["duck", "interrupt", "segment"]
    # The segment keeps the first syllables spoken before the interrupt.
    assert len(monitor.segment) >= 12 * len(frame)


def test_echo_detection_compares_words_language_independently():
    spoken = "Jutro w Warszawie będzie słonecznie, około dwudziestu stopni."
    assert looks_like_echo("w Warszawie będzie słonecznie", spoken)
    assert not looks_like_echo("Stop, a jaka będzie pogoda w Krakowie?", spoken)
    assert not looks_like_echo("", spoken)


def test_echo_canceller_removes_own_playback_but_keeps_the_user():
    pytest.importorskip("livekit")
    from backend.audio.barge_in import EchoCanceller

    rng = np.random.default_rng(1)
    n = REF_RATE * 4
    # Speech-like far end: noise with a syllable-rate envelope.
    far = rng.normal(0, 3000, n) * (0.6 + 0.4 * np.sin(np.arange(n) * 2 * np.pi * 4 / REF_RATE))
    room = np.convolve(far, np.r_[0.5, np.zeros(150), 0.2, np.zeros(300), 0.05])[:n]
    echo = np.r_[np.zeros(800), room][:n]  # 50 ms speaker-to-mic delay
    user = np.zeros(n)
    user[3 * REF_RATE:] = np.sin(np.arange(REF_RATE) * 2 * np.pi * 220 / REF_RATE) * 2000
    mic = np.clip(echo + user, -32768, 32767).astype(np.int16)
    far = np.clip(far, -32768, 32767).astype(np.int16)

    aec = EchoCanceller(delay_ms=50)
    ref = collections.deque()
    out = []
    for i in range(0, n, 480):
        ref.append(far[i:i + 480])
        out.append(np.frombuffer(aec.process(mic[i:i + 480].tobytes(), ref), np.int16))
    out = np.concatenate(out).astype(np.float64)

    def db(x):
        return 10 * np.log10(np.mean(np.square(np.asarray(x, dtype=np.float64))) + 1e-9)

    echo_only = slice(REF_RATE, 3 * REF_RATE)  # after one second of convergence
    assert db(mic[echo_only]) - db(out[echo_only]) > 20
    talk = slice(3 * REF_RATE, n)
    assert db(out[talk]) > db(user[talk]) - 10


def test_speech_detector_rejects_silence_and_noise():
    pytest.importorskip("silero_vad")
    from backend.audio.barge_in import SpeechDetector

    detector = SpeechDetector()
    noise = (np.random.default_rng(2).normal(0, 300, REF_RATE)).astype(np.int16).tobytes()
    assert detector.feed(noise) < 0.3
