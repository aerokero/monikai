"""Regression tests for the deliberately small memory architecture."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from backend.core.runtimes.v2_runtime import V2Runtime
from backend.soul.assembler.context import ContextAssembler
from backend.soul.memory import store as mem_store
from backend.soul.memory.digest import digest_session
from backend.soul.models import MemoryEntry


async def test_startup_prompt_contains_no_generated_memory_or_state(tmp_db):
    await mem_store.add(
        MemoryEntry(
            id="old-topic",
            type="semantic",
            content="Cornel nocleguje dziś u Bartka.",
            importance=9.0,
        ),
        db_path=tmp_db,
    )

    prompt = await ContextAssembler().assemble(
        "CHARACTER", "OPERATIONAL", db_path=tmp_db
    )

    assert "Cornel" not in prompt


async def test_observe_turn_does_not_search_or_return_memory(tmp_db):
    runtime = V2Runtime(db_path=tmp_db)
    with patch(
        "backend.soul.memory.store.search_fts", new=AsyncMock()
    ) as search:
        result = await runtime.observe_turn()

    assert result is None
    search.assert_not_awaited()


async def test_insignificant_digest_persists_nothing(tmp_path, tmp_db):
    session_dir = tmp_path / "sessions" / "2026-07-17" / "sess_noise"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"session_id": "sess_noise"}), encoding="utf-8"
    )
    turns = [
        {"timestamp": 1.0, "sender": "User", "text": "hej co tam, testuję tylko mikrofon i ustawienia wejścia audio; sprawdzam czy dźwięk działa stabilnie, ale to wyłącznie techniczny test i zaraz kończę bez żadnego ważnego tematu", "session_id": "sess_noise"},
        {"timestamp": 2.0, "sender": "AI", "text": "hej, działa", "session_id": "sess_noise"},
    ]
    (session_dir / "turns.jsonl").write_text(
        "\n".join(json.dumps(turn, ensure_ascii=False) for turn in turns) + "\n",
        encoding="utf-8",
    )

    fake = AsyncMock()
    fake.chat_json = AsyncMock(
        return_value={
            "significant": False,
            "title": "Test mikrofonu",
            "recap": "Krótki test mikrofonu.",
        }
    )
    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        result = await digest_session(session_dir, db_path=tmp_db)

    assert result is None
    assert await mem_store.list_recent(db_path=tmp_db) == []
    meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["digest"]["status"] == "skipped_insignificant"


async def test_digest_never_writes_memory(tmp_path, tmp_db):
    session_dir = tmp_path / "sessions" / "2026-07-17" / "sess_history"
    session_dir.mkdir(parents=True)
    (session_dir / "meta.json").write_text("{}", encoding="utf-8")
    user_text = "Mam stabilne preferencje i opowiem o nich wystarczająco długo, żeby ta rozmowa przekroczyła techniczny próg długości używany przez digest. " * 2
    turns = [{"timestamp": 1.0, "sender": "User", "text": user_text}]
    (session_dir / "turns.jsonl").write_text(
        json.dumps(turns[0], ensure_ascii=False) + "\n", encoding="utf-8"
    )
    fake = AsyncMock()
    fake.chat_json = AsyncMock(return_value={
        "significant": True,
        "title": "Trwałe preferencje",
        "recap": "Rozmowa o preferencjach.",
    })

    with patch("backend.soul.memory.digest.get_client", return_value=fake):
        await digest_session(session_dir, db_path=tmp_db)

    assert await mem_store.list_recent(db_path=tmp_db) == []
