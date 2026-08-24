import asyncio
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.audio.server_mic_listener import (
    AdaptiveEnergyVAD,
    ServerMicListenerService,
    _raw_pcm_to_wav,
)


def _generate_pcm_frame(freq: float, duration_ms: int, sample_rate: int = 16000, amplitude: float = 10000.0) -> bytes:
    t = np.linspace(0, duration_ms / 1000.0, int(sample_rate * (duration_ms / 1000.0)), endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.int16)
    return samples.tobytes()


def test_adaptive_energy_vad_speech_detection():
    vad = AdaptiveEnergyVAD(
        sample_rate=16000,
        frame_duration_ms=30,
        energy_threshold_ratio=2.0,
        min_speech_duration_ms=60,
        trailing_silence_duration_ms=120,
        pre_roll_duration_ms=90,
    )

    silence_frame = b"\x00\x00" * vad.frame_size
    loud_frame = _generate_pcm_frame(440.0, 30, sample_rate=16000, amplitude=12000.0)

    # Initially silence
    assert vad.compute_rms(silence_frame) < 50.0
    assert vad.compute_rms(loud_frame) > 5000.0

    # Feed some background silence frames
    for _ in range(5):
        seg = vad.process_frame(silence_frame)
        assert seg is None
    assert not vad.is_speech_active

    # Feed speech frames
    for _ in range(4):
        seg = vad.process_frame(loud_frame)
        assert seg is None
    assert vad.is_speech_active

    # Feed trailing silence frames to finalize segment
    segment_output = None
    for _ in range(5):
        seg = vad.process_frame(silence_frame)
        if seg:
            segment_output = seg
            break

    assert segment_output is not None
    assert len(segment_output) > len(loud_frame) * 3
    assert not vad.is_speech_active


def test_wake_word_extraction():
    service = ServerMicListenerService(require_wake_word=True)

    matched, prompt = service.extract_wake_word("Monika, jaka jest dzisiaj pogoda?")
    assert matched
    assert prompt == "jaka jest dzisiaj pogoda?"

    matched, prompt = service.extract_wake_word("Hej Monika, zanotuj coś")
    assert matched
    assert prompt == "zanotuj coś"

    matched, prompt = service.extract_wake_word("Droga Moniko co tam słychać?")
    assert matched
    assert prompt == "co tam słychać?"

    matched, prompt = service.extract_wake_word("Rozmawiamy sobie o obiedzie.")
    assert not matched

    # Pure VAD mode (no wake word required)
    service.set_wake_word_required(False)
    matched, prompt = service.extract_wake_word("Rozmawiamy sobie o obiedzie.")
    assert matched
    assert prompt == "Rozmawiamy sobie o obiedzie."


def test_server_mic_service_mute_and_controls():
    service = ServerMicListenerService()
    assert not service.is_muted

    service.set_muted(True)
    assert service.is_muted

    service.set_muted(False)
    assert not service.is_muted


@pytest.mark.asyncio
async def test_server_mic_handle_speech_segment():
    mock_handler = AsyncMock(return_value="Jest słonecznie i 20 stopni.")
    mock_turn_cb = AsyncMock()

    service = ServerMicListenerService(
        conversation_handler=mock_handler,
        require_wake_word=False,
        on_turn_finished=mock_turn_cb,
    )

    service.transcribe_speech = AsyncMock(return_value="Jaka jest pogoda?")
    service.play_audio_locally = AsyncMock()

    fake_pcm = b"\x00\x00" * 3200
    with patch("backend.conversation.speech.GeminiSpeechSynthesizer.synthesize", new_callable=AsyncMock) as mock_synth:
        synth_res = MagicMock()
        synth_res.audio = b"\x01\x02\x03\x04"
        synth_res.sample_rate = 24000
        mock_synth.return_value = synth_res

        await service._handle_speech_segment(fake_pcm)

        mock_handler.assert_called_once_with("Jaka jest pogoda?")
        service.play_audio_locally.assert_called_once_with(b"\x01\x02\x03\x04", sample_rate=24000)
        mock_turn_cb.assert_called_once_with("Jaka jest pogoda?", "Jest słonecznie i 20 stopni.")

