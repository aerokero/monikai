"""Tests for the proactivity engine (v3 Phase B)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from backend.soul import proactivity
from backend.soul.time_engine.engine import GapInfo


def _fake_client(text="Hej, myślałam o Tobie. Jak tam projekt?"):
    fake = AsyncMock()
    fake.health = AsyncMock(return_value={"ok": True, "models": [], "model_available": True})
    fake.generation_speed = AsyncMock(return_value=40.0)
    fake.chat = AsyncMock(return_value=text)
    return fake


def _daytime(hour=15):
    return datetime(2026, 7, 14, hour, 0, tzinfo=timezone.utc).astimezone()


async def test_poke_sent_after_gap(tmp_db, monkeypatch):
    monkeypatch.setattr(proactivity, "_now_local", lambda: _daytime())
    sent = []

    async def send(text):
        sent.append(text)
        return True

    with patch(
        "backend.soul.time_engine.engine.TimeEngine.check_gap",
        AsyncMock(return_value=GapInfo(10.0, "short", 0.0)),
    ), patch("backend.llm.ollama_client.get_client", return_value=_fake_client()), patch(
        "backend.soul.proactivity._read_soul_file", return_value=""
    ):
        ok = await proactivity.maybe_poke(db_path=tmp_db, send_fn=send)

    assert ok is True
    assert sent and "myślałam" in sent[0]

    state = await proactivity._get_state(tmp_db)
    assert state["count"] == 1


async def test_no_poke_in_quiet_hours(tmp_db, monkeypatch):
    monkeypatch.setattr(proactivity, "_now_local", lambda: _daytime(hour=1))
    send = AsyncMock(return_value=True)
    ok = await proactivity.maybe_poke(db_path=tmp_db, send_fn=send)
    assert ok is False
    send.assert_not_awaited()


async def test_no_poke_when_gap_small(tmp_db, monkeypatch):
    monkeypatch.setattr(proactivity, "_now_local", lambda: _daytime())
    send = AsyncMock(return_value=True)
    with patch(
        "backend.soul.time_engine.engine.TimeEngine.check_gap",
        AsyncMock(return_value=GapInfo(1.5, "fresh", 0.0)),
    ):
        ok = await proactivity.maybe_poke(db_path=tmp_db, send_fn=send)
    assert ok is False
    send.assert_not_awaited()


async def test_daily_rate_limit(tmp_db, monkeypatch):
    monkeypatch.setattr(proactivity, "_now_local", lambda: _daytime())
    await proactivity._set_state(
        {
            "date": _daytime().date().isoformat(),
            "count": 2,
            "last_sent_at": (datetime.now(tz=timezone.utc) - timedelta(hours=6)).isoformat(),
        },
        tmp_db,
    )
    send = AsyncMock(return_value=True)
    with patch(
        "backend.soul.time_engine.engine.TimeEngine.check_gap",
        AsyncMock(return_value=GapInfo(12.0, "medium", 0.5)),
    ):
        ok = await proactivity.maybe_poke(db_path=tmp_db, send_fn=send)
    assert ok is False
    send.assert_not_awaited()


async def test_no_poke_when_gpu_busy(tmp_db, monkeypatch):
    monkeypatch.setattr(proactivity, "_now_local", lambda: _daytime())
    client = _fake_client()
    client.generation_speed = AsyncMock(return_value=2.0)
    send = AsyncMock(return_value=True)
    with patch(
        "backend.soul.time_engine.engine.TimeEngine.check_gap",
        AsyncMock(return_value=GapInfo(12.0, "medium", 0.5)),
    ), patch("backend.llm.ollama_client.get_client", return_value=client):
        ok = await proactivity.maybe_poke(db_path=tmp_db, send_fn=send)
    assert ok is False
    send.assert_not_awaited()
