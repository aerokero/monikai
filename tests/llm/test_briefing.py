from __future__ import annotations

from datetime import date

from backend.llm.briefing import generate
from backend.soul.memory import store
from backend.soul.models import Affect, MemoryEntry, Needs, SoulState
from backend.soul.time_engine.engine import TimeContext


class _FakeTimeEngine:
    def get_context(self):
        return TimeContext(
            hour=8,
            day_of_week=4,
            month=6,
            season="summer",
            time_of_day="ranek",
            energy_hint=0.65,
            seasonal_mood="Dni długie, ciepłe. Energie wyższe.",
        )

    async def check_anniversaries(self, db_path=None, today: date | None = None):
        return ["Pierwszy film razem"]


class _FakeMoodTracker:
    def weekly_summary(self) -> str:
        return "Ostatnio jest mu lżej."


async def test_generate_briefing_includes_core_sections(tmp_db):
    state = SoulState(
        affect=Affect(pleasure=0.6, arousal=0.4, dominance=0.1),
        needs=Needs(autonomy=0.8, competence=0.7, relatedness=0.9),
        energy=0.75,
    )

    result = await generate(
        soul_state=state,
        time_engine=_FakeTimeEngine(),
        mood_tracker=_FakeMoodTracker(),
        db_path=tmp_db,
    )

    assert "# Dzisiaj" in result
    assert "Piątek" in result
    assert "Mój stan" in result
    assert "Co widzę u Ciebie" in result
    assert "Pierwszy film razem" in result


async def test_generate_briefing_includes_memory(tmp_db):
    await store.add(
        MemoryEntry(
            id="x",
            type="episodic",
            content="Pamiętam spokojny wieczór przy filmie.",
            importance=8.0,
            perspective="hers",
        ),
        db_path=tmp_db,
    )

    result = await generate(
        time_engine=_FakeTimeEngine(),
        mood_tracker=None,
        db_path=tmp_db,
    )

    assert "Coś z pamięci" in result
    assert "spokojny wieczór" in result


async def test_generate_briefing_llm_path(tmp_db, monkeypatch):
    from unittest.mock import MagicMock
    
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Hello from Gemini Daily Briefing!"
    
    async def mock_generate_content(*args, **kwargs):
        return mock_response
        
    mock_client.aio.models.generate_content = mock_generate_content
    
    import backend.core.model_config as mc
    monkeypatch.setattr(mc, "client", mock_client)
    monkeypatch.setattr(mc, "MODEL", "gemini-mock")
    
    from backend.soul.models import Affect, Needs, SoulState
    state = SoulState(
        affect=Affect(pleasure=0.6, arousal=0.4, dominance=0.1),
        needs=Needs(autonomy=0.8, competence=0.7, relatedness=0.9),
        energy=0.75,
    )
    
    result = await generate(
        soul_state=state,
        time_engine=_FakeTimeEngine(),
        mood_tracker=_FakeMoodTracker(),
        db_path=tmp_db,
        language="pl",
    )
    
    assert "Hello from Gemini Daily Briefing!" in result
    assert "# Dzisiaj" in result
