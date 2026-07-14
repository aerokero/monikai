"""Tests for the session digest pipeline (v3 Phase A)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.soul.memory import agenda_store
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
) -> Path:
    sess_dir = tmp_path / "sessions" / day / session_id
    sess_dir.mkdir(parents=True)
    (sess_dir / "meta.json").write_text(
        json.dumps({"session_id": session_id}), encoding="utf-8"
    )
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
    "facts": [
        {"content": "Bartek skończył farmę żelaza w Minecrafcie po tygodniu pracy.",
         "importance": 4, "entities": ["Minecraft", "farma żelaza"]},
        {"content": "Bartek zaczyna nowy projekt w pracy z nowym zespołem.",
         "importance": 6, "entities": ["praca"]},
    ],
    "episodes": [
        {"content": "Pamiętam jak z dumą opowiadał o skończonej farmie żelaza.",
         "importance": 5},
    ],
    "agenda": ["zapytać jak poszedł pierwszy dzień nowego projektu"],
    "user_state": "Bartek jest zadowolony z ukończonego projektu, ale zestresowany nową pracą.",
}


def test_load_transcript_maps_senders(tmp_path):
    sess = _make_session(tmp_path, turns=[("User", "cześć"), ("AI", "hej!")])
    transcript, user_chars = load_transcript(sess)
    assert "Bartek: cześć" in transcript
    assert "Monika: hej!" in transcript
    assert user_chars == len("cześć")


async def test_digest_trivial_session_skipped_and_marked(tmp_path, tmp_db):
    sess = _make_session(tmp_path, turns=[("User", "hej"), ("AI", "hej!")])
    with patch("backend.soul.memory.digest.get_client") as mock_client:
        result = await digest_session(sess, db_path=tmp_db)
    assert result is None
    mock_client.assert_not_called()
    meta = json.loads((sess / "meta.json").read_text(encoding="utf-8"))
    assert meta["digest"]["status"] == "skipped_trivial"


async def test_digest_stores_facts_episodes_agenda(tmp_path, tmp_db, monkeypatch):
    monkeypatch.setattr(
        "backend.soul.memory.digest._USER_STATE_PATH",
        tmp_path / "soul" / "user_state.md",
    )
    sess = _make_session(tmp_path, turns=_RICH_TURNS)

    fake = AsyncMock()
    fake.chat_json = AsyncMock(return_value=_LLM_RESULT)
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        result = await digest_session(sess, db_path=tmp_db)

    assert isinstance(result, SessionDigest)

    semantic = await mem_store.list_recent(types=["semantic"], db_path=tmp_db)
    episodic = await mem_store.list_recent(types=["episodic"], db_path=tmp_db)
    assert len(semantic) == 2
    assert len(episodic) == 1
    assert episodic[0].perspective == "hers"
    assert semantic[0].source_session == "sess_test_001"

    items = await agenda_store.open_items(db_path=tmp_db)
    assert len(items) == 1
    assert "projektu" in items[0]["text"]

    user_state = (tmp_path / "soul" / "user_state.md").read_text(encoding="utf-8")
    assert "zestresowany" in user_state

    meta = json.loads((sess / "meta.json").read_text(encoding="utf-8"))
    assert meta["digest"]["status"] == "done"
    assert meta["digest"]["facts"] == 2


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
    monkeypatch.setattr(
        "backend.soul.memory.digest._USER_STATE_PATH",
        tmp_path / "soul" / "user_state.md",
    )
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


async def test_agenda_store_dedup_and_expiry(tmp_db):
    added = await agenda_store.add_items(
        ["zapytać o projekt", "zapytać o projekt", "  "], db_path=tmp_db
    )
    assert added == 1
    items = await agenda_store.open_items(db_path=tmp_db)
    assert len(items) == 1

    await agenda_store.resolve(items[0]["id"], "done", db_path=tmp_db)
    assert await agenda_store.open_items(db_path=tmp_db) == []
