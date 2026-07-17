"""Tests for the Context Assembler."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.soul.assembler.context import ContextAssembler
from backend.soul.memory import store
from backend.soul.models import MemoryEntry


_CHARACTER = "Jesteś Moniką. Ciepła, bystra, prawdziwa."
_OPERATIONAL = "**ZASADY:** Zawsze używaj narzędzi. Bądź szczera."


async def test_assembler_includes_character(tmp_db):
    assembler = ContextAssembler()
    result = await assembler.assemble(_CHARACTER, _OPERATIONAL, db_path=tmp_db)
    assert _CHARACTER in result


async def test_assembler_includes_operational(tmp_db):
    assembler = ContextAssembler()
    result = await assembler.assemble(_CHARACTER, _OPERATIONAL, db_path=tmp_db)
    assert _OPERATIONAL in result


async def test_assembler_sections_ordered(tmp_db):
    assembler = ContextAssembler()
    result = await assembler.assemble(_CHARACTER, _OPERATIONAL, db_path=tmp_db)
    char_pos = result.index(_CHARACTER)
    op_pos = result.index(_OPERATIONAL)
    assert char_pos < op_pos, "CHARACTER must come before OPERATIONAL"


async def test_assembler_does_not_inject_memory_without_a_turn_query(tmp_db):
    entry = MemoryEntry(
        id="x", type="stm", content="Bartosz lubi ciemny chleb żytni", importance=6.0
    )
    await store.add(entry, db_path=tmp_db)

    assembler = ContextAssembler()
    result = await assembler.assemble(_CHARACTER, _OPERATIONAL, db_path=tmp_db)
    assert "ciemny chleb żytni" not in result


async def test_assembler_memory_block_empty_db(tmp_db):
    assembler = ContextAssembler()
    result = await assembler.assemble(_CHARACTER, _OPERATIONAL, db_path=tmp_db)
    # Should not raise; just no memory section
    assert isinstance(result, str)
    assert len(result) > 0


async def test_assembler_does_not_treat_recency_as_relevance(tmp_db):
    """LTM is retrieved per turn, not injected merely because it is recent."""
    ltm = MemoryEntry(
        id="x", type="episodic", content="Pamiętam nasz pierwszy wieczór przy filmie", importance=8.5
    )
    low = MemoryEntry(
        id="y", type="episodic", content="zwykłe codzienne zdanie", importance=4.0
    )
    await store.add(ltm, db_path=tmp_db)
    await store.add(low, db_path=tmp_db)

    assembler = ContextAssembler()
    result = await assembler.assemble(_CHARACTER, _OPERATIONAL, db_path=tmp_db)
    assert "pierwszy wieczór" not in result
    assert "zwykłe codzienne zdanie" not in result


async def test_assemble_prompt_function(tmp_db):
    """Test the top-level assemble_prompt() in system_prompt.py."""
    from backend.core.system_prompt import assemble_prompt
    result = await assemble_prompt(db_path=tmp_db)
    assert isinstance(result, str)
    assert len(result) > 100


async def test_assemble_prompt_fallback_on_error(tmp_db, monkeypatch):
    """assemble_prompt() must fall back to SYSTEM_PROMPT if assembler errors."""
    from backend.core.system_prompt import assemble_prompt, SYSTEM_PROMPT
    import backend.soul.assembler.context as ctx

    def _broken(*a, **kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(ctx.ContextAssembler, "assemble", _broken)
    result = await assemble_prompt(db_path=tmp_db)
    assert result == SYSTEM_PROMPT
