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
        min_interval_sec: float = 0.8,
        debounce_delay_sec: float = 0.6,
    ):
        self._get_audio_loop = get_audio_loop
        self._ocr_image_bytes = ocr_image_bytes_fn
        self._min_interval_sec = float(min_interval_sec)
        self._debounce_delay_sec = float(debounce_delay_sec)
        self._last_ocr_ts = 0.0
        self._debounce_task = None

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

        try:
            await audio_loop.refresh_latest_frame(min_age_sec=0.05)
        except Exception:
            pass

        raw = self._get_latest_screen_bytes()
        if not raw:
            await self._send_system_notice("System Notification: [Screen OCR] No screen frame available for OCR.")
            return False

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
            await self._send_system_notice(f"System Notification: [Screen OCR] Failed: {e}")
            return False

        if not text_out:
            if err:
                if err == "paddleocr_no_text":
                    await self._send_system_notice("System Notification: [Screen OCR] No readable text found on screen.")
                else:
                    await self._send_system_notice(f"System Notification: [Screen OCR] Unavailable: {err}")
            return False

        cleaned = " ".join(str(text_out).split())
        snippet = cleaned[:1200] + ("..." if len(cleaned) > 1200 else "")
        await self._send_system_notice(f"System Notification: [Screen OCR] Extracted text snippet: {snippet}")
        return True

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
