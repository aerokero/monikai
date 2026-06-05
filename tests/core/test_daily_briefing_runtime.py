from __future__ import annotations

from backend.core.daily_briefing_runtime import DailyBriefingRuntime


class _FakeV2Runtime:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def generate_briefing(self, language: str = "pl") -> str:
        self.calls += 1
        return self.text


def _settings(use_v2: bool = False) -> dict:
    return {
        "daily_briefing": {
            "enabled": True,
            "cache_minutes": 20,
            "use_v2_briefing": use_v2,
            "profile": {
                "pinned_sections": ["weather"],
                "preferred_sections": [],
                "auto_slots": 3,
                "candidate_pool": ["weather"],
                "proposal_policy": {"enabled": True, "min_confidence": 0.65, "cooldown_hours": 12},
                "language_mode": "auto",
                "max_items_per_section": 5,
            },
        }
    }


def _runtime(settings: dict, v2=None) -> DailyBriefingRuntime:
    runtime = DailyBriefingRuntime(
        settings,
        get_audio_loop=lambda: None,
        get_personality_system=lambda: None,
        get_v2_runtime=lambda: v2,
    )
    runtime._collect_context = lambda language="pl": ([], "", "Clear, 20C", {"summary": "Clear, 20C", "items": []})
    return runtime


async def test_daily_briefing_v2_flag_disabled(monkeypatch):
    fake_v2 = _FakeV2Runtime("# V2 briefing")
    runtime = _runtime(_settings(use_v2=False), fake_v2)

    payload = await runtime.build_payload(language="pl", force=True)

    assert "sections" in payload
    assert "v2_briefing" not in payload
    assert fake_v2.calls == 0


async def test_daily_briefing_v2_flag_attaches_markdown(monkeypatch):
    fake_v2 = _FakeV2Runtime("# V2 briefing\nSoul State text")
    runtime = _runtime(_settings(use_v2=True), fake_v2)

    payload = await runtime.build_payload(language="pl", force=True)

    assert "sections" in payload
    assert payload["v2_briefing"] == {
        "mode": "soul_engine",
        "format": "markdown",
        "text": "# V2 briefing\nSoul State text",
    }
    assert fake_v2.calls == 1


async def test_daily_briefing_v2_empty_text_is_ignored():
    fake_v2 = _FakeV2Runtime("")
    runtime = _runtime(_settings(use_v2=True), fake_v2)

    payload = await runtime.build_payload(language="pl", force=True)

    assert "sections" in payload
    assert "v2_briefing" not in payload


async def test_daily_briefing_disabled_skips_v2():
    fake_v2 = _FakeV2Runtime("# skipped")
    settings = _settings(use_v2=True)
    settings["daily_briefing"]["enabled"] = False
    runtime = _runtime(settings, fake_v2)

    payload = await runtime.build_payload(language="pl", force=True)

    assert payload["disabled"] is True
    assert "v2_briefing" not in payload
    assert fake_v2.calls == 0
