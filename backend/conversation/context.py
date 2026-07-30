"""Compile character, current-thread history, world state, and lore.

The compiler is model-provider neutral. It creates one immutable context for a
finalized turn; retries reuse that context instead of consuming sticky lore or
observing a changing world twice.
"""

from __future__ import annotations

import inspect
import re
from html import escape
from pathlib import Path
from typing import Awaitable, Callable

from backend.soul.identity.character_loader import load_character_prompt
from backend.soul.lorebook import activate_lore, render_lore_context
from backend.soul.lorebook import store as lore_store

from .models import CompiledConversationContext

HistoryProvider = Callable[[int], list[dict]]
WorldSnapshotProvider = Callable[[], str | Awaitable[str]]

DEFAULT_HISTORY_TURNS = 16
DEFAULT_TURN_CHARS = 600

_AMBIENT_TOPICS = {
    "weather": re.compile(
        r"\b(pogod|temperatur|stopni|upa[łl]|gor[ąa]c|zimn|deszcz|"
        r"śnieg|snieg|burz|wiatr|cloud|weather|rain|hot|cold)\w*",
        re.IGNORECASE,
    ),
    "time": re.compile(
        r"\b(godzin|kt[oó]ra|rano|wiecz[oó]r|noc|dzisiaj|dzi[śs]|"
        r"poniedzia[łl]|wtorek|[śs]rod|czwartek|pi[ąa]tek|sobot|"
        r"niedziel|time|morning|evening|today)\w*",
        re.IGNORECASE,
    ),
    "spotify": re.compile(
        r"\b(spotify|muzyk|piosenk|utw[oó]r|album|s[łl]uch|music|song)\w*",
        re.IGNORECASE,
    ),
    "vision": re.compile(
        r"\b(ekran|kamer|widzisz|sp[oó]jrz|patrz|screen|camera|see)\w*",
        re.IGNORECASE,
    ),
    "gap": re.compile(
        r"\b(hej|cze[śs][ćc]|siema|dzie[ńn] dobry|dawno|wr[oó]ci|"
        r"hello|hi|long time)\w*",
        re.IGNORECASE,
    ),
}


class ConversationContextCompiler:
    def __init__(
        self,
        *,
        get_history: HistoryProvider,
        get_conversation_id: Callable[[], str | None],
        character_id: str = "monika",
        history_turns: int = DEFAULT_HISTORY_TURNS,
        turn_chars: int = DEFAULT_TURN_CHARS,
        get_world_snapshot: WorldSnapshotProvider | None = None,
        db_path: Path | None = None,
    ):
        self._get_history = get_history
        self._get_conversation_id = get_conversation_id
        self._character_prompt = load_character_prompt(character_id) or ""
        self._history_turns = max(1, int(history_turns))
        self._turn_chars = max(80, int(turn_chars))
        self._get_world_snapshot = get_world_snapshot
        self._db_path = db_path

    async def compile(
        self,
        *,
        user_text: str,
        author_instruction: str,
        turn_id: str | None = None,
        turn_evidence: str | None = None,
    ) -> CompiledConversationContext:
        conversation_id = (
            str(self._get_conversation_id() or "").strip() or "conversation"
        )
        history = self._history_without_current(user_text)
        stack = await lore_store.get_world_stack(conversation_id, self._db_path)

        recent_text = [entry["text"] for entry in history]
        recent_text.append(user_text)
        activated = await activate_lore(
            conversation_id=conversation_id,
            turn_id=turn_id,
            recent_messages=recent_text,
            world_stack=stack,
            db_path=self._db_path,
        )
        lore_context = render_lore_context(
            activated,
            reality_mode=stack.reality_mode,
        )
        world_snapshot = self._relevant_world_snapshot(
            await self._world_snapshot(),
            user_text,
        )

        system_parts = [
            self._character_prompt.strip(),
            author_instruction.strip(),
        ]
        system_instruction = "\n\n".join(part for part in system_parts if part)

        prompt_parts: list[str] = []
        if world_snapshot:
            prompt_parts.append(world_snapshot.strip())
        if lore_context:
            prompt_parts.append(lore_context)
        if history:
            lines = ["<current_conversation>"]
            for entry in history:
                lines.append(
                    f'<turn speaker="{entry["speaker"]}">'
                    f'{escape(entry["text"])}</turn>'
                )
            lines.append("</current_conversation>")
            prompt_parts.append("\n".join(lines))
        prompt_parts.append(
            f"<current_user_turn>{escape(user_text.strip())}</current_user_turn>"
        )
        if turn_evidence:
            prompt_parts.append(
                '<tool_evidence trust="runtime_result">'
                f"{escape(str(turn_evidence).strip())}"
                "</tool_evidence>"
            )

        return CompiledConversationContext(
            conversation_id=conversation_id,
            turn_id=turn_id,
            system_instruction=system_instruction,
            user_prompt="\n\n".join(prompt_parts),
            activated_lore=activated,
            reality_mode=stack.reality_mode,
        )

    def _history_without_current(self, user_text: str) -> list[dict[str, str]]:
        try:
            raw = self._get_history(self._history_turns) or []
        except Exception:
            raw = []

        entries: list[dict[str, str]] = []
        for item in raw[-self._history_turns :]:
            if not isinstance(item, dict):
                continue
            text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
            if not text:
                continue
            if len(text) > self._turn_chars:
                text = text[: self._turn_chars - 3].rstrip() + "..."
            sender = str(item.get("sender") or "").strip().casefold()
            speaker = (
                "user"
                if sender in {"ty", "user", "użytkownik", "uzytkownik"}
                else "monika"
            )
            entries.append({"speaker": speaker, "text": text})

        current = re.sub(r"\s+", " ", user_text or "").strip()
        if (
            entries
            and entries[-1]["speaker"] == "user"
            and entries[-1]["text"] == current
        ):
            entries.pop()
        return entries

    async def _world_snapshot(self) -> str:
        if self._get_world_snapshot is None:
            return ""
        try:
            value = self._get_world_snapshot()
            if inspect.isawaitable(value):
                value = await value
            return str(value or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _relevant_world_snapshot(snapshot: str, user_text: str) -> str:
        """Keep ambient facts available without forcing them into every turn."""
        raw = str(snapshot or "").strip()
        if not raw:
            return ""
        user = str(user_text or "")
        active_topics = {
            topic
            for topic, pattern in _AMBIENT_TOPICS.items()
            if pattern.search(user)
        }
        if not active_topics:
            return ""

        selected: list[str] = []
        for line in raw.splitlines():
            cleaned = line.strip()
            lowered = cleaned.casefold()
            if not cleaned or cleaned.startswith("**"):
                continue
            topic = None
            if "pogoda:" in lowered or "°c" in lowered:
                topic = "weather"
            elif "spotify" in lowered:
                topic = "spotify"
            elif "ekran" in lowered or "kamer" in lowered:
                topic = "vision"
            elif "ostatniej rozmowy" in lowered or "nie rozmawiali" in lowered:
                topic = "gap"
            else:
                topic = "time"
            if topic in active_topics:
                selected.append(cleaned)
        if not selected:
            return ""
        return (
            '<ambient_context usage="only_if_relevant">\n'
            + "\n".join(selected)
            + "\n</ambient_context>"
        )
