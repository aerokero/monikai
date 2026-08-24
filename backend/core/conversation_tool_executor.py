"""Core executors exposed to the provider-neutral conversation tool loop."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from backend.conversation.tools import (
    ConversationToolRequest,
    ConversationToolResult,
)


class CoreConversationToolExecutor:
    def __init__(
        self,
        *,
        reminder_manager,
        calendar_manager,
        notes_path,
        memory_engine,
        session_manager,
        spotify_manager,
        smart_home_executor,
        get_memory_db_path: Callable[[], object | None],
        get_time_context_fn: Callable[[], dict],
        get_personality: Callable[[], object | None],
        on_calendar_update: Callable[[list[dict]], object] | None = None,
    ):
        self._reminders = reminder_manager
        self._calendar = calendar_manager
        self._notes_path = notes_path
        self._memory = memory_engine
        self._sessions = session_manager
        self._spotify = spotify_manager
        self._smart_home = smart_home_executor
        self._get_memory_db_path = get_memory_db_path
        self._get_time_context = get_time_context_fn
        self._get_personality = get_personality
        self._on_calendar_update = on_calendar_update

    async def execute(
        self,
        request: ConversationToolRequest,
    ) -> ConversationToolResult:
        try:
            if request.name == "get_time_context":
                ctx = self._get_time_context()
                rendered = (
                    f"Local time: {ctx['iso']}\n"
                    f"Time zone: {ctx['timezone']} ({ctx['mode']})\n"
                    f"UTC offset: {ctx['offset']}"
                )
            elif request.name == "list_reminders":
                items = self._reminders.list()
                rendered = (
                    "No reminders scheduled."
                    if not items
                    else "Scheduled reminders:\n"
                    + "\n".join(
                        f"{item.id} | {item.when_iso} | {item.message}"
                        for item in items
                    )
                )
            elif request.name == "create_reminder":
                args = request.arguments
                reminder = self._reminders.create(
                    message=str(args.get("message") or "").strip(),
                    at=args.get("at"),
                    in_minutes=args.get("in_minutes"),
                    in_seconds=args.get("in_seconds"),
                    speak=bool(args.get("speak", True)),
                    alert=bool(args.get("alert", True)),
                )
                rendered = (
                    f"Reminder created. ID: {reminder.id}\n"
                    f"When: {reminder.when_iso}\n"
                    f"Message: {reminder.message}"
                )
            elif request.name == "cancel_reminder":
                reminder_id = str(request.arguments.get("id") or "").strip()
                if not reminder_id:
                    raise ValueError("Reminder ID is required.")
                cancelled = self._reminders.cancel(reminder_id)
                rendered = (
                    "Reminder cancelled."
                    if cancelled
                    else "Reminder not found."
                )
            elif request.name == "get_weather":
                personality = self._get_personality()
                if personality is None:
                    raise RuntimeError("Weather system not active.")
                await asyncio.to_thread(personality.update_weather, force=True)
                rendered = f"Current weather: {personality.state.weather}"
            elif request.name == "list_events":
                if self._calendar is None:
                    raise RuntimeError("Calendar manager not available.")
                events = self._calendar.list_events(
                    start_range_iso=str(
                        request.arguments.get("start_range_iso") or ""
                    ),
                    end_range_iso=str(
                        request.arguments.get("end_range_iso") or ""
                    ),
                )
                rendered = (
                    "No events found in that time range."
                    if not events
                    else "Found events:\n"
                    + "\n".join(
                        f"{event.id} | {event.start_iso} | {event.end_iso} | "
                        f"{event.summary}"
                        for event in events
                    )
                )
                if self._on_calendar_update:
                    self._on_calendar_update(
                        [event.__dict__ for event in events]
                    )
            elif request.name == "create_event":
                if self._calendar is None:
                    raise RuntimeError("Calendar manager not available.")
                args = request.arguments
                event = self._calendar.create_event(
                    summary=str(args.get("summary") or "").strip(),
                    start_iso=str(args.get("start_iso") or "").strip(),
                    end_iso=str(args.get("end_iso") or "").strip(),
                    description=args.get("description"),
                    all_day=bool(args.get("all_day", False)),
                )
                rendered = (
                    f"Event created. ID: {event.id}\n"
                    f"Start: {event.start_iso}\n"
                    f"End: {event.end_iso}\n"
                    f"Summary: {event.summary}"
                )
            elif request.name == "update_event":
                if self._calendar is None:
                    raise RuntimeError("Calendar manager not available.")
                event_id = str(request.arguments.get("event_id") or "").strip()
                summary = str(request.arguments.get("summary") or "").strip()
                if not event_id or not summary:
                    raise ValueError("event_id and summary are required.")
                updated = self._calendar.update_event(
                    event_id,
                    summary=summary,
                )
                rendered = (
                    "Event updated successfully."
                    if updated
                    else "Event not found with that ID."
                )
            elif request.name == "delete_event":
                if self._calendar is None:
                    raise RuntimeError("Calendar manager not available.")
                event_id = str(request.arguments.get("event_id") or "").strip()
                if not event_id:
                    raise ValueError("event_id is required.")
                deleted = self._calendar.delete_event(event_id)
                rendered = (
                    "Event deleted successfully."
                    if deleted
                    else "Event not found with that ID."
                )
            elif request.name == "notes_get":
                if self._notes_path is None:
                    raise RuntimeError("Notes storage not available.")
                if not self._notes_path.exists():
                    rendered = "(No notes saved.)"
                else:
                    rendered = (
                        self._notes_path.read_text(encoding="utf-8").strip()
                        or "(The notes file is currently empty.)"
                    )
            elif request.name == "notes_append":
                if self._notes_path is None:
                    raise RuntimeError("Notes storage not available.")
                content = str(request.arguments.get("content") or "").strip()
                if not content:
                    raise ValueError("Note content is required.")
                self._notes_path.parent.mkdir(parents=True, exist_ok=True)
                existing = (
                    self._notes_path.read_text(encoding="utf-8")
                    if self._notes_path.exists()
                    else ""
                )
                separator = "\n" if existing and not existing.endswith("\n") else ""
                with self._notes_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{separator}{content}\n")
                rendered = "Text appended to notes."
            elif request.name == "notes_set":
                if self._notes_path is None:
                    raise RuntimeError("Notes storage not available.")
                content = str(request.arguments.get("content") or "")
                self._notes_path.parent.mkdir(parents=True, exist_ok=True)
                self._notes_path.write_text(content, encoding="utf-8")
                rendered = "Notes have been replaced."
            elif request.name == "memory_search":
                from backend.soul.memory import store as memory_store

                query = str(request.arguments.get("query") or "").strip()
                if not query:
                    raise ValueError("Memory search query is required.")
                limit = max(
                    1,
                    min(10, int(request.arguments.get("limit", 5) or 5)),
                )
                results = await memory_store.search_fts(
                    query,
                    limit=limit,
                    db_path=self._get_memory_db_path(),
                )
                if not results:
                    rendered = "No memory entries found."
                else:
                    lines = []
                    for entry, _score in results:
                        when = entry.created_at.strftime("%Y-%m-%d")
                        lines.append(
                            f"[{entry.type}, {when}] {entry.content}"
                        )
                    rendered = "Memory results:\n" + "\n".join(lines)
            elif request.name == "recall_conversation":
                from backend.core import conversation_store

                if self._sessions is None:
                    raise RuntimeError("Conversation history is not available.")
                query = str(request.arguments.get("query") or "").strip()
                if not query:
                    raise ValueError("Conversation recall query is required.")
                limit = max(
                    1,
                    min(5, int(request.arguments.get("limit", 3) or 3)),
                )
                self._sessions.flush_current_session()
                hits = conversation_store.search_conversations(
                    self._sessions.sessions_dir,
                    query,
                    limit=limit,
                )
                current_id = self._sessions.get_current_session_id()
                hits = [hit for hit in hits if hit.get("id") != current_id]
                if not hits:
                    rendered = "No past conversation matched that query."
                else:
                    blocks = []
                    for hit in hits:
                        block = (
                            f"[{hit['day']}] "
                            f"{hit.get('title') or hit['id']} "
                            f"(channel: {hit.get('channel')})"
                        )
                        if hit.get("recap"):
                            block += f"\nSummary: {hit['recap']}"
                        if hit.get("excerpt"):
                            block += f"\nExcerpts:\n{hit['excerpt']}"
                        blocks.append(block)
                    rendered = "Past conversations found:\n\n" + "\n\n".join(
                        blocks
                    )
            elif request.name == "memory_add_entry":
                from backend.soul.memory import store as memory_store
                from backend.soul.models import MemoryEntry

                args = request.arguments
                raw_type = str(args.get("type") or "semantic").strip()
                if raw_type in {
                    "reflection",
                    "roleplay_scene",
                    "roleplay_insight",
                }:
                    memory_type, perspective = "episodic", "hers"
                elif raw_type in {"episodic", "event"}:
                    memory_type, perspective = "episodic", "factual"
                elif raw_type == "stm":
                    memory_type, perspective = "stm", "factual"
                else:
                    memory_type, perspective = "semantic", "factual"
                content = str(args.get("content") or "").strip()
                if not content:
                    raise ValueError("Memory content is required.")
                stability = str(args.get("stability") or "medium")
                importance = {
                    "low": 3.0,
                    "medium": 5.0,
                    "high": 7.0,
                }.get(stability, 5.0)
                if memory_type == "stm":
                    importance = min(importance, 3.0)
                session_id = (
                    self._sessions.get_current_session_id()
                    if self._sessions is not None
                    else None
                )
                tags = [
                    str(tag)
                    for tag in (args.get("tags") or [])
                    if isinstance(tag, str)
                ]
                if raw_type not in {"fact", "semantic", "episodic", "stm"}:
                    tags.append(raw_type)
                entry_id, status = await memory_store.add(
                    MemoryEntry(
                        id="pending",
                        type=memory_type,
                        content=content,
                        importance=importance,
                        perspective=perspective,
                        tags=tags,
                        entities=[
                            str(entity)
                            for entity in (args.get("entities") or [])
                            if isinstance(entity, str)
                        ],
                        source_session=session_id,
                    ),
                    db_path=self._get_memory_db_path(),
                )
                data = args.get("data") or {}
                birthday = data.get("date_of_birth") or data.get("birthday")
                if self._calendar is not None and isinstance(birthday, str):
                    parts = birthday.replace("/", "-").split("-")
                    if len(parts) == 3:
                        self._calendar.set_user_birthday(
                            int(parts[1]),
                            int(parts[2]),
                        )
                    elif len(parts) == 2:
                        self._calendar.set_user_birthday(
                            int(parts[0]),
                            int(parts[1]),
                        )
                rendered = f"{status}: {entry_id}"
            elif request.name == "memory_get_page":
                if self._memory is None:
                    raise RuntimeError("Memory pages are not available.")
                base = Path(self._memory.pages_dir).resolve()
                raw = Path(str(request.arguments.get("path") or ""))
                candidate = (
                    raw.resolve()
                    if raw.is_absolute()
                    else (base / raw).resolve()
                )
                try:
                    candidate.relative_to(base)
                except ValueError as exc:
                    raise ValueError(
                        "Memory page path escapes memory/pages."
                    ) from exc
                rendered = (
                    candidate.read_text(encoding="utf-8", errors="ignore")
                    if candidate.is_file()
                    else "(Memory page not found.)"
                )
            elif request.name == "memory_create_page":
                if self._memory is None:
                    raise RuntimeError("Memory pages are not available.")
                title = str(request.arguments.get("title") or "").strip()
                if not title:
                    raise ValueError("Memory page title is required.")
                path = self._memory.create_page(
                    title=title,
                    folder=str(
                        request.arguments.get("folder") or "topics"
                    ),
                    tags=[
                        str(tag)
                        for tag in (request.arguments.get("tags") or [])
                        if isinstance(tag, str)
                    ],
                )
                rendered = f"Created memory page: {path}"
            elif request.name == "memory_append_page":
                if self._memory is None:
                    raise RuntimeError("Memory pages are not available.")
                path = str(request.arguments.get("path") or "").strip()
                content = str(
                    request.arguments.get("content") or ""
                ).strip()
                if not path or not content:
                    raise ValueError("Memory page path and content are required.")
                final_path = self._memory.append_page(
                    path=path,
                    content=content,
                )
                rendered = f"Appended to memory page: {final_path}"
            elif request.name == "spotify_get_status":
                if self._spotify is None:
                    raise RuntimeError("Spotify manager unavailable.")
                status = await asyncio.to_thread(self._spotify.status)
                rendered = json.dumps(status, ensure_ascii=False)
            elif request.name == "spotify_get_now_playing":
                if self._spotify is None:
                    raise RuntimeError("Spotify manager unavailable.")
                now_playing = await asyncio.to_thread(
                    self._spotify.get_now_playing
                )
                rendered = json.dumps(now_playing, ensure_ascii=False)
            elif request.name == "spotify_list_playlists":
                if self._spotify is None:
                    raise RuntimeError("Spotify manager unavailable.")
                limit = max(
                    1,
                    min(50, int(request.arguments.get("limit", 20) or 20)),
                )
                playlists = await asyncio.to_thread(
                    self._spotify.list_playlists,
                    limit,
                )
                rendered = json.dumps(playlists, ensure_ascii=False)
            elif request.name == "spotify_recently_played":
                if self._spotify is None:
                    raise RuntimeError("Spotify manager unavailable.")
                limit = max(
                    1,
                    min(50, int(request.arguments.get("limit", 20) or 20)),
                )
                recent = await asyncio.to_thread(
                    self._spotify.recently_played,
                    limit,
                )
                rendered = json.dumps(recent, ensure_ascii=False)
            elif request.name in {"list_smart_devices", "control_light"}:
                if self._smart_home is None:
                    raise RuntimeError("Smart-home system unavailable.")
                return await self._smart_home.execute(request)
            else:
                return ConversationToolResult(
                    name=request.name,
                    result="Unsupported conversation tool.",
                    ok=False,
                )
            return ConversationToolResult(
                name=request.name,
                result=rendered,
                ok=True,
            )
        except Exception as exc:
            return ConversationToolResult(
                name=request.name,
                result=str(exc),
                ok=False,
            )
