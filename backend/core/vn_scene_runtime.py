from __future__ import annotations

import asyncio
import time


VN_SCENE_KEYWORDS = [
    (
        "kitchen",
        [
            "gotow",
            "kuchar",
            "kuchni",
            "kuchnia",
            "obiad",
            "kolac",
            "śniad",
            "sniad",
            "piec",
            "piecz",
            "makaron",
            "przepis",
            "herbat",
            "kawa",
            "jedz",
            "jedzenie",
        ],
    ),
    (
        "outside",
        [
            "na dworze",
            "na zewnątrz",
            "na zewnatrz",
            "spacer",
            "park",
            "natura",
            "pogod",
            "deszcz",
            "śnieg",
            "snieg",
            "wiatr",
            "słońc",
            "slonc",
            "plaż",
            "plaz",
            "las",
        ],
    ),
    ("school", ["szkoł", "szkol", "uczeln", "studia", "lekcj", "egzamin", "nauka", "klasa"]),
    ("room", ["pokój", "pokoj", "biurko", "prac", "kod", "komputer", "projekt", "pisan"]),
    ("club", ["klub", "literatur", "wiersz", "poezj", "spotkanie"]),
    ("library", ["bibliotek", "książk", "czyta", "lektur"]),
    ("bedroom", ["sypialni", "łóżk", "spac", "drzemk", "noc"]),
]


class VnSceneRuntime:
    def __init__(self, *, sio, get_audio_loop):
        self._sio = sio
        self._get_audio_loop = get_audio_loop
        self._state = {"current": None, "last_ts": 0.0}
        self._user_buf = ""
        self._user_last_ts = 0.0
        self._scene_task = None

    def get_user_buf(self):
        return self._user_buf

    def set_user_buf(self, value):
        self._user_buf = value

    def set_user_last_ts(self, value):
        self._user_last_ts = value

    def get_scene_task(self):
        return self._scene_task

    def set_scene_task(self, task):
        self._scene_task = task

    def create_debounced_task(self):
        return asyncio.create_task(self._debounced_scene_check())

    def note_user_text(self, text: str):
        self._user_buf = (self._user_buf + " " + (text or "")).strip()[-400:]
        self._user_last_ts = time.time()
        if self._scene_task is None or self._scene_task.done():
            self._scene_task = self.create_debounced_task()

    def _pick_scene_from_text(self, text: str):
        if not text:
            return None, None
        normalized = text.lower()
        for scene, keys in VN_SCENE_KEYWORDS:
            for key in keys:
                if key in normalized:
                    return scene, key
        return None, None

    async def _debounced_scene_check(self):
        await asyncio.sleep(0.8)
        if (time.time() - self._user_last_ts) < 0.7:
            self._scene_task = asyncio.create_task(self._debounced_scene_check())
            return

        text = (self._user_buf or "").strip()
        if len(text) < 6:
            return

        scene, keyword = self._pick_scene_from_text(text)
        if not scene:
            return

        now = time.time()
        if self._state["current"] == scene:
            return
        if (now - self._state["last_ts"]) < 90:
            return

        self._state["current"] = scene
        self._state["last_ts"] = now
        self._user_buf = ""

        try:
            asyncio.create_task(self._sio.emit("vn_scene", {"scene": scene, "reason": keyword, "ttl_ms": 180000}))
        except Exception:
            pass

        try:
            audio_loop = self._get_audio_loop()
            if audio_loop and getattr(audio_loop, "session", None):
                await audio_loop.session.send(
                    input=(
                        "System Notification: Scene changed to '"
                        + scene
                        + "' because user mentioned '"
                        + str(keyword)
                        + "'. Briefly acknowledge the change in a natural way (1 short sentence), then continue."
                    ),
                    end_of_turn=False,
                )
        except Exception as e:
            print(f"[SERVER] Failed to notify model about scene change: {e}")
