import asyncio
from datetime import datetime, timedelta

import numpy as np
import pytest

from backend.services import alarm_manager as am
from backend.services.alarm_manager import Alarm, AlarmManager, due_time, next_time, parse_days, snooze_minutes

TZ = am.TZ


def at(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def test_parse_days():
    assert parse_days("pn-pt") == [0, 1, 2, 3, 4]
    assert parse_days("weekend") == [5, 6]
    assert parse_days("pt-pn") == [0, 4, 5, 6]  # wraps over the weekend
    assert parse_days("poniedziałek, środa, piątek") == [0, 2, 4]
    assert parse_days("mon,sun") == [0, 6]
    assert parse_days("") == [] and parse_days(None) == []
    with pytest.raises(ValueError):
        parse_days("Praca")


def test_due_and_next():
    # 2026-11-03 is a Tuesday.
    a = Alarm(id="a", time="06:30", days=[0, 1, 2, 3, 4], last_fired=at(2026, 11, 2, 22, 0).isoformat())
    assert due_time(a, at(2026, 11, 3, 6, 29)) is None
    assert due_time(a, at(2026, 11, 3, 6, 31)) == at(2026, 11, 3, 6, 30)
    assert due_time(a, at(2026, 11, 3, 7, 0)) is None  # outside the grace window
    a.last_fired = at(2026, 11, 3, 6, 30).isoformat()
    assert due_time(a, at(2026, 11, 3, 6, 31)) is None  # already rung
    assert next_time(a, at(2026, 11, 6, 7, 0)) == at(2026, 11, 9, 6, 30)  # Fri -> Mon

    # Snooze rings again even though the scheduled time already fired.
    a.snooze_until = at(2026, 11, 3, 6, 40).isoformat()
    assert due_time(a, at(2026, 11, 3, 6, 40)) == at(2026, 11, 3, 6, 40)

    # Created after today's time: no back-fire.
    b = Alarm(id="b", time="06:30", days=[1], last_fired=at(2026, 11, 3, 6, 35).isoformat())
    assert due_time(b, at(2026, 11, 3, 6, 36)) is None

    one = Alarm(id="c", time="07:00", date="2026-11-04")
    assert next_time(one, at(2026, 11, 3, 12, 0)) == at(2026, 11, 4, 7, 0)
    one.enabled = False
    assert due_time(one, at(2026, 11, 4, 7, 1)) is None


def test_voice_minutes():
    assert snooze_minutes("jeszcze 5 minut") == 5
    assert snooze_minutes("drzemka kwadrans") == 15
    assert snooze_minutes("drzemka") == am.SNOOZE_MINUTES


class FakePlayer:
    def __init__(self):
        self.played, self.said = 0, []

    async def play_audio_locally(self, pcm, sample_rate=24000):
        self.played += 1

    async def announce(self, text):
        self.said.append(text)


async def test_ring_snooze_then_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "LISTEN_SECONDS", 0.05)
    events = []
    player = FakePlayer()
    mgr = AlarmManager(tmp_path, player=player, notify=lambda e, a, **i: events.append(e))
    a = mgr.set("06:30", days="")
    mgr.ringing = a

    task = asyncio.create_task(mgr._ring(a, datetime.now(TZ)))
    await asyncio.sleep(0.12)
    assert await mgr.handle_voice("jeszcze dziesięć minut")
    await task
    assert a.enabled and a.snooze_until and events[-1] == "snoozed"
    assert player.played >= 1 and "10 minut" in player.said[-1]

    mgr.ringing = a
    task = asyncio.create_task(mgr._ring(a, datetime.now(TZ)))
    await asyncio.sleep(0.05)
    assert not await mgr.handle_voice("monika co tam")  # unrelated speech ignored
    assert await mgr.handle_voice("już wstaję")
    await task
    assert not a.enabled  # one-shot disables after the final stop
    assert events[-2:] == ["stopped", "greeting"] and player.said[-1].startswith("Dzień dobry")

    # Persisted and reloadable.
    assert AlarmManager(tmp_path).alarms[a.id].time == "06:30"


async def test_muted_mic_still_stops_ringing_alarm_locally():
    from unittest.mock import AsyncMock, MagicMock
    from backend.audio.server_mic_listener import ServerMicListenerService

    svc = ServerMicListenerService(require_wake_word=True)
    svc.set_muted(True)
    svc.alarm = MagicMock(ringing=True, handle_voice=AsyncMock(return_value=True))
    svc.transcribe_wake_word_locally = AsyncMock(return_value="stop")
    svc.transcribe_speech = AsyncMock(return_value="stop")
    speech = (np.sin(np.arange(16000) / 5) * 8000).astype(np.int16).tobytes()

    await svc._handle_speech_segment(speech)
    svc.alarm.handle_voice.assert_awaited_once_with("stop")
    svc.transcribe_speech.assert_not_awaited()  # never cloud STT

    svc.alarm.ringing = False  # alarm over: mute applies again
    svc.transcribe_wake_word_locally.reset_mock()
    await svc._handle_speech_segment(speech)
    svc.transcribe_wake_word_locally.assert_not_awaited()
    svc.transcribe_speech.assert_not_awaited()
