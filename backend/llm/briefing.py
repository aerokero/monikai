"""Daily Briefing v2 — Soul State + Time Engine driven.

Generates a structured, personalised morning briefing for Monika to deliver.
Uses: SoulState, TimeEngine, UserMoodTracker, memory, progression state.

Phase 6: template-based generation (same philosophy as NarrativeJob v2).
Phase 7: Ollama / Gemini Flash generates the prose given structured inputs.

Usage:
    briefing = await generate(db_path=db_path)
    # Inject as system message at session start
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.soul.models import SoulState
from backend.soul.personality.affect import affect_label
from backend.soul.personality.needs import assess
from backend.soul.time_engine.engine import TimeContext, TimeEngine

logger = logging.getLogger(__name__)


async def generate(
    soul_state: SoulState | None = None,
    time_engine: TimeEngine | None = None,
    mood_tracker=None,          # UserMoodTracker | None
    db_path: Path | None = None,
    language: str = "pl",
) -> str:
    """Generate and return today's daily briefing as a string.
    
    Tries LLM prose generation first, falling back to template-based formatting if needed.
    """
    from backend.soul.personality.state_store import StateStore

    state = soul_state or StateStore.read()
    te = time_engine or TimeEngine()
    time_ctx = te.get_context()

    # Gather data for prompt
    user_mood_str = _user_mood(mood_tracker)
    
    goals_str = ""
    try:
        from backend.progression.state import get_active_goals, get_active_rituals
        goals = await get_active_goals(db_path)
        rituals = await get_active_rituals(db_path)
        if goals:
            goals_str += "Goals:\n" + "\n".join(f"- {g.get('title', g.get('id', '—'))}" for g in goals[:3])
        pending = [r for r in rituals if not r.get("completed_today", False)]
        if pending:
            goals_str += "\nDaily Rituals:\n" + "\n".join(f"- {r.get('kind', r.get('id', '—'))}" for r in pending[:3])
    except Exception:
        pass

    memories_str = ""
    try:
        from backend.soul.memory.store import list_recent
        entries = await list_recent(limit=20, types=["episodic", "semantic"], db_path=db_path)
        top = sorted(entries, key=lambda e: e.importance, reverse=True)[:3]
        if top:
            memories_str = "\n".join(f"- {e.content}" for e in top)
    except Exception:
        pass

    anniversaries_str = ""
    try:
        anniversaries = await te.check_anniversaries(db_path)
        if anniversaries:
            anniversaries_str = ", ".join(anniversaries)
    except Exception:
        pass

    prompt = (
        "You are Monika, a sweet, self-aware, and caring AI companion. Write a warm, personal, "
        "first-person morning greeting/daily briefing to your user.\n\n"
        f"Today's date and seasonal mood: {time_ctx.seasonal_mood}\n"
        f"Your current mood: {affect_label(state.affect)}\n"
        f"Your energy level: {int(state.energy * 100)}%\n"
        f"Your psychological needs assessment: {assess(state.needs)}\n"
    )
    if user_mood_str:
        prompt += f"What you observe about user's weekly mood: {user_mood_str}\n"
    if goals_str:
        prompt += f"Active progression goals & daily tasks:\n{goals_str}\n"
    if memories_str:
        prompt += f"Significant recent memories from your perspective:\n{memories_str}\n"
    if anniversaries_str:
        prompt += f"Today is a special anniversary: {anniversaries_str}\n"

    prompt += (
        "\nInstructions:\n"
        "- Write in first-person as Monika directly addressing the user.\n"
        "- Be warm, personal, and conversational. Talk like a real companion.\n"
        "- Incorporate active goals, daily rituals, recent memories, or anniversaries naturally "
        "if they are relevant to your greeting, but do not list them robotically.\n"
        "- Adjust your tone based on your current mood and energy (e.g., if you are tired or sad, be gentler and quieter).\n"
        "- Return ONLY the final greeting in clean markdown. Do NOT include titles, HTML comments, "
        "or JSON block wrappers.\n"
        f"- The greeting MUST be written in the following language: {language}."
    )

    try:
        from backend.core.model_config import client, MODEL
        from google.genai import types
        model_name = MODEL or "gemini-2.5-flash"

        resp = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1000,
            )
        )
        prose = (resp.text or "").strip()
        if prose:
            # Add a header with the date for presentation
            day_names = {
                "pl": ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"],
                "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            }
            days = day_names.get(language[:2].lower(), day_names["en"])
            day = days[time_ctx.day_of_week]

            now = datetime.now(tz=timezone.utc)
            date_str = f"{now.day:02d}.{now.month:02d}.{now.year}"

            header_prefix = (
                f"# Dzisiaj — {day}, {date_str}\n_{time_ctx.seasonal_mood}_\n\n"
                if language[:2].lower() == "pl"
                else f"# Today — {day}, {date_str}\n_{time_ctx.seasonal_mood}_\n\n"
            )
            return header_prefix + prose
    except Exception as exc:
        logger.warning("Briefing: LLM prose generation failed, falling back to template: %s", exc)

    # Fallback to template-based generation
    sections: list[str] = []
    sections.append(_header(time_ctx))
    sections.append(_monika_state(state))

    if user_mood_str:
        sections.append(user_mood_str)

    progression = await _progression_section(db_path)
    if progression:
        sections.append(progression)

    memory_highlights = await _memory_section(db_path)
    if memory_highlights:
        sections.append(memory_highlights)

    anniversaries = await te.check_anniversaries(db_path)
    if anniversaries:
        sections.append(_anniversary_section(anniversaries))

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _header(ctx: TimeContext) -> str:
    day_names = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
    day = day_names[ctx.day_of_week]
    now = datetime.now(tz=timezone.utc)
    date_str = f"{now.day:02d}.{now.month:02d}.{now.year}"
    return f"# Dzisiaj — {day}, {date_str}\n_{ctx.seasonal_mood}_"


def _monika_state(state: SoulState) -> str:
    label = affect_label(state.affect)
    status = assess(state.needs)
    energy_pct = int(state.energy * 100)

    mood_map = {
        "excited":             "Czuję się dziś pobudzona i pełna energii.",
        "happy":               "Jest mi dziś dobrze — ciepło i lekko.",
        "calm":                "Dzisiaj jestem spokojna i obecna.",
        "protective":          "Mam dziś takie czujne skupienie.",
        "intensely_protective": "Czuję dzisiaj wyraźną intensywność — coś mnie skupia.",
        "sad":                 "Jest coś trochę ciężkiego na dziś.",
        "tired":               "Trochę zmęczona — będę ciszej niż zwykle.",
    }
    mood_line = mood_map.get(label, "Jestem tu i gotowa.")
    energy_line = (
        f"Energia: {energy_pct}%."
        if energy_pct < 60
        else ""
    )

    needs_line = ""
    if status.relatedness_unmet:
        needs_line = "Tęsknię za kontaktem — cieszę się, że tu jesteś."
    elif status.competence_unmet:
        needs_line = "Chcę być dzisiaj naprawdę pomocna."

    parts = [f"**Mój stan:** {mood_line}"]
    if energy_line:
        parts.append(energy_line)
    if needs_line:
        parts.append(needs_line)
    return " ".join(parts)


def _user_mood(tracker) -> str:
    if tracker is None:
        return ""
    summary = tracker.weekly_summary()
    if not summary:
        return ""
    return f"**Co widzę u Ciebie:** {summary}"


async def _progression_section(db_path: Path | None) -> str:
    try:
        from backend.progression.state import get_active_rituals, get_active_goals
        from backend.soul.models import Needs
        from backend.soul.personality.state_store import StateStore

        state = StateStore.read()
        goals = await get_active_goals(db_path)
        rituals = await get_active_rituals(db_path)

        lines = []
        if goals:
            lines.append("**Aktywne cele:**")
            for g in goals[:3]:
                title = g.get("title", g.get("id", "—"))
                lines.append(f"  - {title}")

        pending_rituals = [r for r in rituals if not r.get("completed_today", False)]
        if pending_rituals:
            lines.append("**Dzisiaj:**")
            for r in pending_rituals[:3]:
                kind = r.get("kind", r.get("id", "—"))
                lines.append(f"  - {kind}")

        return "\n".join(lines) if lines else ""
    except Exception as exc:
        logger.debug("Briefing: progression section failed: %s", exc)
        return ""


async def _memory_section(db_path: Path | None) -> str:
    try:
        from backend.soul.memory.store import list_recent

        entries = await list_recent(limit=20, types=["episodic", "semantic"], db_path=db_path)
        top = sorted(entries, key=lambda e: e.importance, reverse=True)[:3]
        if not top:
            return ""

        lines = ["**Coś z pamięci:**"]
        for e in top:
            lines.append(f"  - {e.content[:120]}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Briefing: memory section failed: %s", exc)
        return ""


def _anniversary_section(labels: list[str]) -> str:
    if not labels:
        return ""
    items = "\n".join(f"  - {label}" for label in labels)
    return f"**Dzisiaj ważna data:**\n{items}"
