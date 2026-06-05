import asyncio
import base64
import os
import time


class ScreenOcrRuntime:
    def __init__(
        self,
        *,
        get_audio_loop,
        ocr_image_bytes_fn,
        get_shared_activity_runtime=None,
        min_interval_sec: float = 0.8,
        debounce_delay_sec: float = 0.6,
        activity_interval_sec: float = 5.0,
    ):
        self._get_audio_loop = get_audio_loop
        self._ocr_image_bytes = ocr_image_bytes_fn
        self._get_shared_activity_runtime = get_shared_activity_runtime
        self._min_interval_sec = float(min_interval_sec)
        self._debounce_delay_sec = float(debounce_delay_sec)
        self._activity_interval_sec = float(activity_interval_sec)
        self._last_ocr_ts = 0.0
        self._last_activity_ocr_ts = 0.0
        self._debounce_task = None
        self._activity_task = None

    @staticmethod
    def _should_run_screen_ocr(text: str) -> bool:
        if not text:
            return False
        t = str(text).lower()
        if len(t) < 3:
            return False
        keywords = [
            "co pisze",
            "co jest napisane",
            "co jest na ekranie",
            "jaki napis",
            "jakie napisy",
            "przeczytaj",
            "odczytaj",
            "napis",
            "napisy",
            "tekst",
            "dialog",
            "napisy",
            "subtitle",
            "subtitles",
            "caption",
            "what does it say",
            "what's it say",
            "what is written",
            "what's written",
            "read the text",
            "read the dialog",
            "dialog says",
            "quest",
            "objective",
            "mission",
            "hint",
            "tooltip",
        ]
        return any(k in t for k in keywords)

    def _get_latest_screen_bytes(self):
        audio_loop = self._get_audio_loop()
        payload = getattr(audio_loop, "_latest_image_payload", None)
        if not payload or not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not data:
            return None
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)
        try:
            return base64.b64decode(data)
        except Exception:
            return None

    async def _send_system_notice(self, msg: str):
        audio_loop = self._get_audio_loop()
        if not audio_loop or not getattr(audio_loop, "session", None):
            return
        try:
            if hasattr(audio_loop, "send_system_message"):
                await audio_loop.send_system_message(msg, end_of_turn=False)
            else:
                await audio_loop.session.send(input=msg, end_of_turn=False)
        except Exception:
            pass

    def _shared_activity_runtime(self):
        if self._get_shared_activity_runtime is None:
            return None
        try:
            return self._get_shared_activity_runtime()
        except Exception:
            return None

    def _shared_activity_active(self) -> bool:
        runtime = self._shared_activity_runtime()
        return bool(runtime and runtime.is_active())

    def _update_shared_activity(self, text: str) -> bool:
        runtime = self._shared_activity_runtime()
        if not runtime:
            return False
        try:
            return bool(runtime.update_context(text))
        except Exception:
            return False

    async def _extract_latest_screen_text(self):
        audio_loop = self._get_audio_loop()
        if not audio_loop or not getattr(audio_loop, "session", None):
            return "", ""
        if getattr(audio_loop, "video_mode", None) != "screen":
            return "", "screen_mode_inactive"

        try:
            await audio_loop.refresh_latest_frame(min_age_sec=0.05)
        except Exception:
            pass

        raw = self._get_latest_screen_bytes()
        if not raw:
            return "", "no_screen_frame"

        lang = (os.getenv("SCREEN_OCR_LANG") or "en").strip().lower()
        engine = (os.getenv("SCREEN_OCR_ENGINE") or "local").strip().lower()
        use_gpu_env = os.getenv("SCREEN_OCR_USE_GPU", "").strip().lower()
        use_gpu = use_gpu_env in ("1", "true", "yes", "y", "on")

        try:
            text_out, err = await asyncio.to_thread(
                self._ocr_image_bytes,
                raw,
                lang=lang,
                use_gpu=use_gpu,
                engine=engine,
            )
        except Exception as e:
            return "", f"failed:{e}"

        if not text_out:
            return "", err or "no_text"

        return " ".join(str(text_out).split()), ""

    async def maybe_send(self, text: str) -> bool:
        audio_loop = self._get_audio_loop()
        if not audio_loop or not getattr(audio_loop, "session", None):
            return False
        if getattr(audio_loop, "video_mode", None) != "screen":
            return False
        if not self._should_run_screen_ocr(text):
            return False

        now = time.time()
        if (now - self._last_ocr_ts) < self._min_interval_sec:
            return False
        self._last_ocr_ts = now

        cleaned, err = await self._extract_latest_screen_text()
        if not cleaned:
            if err == "no_screen_frame":
                await self._send_system_notice("System Notification: [Screen OCR] No screen frame available for OCR.")
            elif err == "paddleocr_no_text":
                await self._send_system_notice("System Notification: [Screen OCR] No readable text found on screen.")
            elif err:
                await self._send_system_notice(f"System Notification: [Screen OCR] Unavailable: {err}")
            return False

        snippet = cleaned[:1200] + ("..." if len(cleaned) > 1200 else "")
        self._update_shared_activity(cleaned)
        await self._send_system_notice(f"System Notification: [Screen OCR] Extracted text snippet: {snippet}")
        return True

    async def capture_for_activity(self, *, notify_model: bool = True) -> bool:
        """Capture screen OCR for the active shared activity, if one exists."""
        if not self._shared_activity_active():
            return False

        now = time.time()
        if (now - self._last_activity_ocr_ts) < self._activity_interval_sec:
            return False
        self._last_activity_ocr_ts = now

        cleaned, err = await self._extract_latest_screen_text()
        if not cleaned:
            if notify_model and err == "no_screen_frame":
                await self._send_system_notice("System Notification: [Shared Activity] No screen frame available for OCR.")
            return False

        if not self._update_shared_activity(cleaned):
            return False

        if notify_model:
            snippet = cleaned[:800] + ("..." if len(cleaned) > 800 else "")
            await self._send_system_notice(
                "System Notification: [Shared Activity] Current screen context updated: "
                f"{snippet}"
            )
        return True

    def start_activity_loop(self) -> None:
        """Start the low-rate OCR loop used during shared activities."""
        if self._activity_task and not self._activity_task.done():
            return
        self._activity_task = asyncio.create_task(self._activity_loop())

    def stop_activity_loop(self) -> None:
        if self._activity_task and not self._activity_task.done():
            try:
                self._activity_task.cancel()
            except Exception:
                pass
        self._activity_task = None

    async def _activity_loop(self) -> None:
        try:
            while self._shared_activity_active():
                await self.capture_for_activity(notify_model=True)
                await asyncio.sleep(self._activity_interval_sec)
        except asyncio.CancelledError:
            return

    def activity_loop_running(self) -> bool:
        return bool(self._activity_task and not self._activity_task.done())

    def schedule_from_transcription(self):
        if self._debounce_task and not self._debounce_task.done():
            try:
                self._debounce_task.cancel()
            except Exception:
                pass
        self._debounce_task = asyncio.create_task(self._debounced())

    async def _debounced(self):
        await asyncio.sleep(self._debounce_delay_sec)
        audio_loop = self._get_audio_loop()
        if not audio_loop:
            return
        try:
            buf = getattr(audio_loop, "chat_buffer", {}) or {}
            if buf.get("sender") != "Ty":
                return
            text = buf.get("text") or ""
        except Exception:
            return
        await self.maybe_send(text)
