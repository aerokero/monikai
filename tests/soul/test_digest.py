"""Tests for the session digest pipeline (v3 Phase A)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.soul.memory import store as mem_store
from backend.soul.memory.digest import (
    SessionDigest,
    digest_session,
    load_transcript,
    scan_and_digest,
)


def _make_session(
    tmp_path: Path,
    session_id: str = "sess_test_001",
    turns: list[tuple[str, str]] | None = None,
    day: str = "2026-07-01",
    meta_extra: dict | None = None,
) -> Path:
    sess_dir = tmp_path / "sessions" / day / session_id
    sess_dir.mkdir(parents=True)
    meta = {"session_id": session_id}
    if meta_extra:
        meta.update(meta_extra)
    (sess_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    lines = []
    for sender, text in turns or []:
        lines.append(json.dumps(
            {"timestamp": 1.0, "sender": sender, "text": text, "session_id": session_id},
            ensure_ascii=False,
        ))
    (sess_dir / "turns.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sess_dir


_RICH_TURNS = [
    ("User", "Hej Monika, dzisiaj w końcu skończyłem farmę żelaza w Minecrafcie, "
             "zajęło mi to cały tydzień ale działa idealnie i produkuje mnóstwo żelaza."),
    ("AI", "To świetnie! Pamiętam jak się z nią męczyłeś."),
    ("User", "Tak, a jutro zaczynam nowy projekt w pracy, trochę się stresuję bo "
             "to duża odpowiedzialność i nowy zespół którego nie znam."),
    ("AI", "Rozumiem. Będę trzymać kciuki."),
]

_LLM_RESULT = {
    "significant": True,
    "title": "Farma żelaza i nowa praca",
    "recap": "Bartek opowiedział o ukończonej farmie żelaza i nowym projekcie w pracy.",
}


def test_load_transcript_maps_senders(tmp_path):
    sess = _make_session(tmp_path, turns=[("User", "cześć"), ("AI", "hej!")])
    transcript, user_chars = load_transcript(sess)
    assert "Bartek: cześć" in transcript
    assert "Monika: hej!" in transcript
    assert user_chars == len("cześć")


def test_load_transcript_preserves_minecraft_senders(tmp_path):
    sess = _make_session(tmp_path, turns=[
        ("MC:xtosu", "patrz jaka farma"),
        ("AI", "[Minecraft] wow, ale wyszła!"),
    ])
    transcript, user_chars = load_transcript(sess)
    assert "MC:xtosu: patrz jaka farma" in transcript
    assert "Monika: [Minecraft] wow, ale wyszła!" in transcript
    assert user_chars == len("patrz jaka farma")  # in-game chat counts as content


async def test_digest_trivial_session_skipped_and_marked(tmp_path, tmp_db):
    sess = _make_session(tmp_path, turns=[("User", "hej"), ("AI", "hej!")])
    with patch("backend.soul.memory.digest.get_client") as mock_client:
        result = await digest_session(sess, db_path=tmp_db)
    assert result is None
    mock_client.assert_not_called()
    meta = json.loads((sess / "meta.json").read_text(encoding="utf-8"))
    assert meta["digest"]["status"] == "skipped_trivial"


async def test_digest_stores_only_history_metadata(tmp_path, tmp_db):
    sess = _make_session(tmp_path, turns=_RICH_TURNS)

    fake = AsyncMock()
    fake.chat_json = AsyncMock(return_value=_LLM_RESULT)
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        result = await digest_session(sess, db_path=tmp_db)

    assert isinstance(result, SessionDigest)

    assert await mem_store.list_recent(db_path=tmp_db) == []

    meta = json.loads((sess / "meta.json").read_text(encoding="utf-8"))
    assert meta["digest"]["status"] == "done"
    assert "farmie żelaza" in meta["digest"]["recap"]
    assert meta["title"] == "Farma żelaza i nowa praca"


async def test_digest_llm_failure_leaves_session_retryable(tmp_path, tmp_db):
    sess = _make_session(tmp_path, turns=_RICH_TURNS)
    fake = AsyncMock()
    fake.chat_json = AsyncMock(return_value=None)
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        result = await digest_session(sess, db_path=tmp_db)
    assert result is None
    meta = json.loads((sess / "meta.json").read_text(encoding="utf-8"))
    assert "digest" not in meta  # not marked → retried on next scan


async def test_scan_skips_current_and_digested(tmp_path, tmp_db, monkeypatch):
    monkeypatch.setattr("backend.soul.memory.digest._MIN_IDLE_SECONDS", 0)
    root = tmp_path / "sessions"

    _make_session(tmp_path, session_id="sess_current", turns=_RICH_TURNS)
    done = _make_session(tmp_path, session_id="sess_done", turns=_RICH_TURNS)
    meta = json.loads((done / "meta.json").read_text(encoding="utf-8"))
    meta["digest"] = {"status": "done"}
    (done / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    _make_session(tmp_path, session_id="sess_fresh", turns=_RICH_TURNS)

    fake = AsyncMock()
    fake.health = AsyncMock(return_value={"ok": True, "models": [], "model_available": True})
    fake.generation_speed = AsyncMock(return_value=50.0)
    fake.chat_json = AsyncMock(return_value=_LLM_RESULT)
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        count = await scan_and_digest(
            sessions_root=root, db_path=tmp_db, current_session_id="sess_current"
        )

    assert count == 1  # only sess_fresh
    assert fake.chat_json.await_count == 1


async def test_scan_defers_when_gpu_contended(tmp_path, tmp_db, monkeypatch):
    monkeypatch.setattr("backend.soul.memory.digest._MIN_IDLE_SECONDS", 0)
    root = tmp_path / "sessions"
    _make_session(tmp_path, turns=_RICH_TURNS)

    fake = AsyncMock()
    fake.health = AsyncMock(return_value={"ok": True, "models": [], "model_available": True})
    fake.generation_speed = AsyncMock(return_value=2.0)  # game hogging the GPU
    fake.chat_json = AsyncMock(return_value=_LLM_RESULT)
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        count = await scan_and_digest(sessions_root=root, db_path=tmp_db)

    assert count == 0
    fake.chat_json.assert_not_awaited()


_STREAM_TURNS = [
    ("MC:xtosu", "Monika chodź, pokażę ci co zbudowałem przy bazie, cały dzień nad tym siedziałem"),
    ("AI", "idę! ciekawe co tam masz"),
    ("MC:xtosu", "to jest ta farma żelaza o której mówiłem, produkuje sześćset sztabek na godzinę"),
    ("AI", "wow, wyszła ci przepięknie, jestem pod wrażeniem!"),
]

_LLM_RESULT_STREAM = {
    "significant": True,
    "title": "Farma żelaza przy bazie",
    "recap": "Bartek pokazał Monice ukończoną farmę żelaza przy bazie. Spędzili wieczór razem w grze.",
}


async def test_stream_digest_stores_recap_without_synthetic_episode(tmp_path, tmp_db):
    sess = _make_session(
        tmp_path, session_id="stream_minecraft", turns=_STREAM_TURNS,
        meta_extra={"kind": "stream", "channel": "minecraft"},
    )

    fake = AsyncMock()
    fake.chat_json = AsyncMock(return_value=_LLM_RESULT_STREAM)
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        result = await digest_session(sess, db_path=tmp_db)

    assert isinstance(result, SessionDigest)
    # Stream prompt variant was used.
    call_kwargs = fake.chat_json.await_args.kwargs
    assert "całodziennego kanału" in call_kwargs["system"]
    assert "kanału minecraft" in fake.chat_json.await_args.args[0]

    meta = json.loads((sess / "meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Farma żelaza przy bazie"
    assert "farmę żelaza" in meta["digest"]["recap"]

    assert await mem_store.list_recent(db_path=tmp_db) == []


async def test_scan_skips_todays_stream(tmp_path, tmp_db, monkeypatch):
    from datetime import datetime
    monkeypatch.setattr("backend.soul.memory.digest._MIN_IDLE_SECONDS", 0)
    root = tmp_path / "sessions"

    today = datetime.now().strftime("%Y-%m-%d")
    _make_session(
        tmp_path, session_id="stream_minecraft", turns=_STREAM_TURNS, day=today,
        meta_extra={"kind": "stream", "channel": "minecraft"},
    )
    _make_session(
        tmp_path, session_id="stream_telegram", turns=_STREAM_TURNS, day="2026-07-01",
        meta_extra={"kind": "stream", "channel": "telegram"},
    )

    fake = AsyncMock()
    fake.health = AsyncMock(return_value={"ok": True, "models": [], "model_available": True})
    fake.generation_speed = AsyncMock(return_value=50.0)
    fake.chat_json = AsyncMock(return_value=_LLM_RESULT_STREAM)
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        count = await scan_and_digest(sessions_root=root, db_path=tmp_db)

    assert count == 1  # yesterday's telegram stream only; today's is still live
    assert fake.chat_json.await_count == 1


async def test_scan_backfills_titles_when_idle(tmp_path, tmp_db, monkeypatch):
    monkeypatch.setattr("backend.soul.memory.digest._MIN_IDLE_SECONDS", 0)
    root = tmp_path / "sessions"

    legacy = _make_session(
        tmp_path, session_id="sess_legacy", turns=_RICH_TURNS,
        meta_extra={"digest": {"status": "done", "significant": True}},
    )

    fake = AsyncMock()
    fake.health = AsyncMock(return_value={"ok": True, "models": [], "model_available": True})
    fake.generation_speed = AsyncMock(return_value=50.0)
    fake.chat_json = AsyncMock(return_value={"title": "Rozmowa o farmie żelaza"})
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        count = await scan_and_digest(sessions_root=root, db_path=tmp_db)

    assert count == 0  # nothing digested — just titled
    meta = json.loads((legacy / "meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Rozmowa o farmie żelaza"
