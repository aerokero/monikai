from __future__ import annotations

import sys
from pathlib import Path

import pytest


ODY_ROOT = Path(__file__).resolve().parents[2] / "backend" / "odysseus"
if str(ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(ODY_ROOT))

from core.models import ChatMessage, Session  # noqa: E402
from backend.soul.lorebook import LoreEntry, Lorebook, WorldStack  # noqa: E402
from backend.soul.lorebook import store  # noqa: E402
from routes.chat_helpers import _active_lore_context_message  # noqa: E402


@pytest.mark.asyncio
async def test_active_world_lore_is_added_as_guarded_chat_context(tmp_db):
    await store.upsert_lorebook(
        Lorebook(
            id="night_city",
            name="Night City",
            kind="imported_fiction",
        ),
        tmp_db,
    )
    await store.upsert_entry(
        LoreEntry(
            id="arasaka",
            lorebook_id="night_city",
            title="Arasaka",
            content="Arasaka controls Mikoshi.",
            keys=["Arasaka"],
        ),
        tmp_db,
    )
    await store.set_world_stack(
        WorldStack(
            conversation_id="session-roleplay",
            reality_mode="roleplay",
            lorebook_ids=["night_city"],
        ),
        tmp_db,
    )

    session = Session(
        id="session-roleplay",
        name="Roleplay",
        endpoint_url="http://llm.test",
        model="model",
        history=[ChatMessage(role="assistant", content="Słucham.")],
    )

    message = await _active_lore_context_message(
        sess=session,
        session_id=session.id,
        current_message="Co Arasaka trzyma w Mikoshi?",
        incognito=False,
        is_research_spinoff=False,
        db_path=tmp_db,
    )

    assert message is not None
    assert message["role"] == "user"
    assert message["metadata"]["provenance_origin"] == "world_stack"
    assert "active world lore" in message["content"]
    assert 'reality_mode="roleplay"' in message["content"]
    assert "Arasaka controls Mikoshi." in message["content"]


@pytest.mark.asyncio
async def test_active_world_lore_does_not_leak_into_incognito(tmp_db):
    await store.upsert_lorebook(Lorebook(id="world", name="World"), tmp_db)
    await store.set_world_stack(
        WorldStack(conversation_id="incognito-session", lorebook_ids=["world"]),
        tmp_db,
    )

    session = Session(
        id="incognito-session",
        name="Incognito",
        endpoint_url="http://llm.test",
        model="model",
    )
    message = await _active_lore_context_message(
        sess=session,
        session_id=session.id,
        current_message="hello",
        incognito=True,
        is_research_spinoff=False,
        db_path=tmp_db,
    )

    assert message is None
