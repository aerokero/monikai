import time
from datetime import datetime, timezone

from ..ai.daily_briefing import (
    DEFAULT_SECTIONS,
    build_daily_briefing,
    fetch_weather_details,
    normalize_profile,
)


class DailyBriefingRuntime:
    def __init__(
        self,
        settings: dict,
        *,
        get_audio_loop,
        get_personality_system,
        get_v2_runtime=None,
    ):
        self._settings = settings
        self._get_audio_loop = get_audio_loop
        self._get_personality_system = get_personality_system
        self._get_v2_runtime = get_v2_runtime or _default_v2_runtime
        self._cache = {"ts": 0.0, "lang": "pl", "payload": None}
        self._rejected_until = {}

    def _language(self, raw: str = "pl") -> str:
        raw_lower = str(raw or "pl").lower()
        if raw_lower.startswith("pl"):
            return "pl"
        if raw_lower.startswith("zh"):
            return "zh"
        if raw_lower.startswith("ja"):
            return "ja"
        return "en"

    def get_profile(self) -> dict:
        section = self._settings.setdefault("daily_briefing", {})
        profile = normalize_profile(section.get("profile") or {})
        section["profile"] = profile
        return profile

    def set_profile(self, profile: dict) -> dict:
        normalized = normalize_profile(profile or {})
        self._settings.setdefault("daily_briefing", {})["profile"] = normalized
        return normalized

    def invalidate_cache(self):
        self._cache["payload"] = None
        self._cache["ts"] = 0.0

    def reject_proposal(self, from_section: str, to_section: str, cooldown_hours: int):
        if from_section and to_section:
            key = f"{from_section}->{to_section}"
            self._rejected_until[key] = time.time() + max(1, int(cooldown_hours)) * 3600

    def _is_proposal_rejected(self, proposal: dict) -> bool:
        pair = f"{proposal.get('from_section')}->{proposal.get('to_section')}"
        until = float(self._rejected_until.get(pair, 0.0) or 0.0)
        return time.time() < until

    async def _build_v2_briefing(self, language: str = "pl") -> dict | None:
        try:
            runtime = self._get_v2_runtime()
            if runtime is None or not hasattr(runtime, "generate_briefing"):
                return None
            text = await runtime.generate_briefing(language=language)
        except Exception:
            return None

        text = str(text or "").strip()
        if not text:
            return None
        return {
            "mode": "soul_engine",
            "format": "markdown",
            "text": text,
        }

    def _collect_context(self, language: str = "pl") -> tuple[list, str, str, dict]:
        memory_entries = []
        topic_hint = ""
        weather_summary = ""
        weather_details = {}

        audio_loop = self._get_audio_loop()
        personality_system = self._get_personality_system()

        if audio_loop and getattr(audio_loop, "memory_engine", None):
            try:
                memory_entries = audio_loop.memory_engine.list_recent(
                    limit=25,
                    types=["fact", "preference", "event", "reflection"],
                )
            except Exception:
                memory_entries = []

        if audio_loop and getattr(audio_loop, "proactivity", None):
            try:
                topic_hint = audio_loop.proactivity.pick_topic_hint() or ""
            except Exception:
                topic_hint = ""

        if personality_system:
            try:
                personality_system.update_weather(force=False)
                weather_summary = str(getattr(personality_system.state, "weather", "") or "")
            except Exception:
                weather_summary = ""

        try:
            weather_details = fetch_weather_details(language=language, days=7)
            detail_summary = str((weather_details or {}).get("summary") or "")
            if detail_summary:
                weather_summary = detail_summary
        except Exception:
            weather_details = {}

        return memory_entries, topic_hint, weather_summary, weather_details

    async def build_payload(self, language: str = "pl", force: bool = False) -> dict:
        lang = self._language(language)
        cfg = self._settings.setdefault("daily_briefing", {})
        if not bool(cfg.get("enabled", True)):
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "language": lang,
                "active_sections": [],
                "sections": [],
                "profile": self.get_profile(),
                "proposal": None,
                "disabled": True,
            }

        cache_minutes = max(1, int(cfg.get("cache_minutes", 20)))
        now_ts = time.time()
        if not force and self._cache.get("payload") and self._cache.get("lang") == lang:
            if (now_ts - float(self._cache.get("ts", 0.0))) < (cache_minutes * 60):
                return self._cache["payload"]

        profile = self.get_profile()
        memory_entries, topic_hint, weather_summary, weather_details = self._collect_context(language=lang)

        payload = build_daily_briefing(
            profile=profile,
            language=lang,
            weather_summary=weather_summary,
            weather_details=weather_details,
            memory_entries=memory_entries,
            topic_hint=topic_hint,
        )

        payload["section_options"] = [
            {
                "id": sid,
                "title": cfg_data.get("title", {}).get(lang, cfg_data.get("title", {}).get("en", sid)),
            }
            for sid, cfg_data in DEFAULT_SECTIONS.items()
        ]

        proposal = payload.get("proposal")
        if proposal and self._is_proposal_rejected(proposal):
            payload["proposal"] = None

        if bool(cfg.get("use_v2_briefing", False)):
            v2_briefing = await self._build_v2_briefing(language=lang)
            if v2_briefing:
                payload["v2_briefing"] = v2_briefing

        self._cache["payload"] = payload
        self._cache["lang"] = lang
        self._cache["ts"] = now_ts
        return payload


def _default_v2_runtime():
    try:
        from backend.core.v2_runtime import get
        return get()
    except Exception:
        return None
