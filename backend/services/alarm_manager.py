"""Alarm clock rung on the server speakers.

Deliberately independent of the Odysseus TaskScheduler: that scheduler defers
due jobs by 15 min while the user is active and cancels running jobs on any
foreground activity, both wrong for an alarm.  This loop owns nothing but
alarms, persists to JSON and never needs a model to ring.
"""

import asyncio
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np

TZ = ZoneInfo(os.getenv("TZ") or "Europe/Warsaw")
# Ring an alarm that came due while the container was down, if not too stale.
GRACE = timedelta(minutes=int(os.getenv("ALARM_GRACE_MINUTES", "15")))
RING_MINUTES = float(os.getenv("ALARM_RING_MINUTES", "15"))
SNOOZE_MINUTES = int(os.getenv("ALARM_SNOOZE_MINUTES", "10"))
# Calibration knobs: room/speaker dependent.
START_VOLUME = float(os.getenv("ALARM_START_VOLUME", "0.3"))
VOLUME_STEP = float(os.getenv("ALARM_VOLUME_STEP", "0.1"))
BURST_SECONDS = float(os.getenv("ALARM_BURST_SECONDS", "6"))
# Silence between bursts: the microphone listens for "stop"/"drzemka" here.
LISTEN_SECONDS = float(os.getenv("ALARM_LISTEN_SECONDS", "5"))
GREETING_PREP = timedelta(minutes=5)
SOUNDS_DIR = Path(os.getenv("ALARM_SOUNDS_DIR", "/app/data/alarms"))
SAMPLE_RATE = 24000

_DAY_SETS = {
    "daily": [0, 1, 2, 3, 4, 5, 6], "codziennie": [0, 1, 2, 3, 4, 5, 6],
    "everyday": [0, 1, 2, 3, 4, 5, 6], "weekdays": [0, 1, 2, 3, 4],
    "robocze": [0, 1, 2, 3, 4], "dni robocze": [0, 1, 2, 3, 4],
    "weekend": [5, 6],
}
# Prefixes, longest first, so "piątek" hits "pią" and "pt" stays exact.
_DAY_PREFIXES = sorted({
    "mon": 0, "pon": 0, "pn": 0, "tue": 1, "wt": 1, "wed": 2, "śr": 2, "sr": 2,
    "thu": 3, "czw": 3, "fri": 4, "pią": 4, "pia": 4, "pt": 4,
    "sat": 5, "sob": 5, "sun": 6, "nie": 6, "nd": 6,
}.items(), key=lambda kv: -len(kv[0]))
_DAY_SHORT = ["pn", "wt", "śr", "czw", "pt", "sob", "nd"]

_SNOOZE_RE = re.compile(r"drzemk|jeszcze|później|pozniej|minut|chwil|snooze")
_STOP_RE = re.compile(
    r"\b(stop|wyłącz|wylacz|dość|dosc|wstaj|wstał|wstal|już|juz|dobra|dobrze|ok|okej|"
    r"dzięk|dziek|cisza|koniec|budzik)"
)
_NUMBER_WORDS = {
    "pięć": 5, "piec": 5, "dziesięć": 10, "dziesiec": 10, "kwadrans": 15,
    "piętnaście": 15, "pietnascie": 15, "dwadzieścia": 20, "dwadziescia": 20,
    "pół godziny": 30, "pol godziny": 30, "trzydzieści": 30, "trzydziesci": 30,
}


def parse_days(spec: Any) -> List[int]:
    """'pn-pt' / 'weekend' / 'mon,wed' / [0, 2] -> sorted weekday ints; '' -> one-shot."""
    if spec in (None, "", []):
        return []
    if isinstance(spec, (list, tuple)):
        return sorted({_day(str(d)) if not str(d).isdigit() else int(d) % 7 for d in spec})
    s = str(spec).strip().lower()
    if s in ("once", "jednorazowo", "raz"):
        return []
    if s in _DAY_SETS:
        return _DAY_SETS[s]
    m = re.fullmatch(r"(\w+)\s*[-–]\s*(\w+)", s)
    if m:
        a, b = _day(m.group(1)), _day(m.group(2))
        return sorted({(a + i) % 7 for i in range((b - a) % 7 + 1)})
    return sorted({_day(t) for t in re.split(r"[,\s]+", s) if t and t not in ("i", "and")})


def _day(token: str) -> int:
    token = token.strip().lower()
    for prefix, num in _DAY_PREFIXES:
        if token.startswith(prefix):
            return num
    raise ValueError(f"Nieznany dzień tygodnia: {token!r}")


def _parse_time(value: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", str(value or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError(f"Godzina musi mieć format HH:MM, dostałam {value!r}")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


@dataclass
class Alarm:
    id: str
    time: str                                   # HH:MM local
    days: List[int] = field(default_factory=list)  # empty = one-shot on `date`
    date: str = ""                              # YYYY-MM-DD for one-shot
    label: str = ""
    sound: str = ""                             # "" = generated tone, else file in SOUNDS_DIR
    greeting: bool = True
    enabled: bool = True
    last_fired: str = ""                        # also set on create/edit: no back-fire
    snooze_until: str = ""


def _at(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, dtime(h, m), TZ)


def _occurs_on(a: Alarm, d: date) -> bool:
    return d.weekday() in a.days if a.days else a.date == d.isoformat()


def due_time(a: Alarm, now: datetime) -> Optional[datetime]:
    """Latest not-yet-rung ring time <= now that is still within GRACE."""
    if not a.enabled:
        return None
    cands = [_at(d, a.time) for d in (now.date(), now.date() - timedelta(days=1)) if _occurs_on(a, d)]
    if a.snooze_until:
        cands.append(datetime.fromisoformat(a.snooze_until))
    last = datetime.fromisoformat(a.last_fired) if a.last_fired else None
    cands = [c for c in cands if c <= now and now - c <= GRACE and (last is None or c > last)]
    return max(cands, default=None)


def next_time(a: Alarm, now: datetime, *, include_snooze: bool = True) -> Optional[datetime]:
    if not a.enabled:
        return None
    cands = []
    if include_snooze and a.snooze_until and datetime.fromisoformat(a.snooze_until) > now:
        cands.append(datetime.fromisoformat(a.snooze_until))
    for i in range(8):
        d = now.date() + timedelta(days=i)
        if _occurs_on(a, d) and _at(d, a.time) > now:
            cands.append(_at(d, a.time))
            break
    return min(cands, default=None)


def snooze_minutes(text: str) -> int:
    m = re.search(r"\d+", text)
    if m:
        return max(1, min(60, int(m.group())))
    for word, n in _NUMBER_WORDS.items():
        if word in text:
            return n
    return SNOOZE_MINUTES


def days_label(days: List[int]) -> str:
    if not days:
        return "jednorazowo"
    if days == [0, 1, 2, 3, 4, 5, 6]:
        return "codziennie"
    if days == [0, 1, 2, 3, 4]:
        return "pn–pt"
    if days == [5, 6]:
        return "weekend"
    return ", ".join(_DAY_SHORT[d] for d in days)


def tone_pcm() -> bytes:
    """Generated alarm: two groups of four 880 Hz beeps (~2.4 s, pcm16 mono 24 kHz)."""
    beep_n, gap_n = int(0.12 * SAMPLE_RATE), int(0.08 * SAMPLE_RATE)
    t = np.arange(beep_n) / SAMPLE_RATE
    env = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.01)  # 10 ms ramps: no clicks
    beep = np.sin(2 * np.pi * 880 * t) * env
    group = np.concatenate([np.concatenate([beep, np.zeros(gap_n)]) for _ in range(4)])
    pattern = np.concatenate([group, np.zeros(int(0.5 * SAMPLE_RATE)), group, np.zeros(int(0.3 * SAMPLE_RATE))])
    return (pattern * 0.9 * 32767).astype(np.int16).tobytes()


def _scale(pcm: bytes, level: float) -> bytes:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * max(0.0, min(1.0, level))
    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()


class AlarmManager:
    """player: duck-typed ServerMicListenerService (play_audio_locally, render_speech).
    notify(event, alarm, **info): telegram/frontend fan-out, sync or async.
    compose_greeting(alarm) -> str: optional LLM wake-up text, prepared ahead of time.
    """

    def __init__(
        self,
        storage_dir: Path,
        *,
        player: Any = None,
        notify: Optional[Callable[..., Any]] = None,
        compose_greeting: Optional[Callable[[Alarm], Any]] = None,
    ):
        self.path = Path(storage_dir) / "alarms.json"
        self.player = player
        self.notify = notify
        self.compose_greeting = compose_greeting
        self.alarms: Dict[str, Alarm] = {}
        self.ringing: Optional[Alarm] = None
        self._stop = asyncio.Event()
        self._snooze: Optional[int] = None
        self._sounds: Dict[str, bytes] = {}
        self._greeting: Optional[tuple] = None  # (alarm_id, text, pcm, sr)
        self._prep_key = ""
        self._tasks: set = set()
        self._loop_task: Optional[asyncio.Task] = None
        self._load()

    # ── persistence ─────────────────────────────────────────────────────
    def _load(self):
        if not self.path.exists():
            return
        try:
            for item in json.loads(self.path.read_text(encoding="utf-8")):
                a = Alarm(**item)
                self.alarms[a.id] = a
        except Exception as exc:
            print(f"[ALARMS] Failed to load {self.path}: {exc}")

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps([asdict(a) for a in self.alarms.values()], ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception as exc:
            print(f"[ALARMS] Failed to save {self.path}: {exc}")

    # ── CRUD ────────────────────────────────────────────────────────────
    def set(
        self,
        time: str,
        days: Any = None,
        date_str: str = "",
        label: str = "",
        sound: str = "",
        greeting: bool = True,
        alarm_id: str = "",
    ) -> Alarm:
        hhmm = _parse_time(time)
        day_list = parse_days(days)
        now = datetime.now(TZ)
        one_shot = ""
        if not day_list:
            if date_str:
                one_shot = date.fromisoformat(str(date_str).strip()).isoformat()
            else:
                today = now.date()
                one_shot = (today if _at(today, hhmm) > now else today + timedelta(days=1)).isoformat()
        sound = str(sound or "").strip()
        sound = "" if sound.lower() in ("", "tone", "default", "domyślny") else Path(sound).name
        a = self.alarms.get(alarm_id) or Alarm(id=uuid.uuid4().hex[:8], time=hhmm)
        a.time, a.days, a.date = hhmm, day_list, one_shot
        a.label, a.sound, a.greeting = str(label or "").strip(), sound, bool(greeting)
        a.enabled, a.snooze_until, a.last_fired = True, "", now.isoformat()
        self.alarms[a.id] = a
        self._save()
        return a

    def delete(self, alarm_id: str) -> bool:
        existed = self.alarms.pop(alarm_id, None) is not None
        if existed:
            self._save()
        return existed

    def set_enabled(self, alarm_id: str, enabled: bool) -> Optional[Alarm]:
        a = self.alarms.get(alarm_id)
        if not a:
            return None
        if enabled and not a.days:
            return self.set(a.time, [], "", a.label, a.sound, a.greeting, a.id)
        a.enabled, a.snooze_until = bool(enabled), ""
        a.last_fired = datetime.now(TZ).isoformat()
        self._save()
        return a

    def list(self) -> List[Alarm]:
        now = datetime.now(TZ)
        far = now + timedelta(days=400)
        return sorted(self.alarms.values(), key=lambda a: (not a.enabled, next_time(a, now) or far))

    def describe(self, a: Alarm) -> str:
        nxt = next_time(a, datetime.now(TZ))
        parts = [a.time, days_label(a.days)]
        if a.label:
            parts.append(f"„{a.label}”")
        if a.sound:
            parts.append(f"dźwięk: {a.sound}")
        state = f"następny: {_DAY_SHORT[nxt.weekday()]} {nxt.strftime('%d.%m %H:%M')}" if nxt else "wyłączony"
        return f"[{a.id}] " + " · ".join(parts) + f" ({state})"

    # ── ringing control ─────────────────────────────────────────────────
    def stop(self) -> bool:
        if not self.ringing:
            return False
        self._stop.set()
        return True

    def snooze(self, minutes: Optional[int] = None) -> bool:
        if not self.ringing:
            return False
        self._snooze = int(minutes or SNOOZE_MINUTES)
        self._stop.set()
        return True

    async def handle_voice(self, text: str) -> bool:
        """Local (Vosk) transcript heard between bursts; no wake word needed."""
        if not self.ringing:
            return False
        t = str(text or "").lower()
        if _SNOOZE_RE.search(t):
            return self.snooze(snooze_minutes(t))
        if _STOP_RE.search(t):
            return self.stop()
        return False

    # ── loop ────────────────────────────────────────────────────────────
    def start(self):
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._run(), name="alarm-manager")

    async def shutdown(self):
        for t in [self._loop_task, *self._tasks]:
            if t and not t.done():
                t.cancel()
        self._loop_task = None

    def _spawn(self, coro):
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self):
        while True:
            try:
                now = datetime.now(TZ)
                if not self.ringing:
                    for a in list(self.alarms.values()):
                        due = due_time(a, now)
                        if due:
                            self.ringing = a  # claim before the next tick
                            self._spawn(self._ring(a, due))
                            break
                if self.compose_greeting and self.player is not None:
                    for a in self.alarms.values():
                        nxt = next_time(a, now, include_snooze=False) if a.greeting else None
                        key = f"{a.id}@{nxt.isoformat()}" if nxt else ""
                        if nxt and nxt - now <= GREETING_PREP and key != self._prep_key:
                            self._prep_key = key
                            self._spawn(self._prepare_greeting(a))
            except Exception as exc:
                print(f"[ALARMS] Loop error: {exc}")
            await asyncio.sleep(1.0)

    async def _emit(self, event: str, a: Alarm, **info):
        if not self.notify:
            return
        try:
            maybe = self.notify(event, a, **info)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as exc:
            print(f"[ALARMS] notify({event}) failed: {exc}")

    def forget_sound(self, name: str):
        self._sounds.pop(name, None)

    async def _sound(self, name: str) -> bytes:
        if name in self._sounds:
            return self._sounds[name]
        pcm = b""
        if name:
            path = SOUNDS_DIR / Path(name).name  # never outside SOUNDS_DIR
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                pcm, err = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode != 0:
                    raise RuntimeError(err.decode(errors="replace").strip() or f"ffmpeg exit {proc.returncode}")
            except Exception as exc:
                print(f"[ALARMS] Sound {path} unusable ({exc}); using generated tone.")
                pcm = b""
        pcm = pcm or tone_pcm()
        self._sounds[name] = pcm
        return pcm

    async def _ring(self, a: Alarm, fired_at: datetime):
        a.last_fired, a.snooze_until = fired_at.isoformat(), ""
        self._save()
        self._stop.clear()
        self._snooze = None
        print(f"[ALARMS] Ringing {self.describe(a)}")
        await self._emit("ringing", a)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + RING_MINUTES * 60
        try:
            pcm = await self._sound(a.sound)
            burst = int(BURST_SECONDS * SAMPLE_RATE) * 2
            pos, level = 0, START_VOLUME
            while not self._stop.is_set() and loop.time() < deadline:
                if self.player is not None:
                    chunk = pcm[pos:pos + burst] if len(pcm) > burst else pcm
                    pos = (pos + burst) % len(pcm) if len(pcm) > burst else 0
                    await self.player.play_audio_locally(_scale(chunk, level), sample_rate=SAMPLE_RATE)
                    level = min(1.0, level + VOLUME_STEP)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=LISTEN_SECONDS)
                except asyncio.TimeoutError:
                    pass
        except Exception as exc:
            # Speakers failed: Telegram already got "ringing"; keep waiting there.
            print(f"[ALARMS] Playback failed: {exc}")
            await self._emit("error", a, error=str(exc))
            remaining = deadline - loop.time()
            if remaining > 0:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.ringing = None

        if self._snooze:
            a.snooze_until = (datetime.now(TZ) + timedelta(minutes=self._snooze)).isoformat(timespec="seconds")
            self._save()
            await self._emit("snoozed", a, minutes=self._snooze)
            await self._say(f"Dobrze, obudzę cię za {self._snooze} minut.")
            return
        if not a.days:
            a.enabled = False
        self._save()
        if not self._stop.is_set():
            await self._emit("timeout", a)
            return
        await self._emit("stopped", a)
        if a.greeting:
            await self._greet(a)

    def _static_greeting(self, a: Alarm) -> str:
        label = f" {a.label}." if a.label else ""
        return f"Dzień dobry! Jest {datetime.now(TZ).strftime('%H:%M')}.{label} Czas wstawać."

    async def _prepare_greeting(self, a: Alarm):
        try:
            text = str(await asyncio.wait_for(self.compose_greeting(a), timeout=180) or "").strip()
            if not text:
                return
            pcm, sr = await self.player.render_speech(text)
            self._greeting = (a.id, text, pcm, sr)
            print(f"[ALARMS] Greeting ready for {a.id} ({len(text)} chars).")
        except Exception as exc:
            print(f"[ALARMS] Greeting preparation failed, will use the static one: {exc}")

    async def _greet(self, a: Alarm):
        prepared, self._greeting = self._greeting, None
        if prepared and prepared[0] == a.id:
            _, text, pcm, sr = prepared
            try:
                await self.player.play_audio_locally(pcm, sample_rate=sr)
                await self._emit("greeting", a, text=text)
                return
            except Exception as exc:
                print(f"[ALARMS] Prepared greeting playback failed: {exc}")
        text = self._static_greeting(a)
        await self._say(text)
        await self._emit("greeting", a, text=text)

    async def _say(self, text: str):
        if self.player is None:
            return
        try:
            await self.player.announce(text)
        except Exception as exc:
            print(f"[ALARMS] Speech failed: {exc}")
