from types import SimpleNamespace

from backend.core.handlers.lorebook_handlers import register_lorebook_handlers
from backend.soul.lorebook import LoreCandidate, Lorebook
from backend.soul.lorebook import store


class FakeSio:
    def __init__(self):
        self.handlers = {}
        self.emitted = []

    def event(self, function):
        self.handlers[function.__name__] = function
        return function

    async def emit(self, event, payload, room=None):
        self.emitted.append((event, payload, room))


def _register(tmp_db, conversation_id="session-1"):
    sio = FakeSio()
    loop = SimpleNamespace(
        session_manager=SimpleNamespace(
            get_current_session_id=lambda: conversation_id
        )
    )
    register_lorebook_handlers(
        sio,
        get_audio_loop=lambda: loop,
        db_path=tmp_db,
    )
    return sio


async def test_lore_state_uses_current_conversation(tmp_db):
    await store.upsert_lorebook(
        Lorebook(id="reality", name="Reality", kind="reality"),
        tmp_db,
    )
    sio = _register(tmp_db)

    payload = await sio.handlers["lore_state_get"]("client", {})

    assert payload["conversation_id"] == "session-1"
    assert payload["lorebooks"][0]["id"] == "reality"
    assert payload["world_stack"]["conversation_id"] == "session-1"
    assert sio.emitted[-1][0] == "lore_state"


async def test_world_stack_update_validates_ids_and_mode(tmp_db):
    await store.upsert_lorebook(
        Lorebook(id="reality", name="Reality", kind="reality"),
        tmp_db,
    )
    sio = _register(tmp_db)

    accepted = await sio.handlers["lore_world_stack_set"](
        "client",
        {
            "reality_mode": "crossover",
            "lorebook_ids": ["reality"],
            "token_budget": 900,
        },
    )
    rejected = await sio.handlers["lore_world_stack_set"](
        "client",
        {
            "reality_mode": "grounded",
            "lorebook_ids": ["unknown"],
        },
    )

    stack = await store.get_world_stack("session-1", tmp_db)
    assert accepted["ok"] is True
    assert stack.reality_mode == "crossover"
    assert stack.lorebook_ids == ["reality"]
    assert rejected["ok"] is False
    assert "Unknown or disabled" in rejected["error"]


async def test_socket_import_does_not_activate_or_trust_book(tmp_db):
    sio = _register(tmp_db)

    result = await sio.handlers["lore_import"](
        "client",
        {
            "file_name": "night-city.json",
            "content": """
            {
              "name": "Night City",
              "trusted": true,
              "entries": {
                "0": {
                  "comment": "Arasaka",
                  "content": "Arasaka controls Mikoshi.",
                  "key": ["Arasaka"]
                }
              }
            }
            """,
        },
    )

    book = await store.get_lorebook("night-city", tmp_db)
    stack = await store.get_world_stack("session-1", tmp_db)
    assert result["ok"] is True
    assert result["entry_count"] == 1
    assert book is not None and book.trusted is False
    assert stack.lorebook_ids == []


async def test_socket_export_returns_download_payload(tmp_db):
    sio = _register(tmp_db)
    await sio.handlers["lore_import"](
        "client",
        {
            "file_name": "world.md",
            "content": "# Rainy world\n\nIt rains every evening.",
        },
    )

    result = await sio.handlers["lore_export"](
        "client",
        {"book_id": "rainy-world", "format": "markdown"},
    )

    assert result["ok"] is True
    assert result["filename"] == "rainy-world.md"
    assert "It rains every evening." in result["content"]


async def test_candidate_review_updates_queue_and_creates_lore(tmp_db):
    candidate = await store.add_lore_candidate(
        LoreCandidate(
            conversation_id="session-1",
            target_type="world_lore",
            target_lorebook_id="reality",
            title="Biuro",
            content="Biuro jest w Warszawie.",
            confidence=0.94,
        ),
        tmp_db,
    )
    sio = _register(tmp_db)

    result = await sio.handlers["lore_candidate_review"](
        "client",
        {
            "candidate_id": candidate.id,
            "accept": True,
            "edits": {
                "title": "Lokalizacja biura",
                "content": "Biuro znajduje się w Warszawie.",
            },
        },
    )

    assert result["ok"] is True
    assert result["candidate"]["status"] == "accepted"
    assert result["state"]["candidates"] == []
    assert await store.get_lorebook("reality", tmp_db) is not None
