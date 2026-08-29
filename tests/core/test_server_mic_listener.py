import asyncio
import time
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
    assert not matched


    matched, prompt = service.extract_wake_word("Hej Monika, zanotuj coś")
    assert matched
    assert prompt == "zanotuj coś"

    matched, prompt = service.extract_wake_word("Ej Monika, włącz światło")
    assert matched
    assert prompt == "włącz światło"

    matched, prompt = service.extract_wake_word("Droga Moniko co tam słychać?")
    assert not matched

    matched, prompt = service.extract_wake_word("Okej Moniko, co tam słychać?")
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


@pytest.mark.asyncio
async def test_sounddevice_read_does_not_block_event_loop():
    class BlockingStream:
        def read(self, _chunk_size):
            time.sleep(0.08)
            return b"frame", False

    task = asyncio.create_task(
        ServerMicListenerService._read_sounddevice_frame(BlockingStream(), 480)
    )

    await asyncio.sleep(0.01)
    assert not task.done()
    assert await task == (b"frame", False)

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
        use_gemini_live=False,
    )

    service.transcribe_speech = AsyncMock(return_value="Jaka jest pogoda?")
    service.play_audio_locally = AsyncMock()

    fake_pcm = _generate_pcm_frame(440.0, 500, amplitude=2000.0)
    with patch("backend.conversation.speech.GeminiSpeechSynthesizer.synthesize", new_callable=AsyncMock) as mock_synth:
        synth_res = MagicMock()
        synth_res.audio = b"\x01\x02\x03\x04"
        synth_res.sample_rate = 24000
        mock_synth.return_value = synth_res

        await service._handle_speech_segment(fake_pcm)

        mock_handler.assert_called_once_with("Jaka jest pogoda?")
        service.play_audio_locally.assert_called_once_with(b"\x01\x02\x03\x04", sample_rate=24000)
        mock_turn_cb.assert_called_once_with("Jaka jest pogoda?", "Jest słonecznie i 20 stopni.")


@pytest.mark.asyncio
async def test_standalone_wake_word_acknowledges_then_accepts_follow_up():
    mock_handler = AsyncMock(return_value="Już włączam światło.")
    service = ServerMicListenerService(
        conversation_handler=mock_handler,
        require_wake_word=True,
        use_gemini_live=False,
    )
    service._play_wake_chime = AsyncMock()
    service._synthesize_and_play = AsyncMock()
    service.transcribe_speech = AsyncMock(side_effect=["Monika", "Włącz światło"])

    # A non-silent segment that passes the service's input sanity checks.
    fake_pcm = _generate_pcm_frame(440.0, 500, amplitude=2000.0)

    await service._handle_speech_segment(fake_pcm)

    service._play_wake_chime.assert_awaited_once_with()
    assert service.is_awaiting_command
    mock_handler.assert_not_awaited()

    await service._handle_speech_segment(fake_pcm)

    mock_handler.assert_awaited_once_with("Włącz światło")
    assert not service.is_awaiting_command


class _FakeContinuousRecognizer:
    def __init__(self, *, completed: bool, result: str, partial: str = "monikę"):
        self.completed = completed
        self.result = result
        self.partial = partial
        self.result_calls = 0
        self.partial_calls = 0

    def AcceptWaveform(self, _frame):
        return self.completed

    def Result(self):
        self.result_calls += 1
        return self.result

    def PartialResult(self):
        self.partial_calls += 1
        return f'{{"partial": "{self.partial}"}}'


def test_continuous_wake_partial_requires_stability():
    service = ServerMicListenerService(require_wake_word=True)
    service.partial_wake_stability_frames = 3
    recognizer = _FakeContinuousRecognizer(
        completed=False,
        result="{}",
        partial="hej monika",
    )
    service._continuous_wake_recognizer = recognizer
    service._start_live_session = MagicMock(return_value=True)

    assert not service._process_continuous_wake_frame(b"frame", voiced=True)
    assert not service._process_continuous_wake_frame(b"frame", voiced=True)
    assert service._process_continuous_wake_frame(b"frame", voiced=True)
    assert recognizer.result_calls == 0
    assert recognizer.partial_calls == 3
    service._start_live_session.assert_called_once_with(
        b"frameframeframe",
        "hej monika",
        provisional=True,
    )


def test_continuous_wake_unrelated_partial_does_not_preconnect():
    service = ServerMicListenerService(require_wake_word=True)
    service._continuous_wake_recognizer = _FakeContinuousRecognizer(
        completed=False,
        result="{}",
        partial="rozmawiamy o monice",
    )
    service._start_live_session = MagicMock(return_value=True)

    for _ in range(5):
        assert not service._process_continuous_wake_frame(b"frame", voiced=True)
    service._start_live_session.assert_not_called()


def test_continuous_wake_requires_direct_final_form_and_confidence():
    service = ServerMicListenerService(require_wake_word=True)

    matched, _, confidence = service._validate_continuous_wake_result({
        "text": "monikę",
        "result": [{"word": "monikę", "conf": 0.99}],
    })
    assert not matched
    assert confidence == 0.0

    matched, _, confidence = service._validate_continuous_wake_result({
        "text": "monika",
        "result": [{"word": "monika", "conf": 0.90}],
    })
    assert not matched
    assert confidence == 0.0

    matched, _, confidence = service._validate_continuous_wake_result({
        "text": "hej monika",
        "result": [
            {"word": "hej", "conf": 0.91},
            {"word": "monika", "conf": 0.93},
        ],
    })
    assert matched
    assert confidence == pytest.approx(0.91)

    matched, _, confidence = service._validate_continuous_wake_result({
        "text": "ej monika",
        "result": [
            {"word": "ej", "conf": 0.91},
            {"word": "monika", "conf": 0.93},
        ],
    })
    assert matched
    assert confidence == pytest.approx(0.91)


def test_final_confident_wake_starts_live_once():
    service = ServerMicListenerService(require_wake_word=True)
    service._continuous_wake_recognizer = _FakeContinuousRecognizer(
        completed=True,
        result='{"text": "hej monika", "result": [{"word": "hej", "conf": 0.97}, {"word": "monika", "conf": 0.98}]}',
    )
    service._start_live_session = MagicMock(return_value=True)

    assert service._process_continuous_wake_frame(b"frame", voiced=True)
    service._start_live_session.assert_called_once_with(
        b"frame", "hej monika", provisional=False
    )


@pytest.mark.asyncio
async def test_provisional_preconnect_keeps_audio_local_until_verified():
    service = ServerMicListenerService(require_wake_word=True)
    service._run_live_session = AsyncMock()
    service._play_wake_chime = AsyncMock()

    assert service._start_live_session(
        b"private audio", "hej monika", provisional=True
    )
    await asyncio.sleep(0)

    service._run_live_session.assert_awaited_once_with(b"")
    assert service._pending_initial_pcm == b"private audio"
    assert service._wake_verified_event is not None
    assert not service._wake_verified_event.is_set()


@pytest.mark.asyncio
async def test_final_verifier_opens_audio_gate():
    service = ServerMicListenerService(require_wake_word=True)
    service._continuous_wake_recognizer = _FakeContinuousRecognizer(
        completed=True,
        result='{"text": "hej monika", "result": [{"word": "hej", "conf": 0.97}, {"word": "monika", "conf": 0.98}]}',
    )
    service._wake_provisional = True
    service._wake_verified_event = asyncio.Event()
    service._live_session_task = MagicMock()
    service._live_session_task.done.return_value = False

    assert service._process_continuous_wake_frame(b"frame", voiced=True)
    assert service._wake_verified_event.is_set()
    service._live_session_task.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_stream_live_audio_writes_before_turn_end():
    service = ServerMicListenerService()
    audio_queue = asyncio.Queue()
    fake_stream = MagicMock()
    chunk = _generate_pcm_frame(440.0, 60, sample_rate=24000)

    with (
        patch("backend.audio.server_mic_listener._SOUNDDEVICE_AVAILABLE", True),
        patch("backend.audio.server_mic_listener.find_best_output_device", return_value=1),
        patch("backend.audio.server_mic_listener.sd.query_devices", return_value={"name": "fake"}),
        patch("backend.audio.server_mic_listener.sd.check_output_settings"),
        patch("backend.audio.server_mic_listener.sd.RawOutputStream", return_value=fake_stream),
    ):
        player = asyncio.create_task(service._stream_live_audio(audio_queue))
        await audio_queue.put(chunk)
        for _ in range(20):
            if fake_stream.write.called:
                break
            await asyncio.sleep(0.01)
        assert fake_stream.write.called
        await audio_queue.put(None)
        await player


def test_live_mutations_require_explicit_current_utterance():
    service = ServerMicListenerService(require_wake_word=True)
    add_args = {"action": "add", "item": "mleko"}
    light_args = {"action": "turn_on", "target": "salon"}

    assert not service._live_tool_is_explicitly_requested(
        "manage_shopping_list", add_args, "Dobra"
    )
    assert service._live_tool_is_explicitly_requested(
        "manage_shopping_list", add_args, "Dodaj mleko do listy zakupów"
    )
    assert not service._live_tool_is_explicitly_requested(
        "control_light", light_args, "Salon wygląda dobrze"
    )
    assert service._live_tool_is_explicitly_requested(
        "control_light", light_args, "Włącz światło w salonie"
    )
