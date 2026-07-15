"""Tests for the conversation read-side helpers (v3 Phase G)."""

from __future__ import annotations

import json
from pathlib import Path

from backend.core.conversation_store import (
    build_continuation_context,
    delete_conversation,
    get_conversation,
    list_conversations,
    search_conversations,
)
from backend.core.session_manager import SessionManager


def _make_session(
    root: Path,
    session_id: str,
    day: str,
    turns: list[tuple[str, str]],
    meta_extra: dict | None = None,
) -> Path:
    sess_dir = root / day / session_id
    sess_dir.mkdir(parents=True)
    meta = {"session_id": session_id, "kind": "conversation", "channel": "app"}
    if meta_extra:
        meta.update(meta_extra)
    (sess_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    lines = [
        json.dumps({"timestamp": 1.0, "sender": s, "text": t, "session_id": session_id}, ensure_ascii=False)
        for s, t in turns
    ]
    (sess_dir / "turns.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sess_dir


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "sessions"
    _make_session(
        root, "sess_a", "2026-07-10",
        [("User", "porozmawiajmy o wakacjach w Chorwacji"), ("AI", "chętnie! gdzie dokładnie?")],
        {"title": "Plany wakacji w Chorwacji", "digest": {"status": "done"}},
    )
    _make_session(
        root, "sess_b", "2026-07-12",
        [("User", "pomóż mi z projektem w pracy"), ("AI", "jasne, od czego zaczynamy?")],
        {"title": "Projekt w pracy", "digest": {"status": "done"}},
    )
    _make_session(
        root, "stream_minecraft", "2026-07-12",
        [("MC:xtosu", "zbudowałem farmę żelaza"), ("AI", "pięknie wyszła!")],
        {"kind": "stream", "channel": "minecraft",
         "title": "Farma żelaza", "digest": {"status": "done", "recap": "Budowa farmy żelaza przy bazie."}},
    )
    # Empty session — should be hidden from the list.
    empty = root / "2026-07-13" / "sess_empty"
    empty.mkdir(parents=True)
    (empty / "meta.json").write_text(json.dumps({"session_id": "sess_empty"}), encoding="utf-8")
    return root


def test_list_conversations_newest_first_skips_empty(tmp_path):
    root = _fixture_root(tmp_path)
    items = list_conversations(root)
    ids = [i["id"] for i in items]
    assert ids == ["stream_minecraft", "sess_b", "sess_a"]
    assert all(i["turn_count"] > 0 for i in items)
    stream = items[0]
    assert stream["kind"] == "stream"
    assert stream["recap"] == "Budowa farmy żelaza przy bazie."


def test_get_conversation_returns_turns(tmp_path):
    root = _fixture_root(tmp_path)
    item = get_conversation(root, "sess_a")
    assert item is not None
    assert item["title"] == "Plany wakacji w Chorwacji"
    assert len(item["turns"]) == 2
    assert item["turns"][0]["text"].startswith("porozmawiajmy")
    assert get_conversation(root, "sess_nope") is None


def test_search_by_title_content_and_date(tmp_path):
    root = _fixture_root(tmp_path)

    by_title = search_conversations(root, "chorwacji")
    assert [h["id"] for h in by_title] == ["sess_a"]

    by_content = search_conversations(root, "farmę żelaza")
    assert by_content and by_content[0]["id"] == "stream_minecraft"
    assert "farmę żelaza" in by_content[0]["excerpt"]

    by_date = search_conversations(root, "2026-07-12")
    assert {h["id"] for h in by_date} == {"sess_b", "stream_minecraft"}

    assert search_conversations(root, "nieistniejący temat xyz") == []


def test_continuation_context_has_recap_and_last_turns(tmp_path):
    root = _fixture_root(tmp_path)
    ctx = build_continuation_context(root, "sess_a")
    assert "Plany wakacji w Chorwacji" in ctx
    assert "2026-07-10" in ctx
    assert "porozmawiajmy o wakacjach" in ctx
    assert build_continuation_context(root, "sess_nope") == ""


def test_delete_conversation_removes_dir(tmp_path):
    root = _fixture_root(tmp_path)
    assert delete_conversation(root, "sess_a") is True
    assert get_conversation(root, "sess_a") is None
    assert [i["id"] for i in list_conversations(root)] == ["stream_minecraft", "sess_b"]
    # Unknown id → False, nothing else touched.
    assert delete_conversation(root, "sess_nope") is False
    assert delete_conversation(root, "") is False
    assert get_conversation(root, "sess_b") is not None
    # Streams are deletable too.
    assert delete_conversation(root, "stream_minecraft") is True
    assert [i["id"] for i in list_conversations(root)] == ["sess_b"]


def test_continue_meta_written_by_session_manager(tmp_path):
    sm = SessionManager(tmp_path, write_mode="immediate")
    new_id = sm.start_new_session(extra_meta={"continues": "sess_old"})
    meta = json.loads((sm.get_current_session_path() / "meta.json").read_text(encoding="utf-8"))
    assert meta["continues"] == "sess_old"
    assert meta["session_id"] == new_id
    assert meta["kind"] == "conversation"
