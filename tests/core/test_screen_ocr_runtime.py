from __future__ import annotations

from backend.core.runtimes.screen_ocr_runtime import ScreenOcrRuntime
from backend.vn.activity_runtime import SharedActivityRuntime


class _FakeSession:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, *, input: str, end_of_turn: bool = False) -> None:
        self.sent.append(input)


class _FakeAudioLoop:
    def __init__(self, raw: bytes = b"image") -> None:
        self.session = _FakeSession()
        self.video_mode = "screen"
        self._latest_image_payload = {"data": raw}
        self.refreshed = 0

    async def refresh_latest_frame(self, *, min_age_sec: float = 0.05) -> None:
        self.refreshed += 1


def _ocr_result(text: str):
    def _ocr(raw, *, lang: str, use_gpu: bool, engine: str):
        return text, None

    return _ocr


async def test_capture_for_activity_updates_active_context(tmp_db):
    audio_loop = _FakeAudioLoop()
    activity = SharedActivityRuntime(db_path=tmp_db)
    await activity.start("film", title="Test Film")

    runtime = ScreenOcrRuntime(
        get_audio_loop=lambda: audio_loop,
        ocr_image_bytes_fn=_ocr_result("Line one\nLine two"),
        get_shared_activity_runtime=lambda: activity,
        activity_interval_sec=0,
    )

    changed = await runtime.capture_for_activity(notify_model=False)

    assert changed is True
    assert "Line one Line two" in activity.monika_context()
    assert audio_loop.refreshed == 1


async def test_capture_for_activity_sends_context_notice(tmp_db):
    audio_loop = _FakeAudioLoop()
    activity = SharedActivityRuntime(db_path=tmp_db)
    await activity.start("game", title="Hollow Knight")

    runtime = ScreenOcrRuntime(
        get_audio_loop=lambda: audio_loop,
        ocr_image_bytes_fn=_ocr_result("Quest objective: find the key"),
        get_shared_activity_runtime=lambda: activity,
        activity_interval_sec=0,
    )

    assert await runtime.capture_for_activity(notify_model=True)
    assert any("[Shared Activity]" in msg for msg in audio_loop.session.sent)


async def test_manual_ocr_updates_shared_activity_context(tmp_db):
    audio_loop = _FakeAudioLoop()
    activity = SharedActivityRuntime(db_path=tmp_db)
    await activity.start("film", title="Test Film")

    runtime = ScreenOcrRuntime(
        get_audio_loop=lambda: audio_loop,
        ocr_image_bytes_fn=_ocr_result("Subtitle text"),
        get_shared_activity_runtime=lambda: activity,
        min_interval_sec=0,
    )

    assert await runtime.maybe_send("read the subtitles")
    assert "Subtitle text" in activity.monika_context()
    assert any("[Screen OCR]" in msg for msg in audio_loop.session.sent)


async def test_capture_for_activity_noops_without_active_activity(tmp_db):
    audio_loop = _FakeAudioLoop()
    activity = SharedActivityRuntime(db_path=tmp_db)

    runtime = ScreenOcrRuntime(
        get_audio_loop=lambda: audio_loop,
        ocr_image_bytes_fn=_ocr_result("Unused text"),
        get_shared_activity_runtime=lambda: activity,
        activity_interval_sec=0,
    )

    assert await runtime.capture_for_activity(notify_model=True) is False
    assert audio_loop.refreshed == 0
