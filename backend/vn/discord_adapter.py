from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import discord

from backend.core import monikai

logger = logging.getLogger(__name__)


class DiscordChatSession:
    """Manages an active Monika text session for a single Discord channel."""

    def __init__(
        self,
        channel_id: int,
        channel_label: str,
        settings_getter: Callable[[], Dict[str, Any]],
        *,
        calendar_manager=None,
        reminder_manager=None,
        spotify_manager=None,
        personality=None,
    ):
        self.channel_id = int(channel_id)
        self.channel_label = str(channel_label or f"discord:{channel_id}")
        self.settings_getter = settings_getter
        self.calendar_manager = calendar_manager
        self.reminder_manager = reminder_manager
        self.spotify_manager = spotify_manager
        self.personality = personality
        self.audio_loop = None
        self.run_task = None
        self.lock = asyncio.Lock()
        self.last_activity_ts = time.monotonic()

    async def ensure_started(self):
        if self.audio_loop and self.run_task and not self.run_task.done():
            return

        self.audio_loop = monikai.AudioLoop(
            video_mode="none",
            calendar_manager=self.calendar_manager,
            reminder_manager=self.reminder_manager,
            spotify_manager=self.spotify_manager,
            personality=self.personality,
            enable_audio_io=False,
            auto_allow_tools_without_confirmation=False,
        )
        self.audio_loop.update_permissions((self.settings_getter() or {}).get("tool_permissions") or {})
        self.run_task = asyncio.create_task(
            self.audio_loop.run(
                start_message=(
                    "System Notification: You are chatting with the user over Discord text messages. "
                    "Respond in plain text only. Keep replies concise by default. "
                    "On Discord, you may sound a little more casual, warm, and playful, "
                    "if it feels natural for the moment. Keep that text style consistent. "
                    "Reply in the user's current language by default. "
                    "Prefer short, natural replies. "
                    "Do not imply that you can see images or hear audio unless the user explicitly sends them."
                )
            )
        )
        await self.audio_loop.wait_until_ready(25.0)

    async def ask(self, text: str) -> str:
        async with self.lock:
            await self.ensure_started()
            self.last_activity_ts = time.monotonic()
            reply = await self.audio_loop.submit_text_turn(text, timeout_sec=120.0)
            self.last_activity_ts = time.monotonic()
            return reply

    async def stop(self):
        if self.audio_loop:
            self.audio_loop.stop()
        if self.run_task and not self.run_task.done():
            self.run_task.cancel()
            try:
                await self.run_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self.run_task = None
        self.audio_loop = None

    def is_active(self) -> bool:
        return bool(self.audio_loop and self.run_task and not self.run_task.done())

    def get_status_summary(self) -> str:
        active = self.is_active()
        last_age = max(0, int(time.monotonic() - self.last_activity_ts))
        return (
            f"Sesja Discord: {'aktywna' if active else 'nieaktywna'}\n"
            f"Kanał: {self.channel_id}\n"
            f"Ostatnia aktywność: {last_age}s temu"
        )

    def get_mood_summary(self) -> str:
        state = getattr(getattr(self, "personality", None), "state", None)
        if not state:
            return "Nie mam teraz aktywnego nastroju."
        affection = max(0.0, min(100.0, float(getattr(state, "affection", 0.0) or 0.0)))
        energy = max(0.0, min(1.0, float(getattr(state, "energy", 0.0) or 0.0)))
        mood = str(getattr(state, "mood", "neutral") or "neutral")
        return (
            f"Nastrój: {mood}\n"
            f"Energia: {int(round(energy * 100))}%\n"
            f"Bliskość: {affection:.1f}/100"
        )

    def get_memory_summary(self, limit: int = 5) -> str:
        engine = getattr(self.audio_loop, "memory_engine", None) if self.audio_loop else None
        if not engine:
            return "Pamięć nie jest teraz dostępna."
        items = engine.list_recent(limit=max(1, min(int(limit or 5), 10)))
        if not items:
            return "Nie mam jeszcze zapisanych wpisów pamięci."
        lines = ["Ostatnie wpisy pamięci:"]
        for item in items:
            content = str(item.get("content") or "").strip().replace("\n", " ")
            if len(content) > 140:
                content = content[:137].rstrip() + "..."
            lines.append(f"- [{item.get('type')}] {content} (id={item.get('id')})")
        return "\n".join(lines)

    def forget_last_memory(self) -> str:
        engine = getattr(self.audio_loop, "memory_engine", None) if self.audio_loop else None
        if not engine:
            return "Pamięć nie jest teraz dostępna."
        items = engine.list_recent(limit=10)
        if not items:
            return "Nie mam czego usuwać z pamięci."
        target = items[0]
        status = engine.update_entry(str(target.get("id") or ""), {"status": "archived"})
        if status != "ok":
            return f"Nie udało się usunąć wpisu: {status}"
        content = str(target.get("content") or "").strip().replace("\n", " ")
        if len(content) > 120:
            content = content[:117].rstrip() + "..."
        return f"Usunęłam ostatni wpis pamięci: [{target.get('type')}] {content}"

    def get_note_page(self, selector: str, max_chars: int = 2200) -> str:
        if not self.audio_loop:
            return "Notatki nie są teraz dostępne."
        engine = getattr(self.audio_loop, "memory_engine", None)
        if not engine:
            return "Notatki nie są teraz dostępne."
        resolved = self._resolve_note_selector(selector)
        if not resolved:
            return "Nie znalazłam takiej notatki. Użyj !notes, żeby zobaczyć listę."
        try:
            content = engine.get_page(resolved).strip()
        except Exception as exc:
            return f"Nie udało się odczytać notatki: {exc}"
        if not content:
            return f"Strona {resolved} jest pusta."
        if len(content) > max_chars:
            content = content[: max(0, max_chars - 3)].rstrip() + "..."
        return f"[{resolved}]\n\n{content}"

    def list_notes_catalog(self, limit: int = 24) -> str:
        paths = self._list_note_pages(limit=limit)
        if not paths:
            return "Nie mam jeszcze żadnych stron notatek."
        lines = ["Dostępne notatki/strony:", *[f"- {path}" for path in paths]]
        lines.append("")
        lines.append("Użycie:")
        lines.append("!notes <ścieżka> - pokaż stronę")
        lines.append("!notes add <tekst> - dopisz do notes.md")
        lines.append("!notes add <ścieżka> | <tekst> - dopisz do wybranej strony")
        return "\n".join(lines)

    def _resolve_note_selector(self, selector: str) -> Optional[str]:
        raw = str(selector or "").strip().replace("\\", "/").lstrip("/")
        if not raw:
            return "notes.md"
        aliases = {
            "global": "notes.md",
            "notes": "notes.md",
            "notes.md": "notes.md",
        }
        lowered = raw.lower()
        if lowered in aliases:
            return aliases[lowered]

        pages = self._list_note_pages(limit=200)
        lookup = {path.lower(): path for path in pages}
        if lowered in lookup:
            return lookup[lowered]
        if not lowered.endswith(".md") and f"{lowered}.md" in lookup:
            return lookup[f"{lowered}.md"]

        basename_matches = [path for path in pages if Path(path).name.lower() in {lowered, f"{lowered}.md"}]
        if len(basename_matches) == 1:
            return basename_matches[0]
        return None

    def _list_note_pages(self, limit: int = 24) -> List[str]:
        engine = getattr(self.audio_loop, "memory_engine", None) if self.audio_loop else None
        pages_dir = getattr(engine, "pages_dir", None)
        if not pages_dir:
            return []
        try:
            pages_path = Path(pages_dir).resolve()
            if not pages_path.exists():
                return []
            paths: List[str] = []
            for path in sorted(pages_path.rglob("*.md")):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(pages_path).as_posix()
                except Exception:
                    rel = path.name
                paths.append(rel)
            return paths[: max(1, min(int(limit or 24), 100))]
        except Exception:
            return []

    def append_notes(self, text: str) -> str:
        if not self.audio_loop:
            return "Notatki nie są teraz dostępne."
        notes_path = getattr(self.audio_loop, "notes_path", None)
        if not notes_path:
            return "Notatki nie są teraz dostępne."
        payload = str(text or "").strip()
        if not payload:
            return "Podaj tekst do dopisania, np. !notes add kupić herbatę"
        try:
            existing_size = notes_path.stat().st_size if notes_path.exists() else 0
            with notes_path.open("a", encoding="utf-8") as handle:
                if existing_size > 0:
                    handle.write("\n")
                handle.write(payload)
        except Exception as exc:
            return f"Nie udało się dopisać notatki: {exc}"
        return "Dopisałam to do notatek."

    def append_note_page(self, selector: str, text: str) -> str:
        if not self.audio_loop:
            return "Notatki nie są teraz dostępne."
        engine = getattr(self.audio_loop, "memory_engine", None)
        if not engine:
            return "Notatki nie są teraz dostępne."
        payload = str(text or "").strip()
        if not payload:
            return "Podaj tekst do dopisania."
        resolved = self._resolve_note_selector(selector)
        if not resolved:
            return "Nie znalazłam takiej notatki. Użyj !notes, żeby zobaczyć listę."
        try:
            engine.append_page(resolved, payload)
        except Exception as exc:
            return f"Nie udało się dopisać do notatki: {exc}"
        return f"Dopisałam to do {resolved}."

    def create_reminder_from_command(self, args: str) -> str:
        if not self.reminder_manager:
            return "Przypomnienia nie są teraz dostępne."
        raw = str(args or "").strip()
        if not raw or "|" not in raw:
            return (
                "Użycie:\n"
                "!remind zadzwoń do mamy | 45m\n"
                "!remind wyjść z psem | 2026-03-15 18:30"
            )
        message, when_raw = [part.strip() for part in raw.split("|", 1)]
        if not message or not when_raw:
            return (
                "Użycie:\n"
                "!remind zadzwoń do mamy | 45m\n"
                "!remind wyjść z psem | 2026-03-15 18:30"
            )
        try:
            from datetime import datetime
            if when_raw.lower().endswith("m") and when_raw[:-1].strip().isdigit():
                reminder = self.reminder_manager.create(message=message, in_minutes=int(when_raw[:-1].strip()))
            elif when_raw.lower().endswith("s") and when_raw[:-1].strip().isdigit():
                reminder = self.reminder_manager.create(message=message, in_seconds=int(when_raw[:-1].strip()))
            else:
                datetime.strptime(when_raw, "%Y-%m-%d %H:%M")
                reminder = self.reminder_manager.create(message=message, at=when_raw)
        except Exception as exc:
            return f"Nie udało się utworzyć przypomnienia: {exc}"
        return f"Ustawiłam przypomnienie na {reminder.when_iso}: {reminder.message}"


class DiscordChannelAdapter(discord.Client):
    """Phase 6: Discord Channel Integration.

    Connects Discord messages to the Soul Engine's Event Bus and V2Runtime.
    """

    def __init__(
        self,
        token: str,
        settings_getter: Callable[[], Dict[str, Any]],
        *,
        calendar_manager=None,
        reminder_manager=None,
        spotify_manager=None,
        personality=None,
        allowed_channel_ids: list[int] = None,
        session_idle_sec: float = 1800.0,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self.token = token
        self.settings_getter = settings_getter
        self.calendar_manager = calendar_manager
        self.reminder_manager = reminder_manager
        self.spotify_manager = spotify_manager
        self.personality = personality
        self.allowed_channel_ids = allowed_channel_ids or []
        self.session_idle_sec = max(300.0, float(session_idle_sec or 1800.0))

        self._sessions: Dict[int, DiscordChatSession] = {}
        self._sessions_lock = asyncio.Lock()
        self.cleanup_task = None

    async def setup_hook(self) -> None:
        self.cleanup_task = asyncio.create_task(self._cleanup_idle_sessions())
        logger.info("[Discord] Setup hook complete.")

    async def on_ready(self) -> None:
        logger.info(f"[Discord] Logged in as {self.user} (ID: {self.user.id})")

    async def on_message(self, message: discord.Message) -> None:
        # Ignore our own messages
        if message.author == self.user:
            return

        # Ignore messages in unauthorized channels (to preserve privacy)
        is_dm = isinstance(message.channel, discord.DMChannel) or type(message.channel).__name__ == "DMChannel"
        if not is_dm and self.allowed_channel_ids and message.channel.id not in self.allowed_channel_ids:
            return

        text = message.content.strip()
        if not text:
            return

        # Check if we are mentioned or if it is a command
        is_mention, text_after_mention = self._parse_mention(text)
        is_command = text.startswith("!")

        if not is_mention and not is_command:
            # Check if this channel has an active session, otherwise ignore general chatter
            # Unless we are in a DM channel where all messages are directed to the bot
            if not is_dm and message.channel.id not in self._sessions:
                return

        # Use the cleaned text if we were mentioned
        raw_input = text_after_mention if is_mention else text

        command, args = self._parse_command(raw_input)
        chat_id = message.channel.id
        channel_label = getattr(message.channel, "name", f"discord:{chat_id}")

        try:
            if command:
                if command == "start":
                    await message.channel.send(
                        "Monika jest gotowa na Discordzie.\n\n"
                        "Komendy:\n"
                        "!help\n!reset\n!status\n!mood\n!memory\n!forget\n!notes\n!remind"
                    )
                    return
                elif command == "help":
                    await message.channel.send(
                        "Dostępne komendy:\n"
                        "!start - start sesji Discord\n"
                        "!help - lista komend\n"
                        "!reset - reset sesji Discord\n"
                        "!status - status sesji\n"
                        "!mood - nastrój Moniki\n"
                        "!memory - ostatnie wpisy pamięci\n"
                        "!forget - usuń ostatni wpis pamięci\n"
                        "!notes - lista notatek i stron\n"
                        "!notes <ścieżka> - pokaż wybraną notatkę\n"
                        "!notes add <tekst> - dopisz do notes.md\n"
                        "!notes add <ścieżka> | <tekst> - dopisz do wybranej strony\n"
                        "!remind <wiadomość> | 45m\n"
                        "!remind <wiadomość> | 2026-03-15 18:30"
                    )
                    return
                elif command == "reset":
                    await self._drop_session(chat_id)
                    await message.channel.send("Zresetowałam bieżącą sesję Discord.")
                    return
                elif command == "status":
                    session = await self._peek_session(chat_id)
                    if not session:
                        await message.channel.send(f"Sesja: nieaktywna\nKanał: {chat_id}\nOstatnia aktywność: brak")
                    else:
                        await message.channel.send(session.get_status_summary())
                    return
                elif command == "mood":
                    session = await self._get_session(chat_id, channel_label)
                    await session.ensure_started()
                    await message.channel.send(session.get_mood_summary())
                    return
                elif command == "memory":
                    session = await self._get_session(chat_id, channel_label)
                    await session.ensure_started()
                    await message.channel.send(session.get_memory_summary())
                    return
                elif command == "forget":
                    session = await self._get_session(chat_id, channel_label)
                    await session.ensure_started()
                    await message.channel.send(session.forget_last_memory())
                    return
                elif command == "notes":
                    session = await self._get_session(chat_id, channel_label)
                    await session.ensure_started()
                    if not args:
                        await message.channel.send(session.list_notes_catalog())
                    elif args.lower().startswith("add "):
                        payload = args[4:].strip()
                        if "|" in payload:
                            selector, note_text = [part.strip() for part in payload.split("|", 1)]
                            await message.channel.send(session.append_note_page(selector, note_text))
                        else:
                            await message.channel.send(session.append_notes(payload))
                    else:
                        await message.channel.send(session.get_note_page(args))
                    return
                elif command == "remind":
                    session = await self._get_session(chat_id, channel_label)
                    await session.ensure_started()
                    await message.channel.send(session.create_reminder_from_command(args))
                    return

            # Normal chat processing
            session = await self._get_session(chat_id, channel_label)
            async with message.channel.typing():
                reply = await session.ask(raw_input)
                if reply:
                    await message.channel.send(reply)

        except Exception as e:
            logger.error(f"[Discord] Error processing message: {e}", exc_info=True)
            await message.channel.send("*Napotkałam problem z odpowiedzią. Daj mi chwilę.*")

    def _parse_mention(self, text: str) -> Tuple[bool, str]:
        if not self.user:
            return False, text
        bot_mention = f"<@!{self.user.id}>"
        bot_mention_alt = f"<@{self.user.id}>"
        raw = text.strip()
        if raw.startswith(bot_mention):
            return True, raw[len(bot_mention):].strip()
        if raw.startswith(bot_mention_alt):
            return True, raw[len(bot_mention_alt):].strip()
        return False, text

    def _parse_command(self, text: str) -> Tuple[str, str]:
        raw = str(text or "").strip()
        if not raw.startswith("!"):
            return "", raw
        head, _, rest = raw.partition(" ")
        command = head[1:].strip().lower()
        return command, rest.strip()

    async def _get_session(self, chat_id: int, channel_label: str) -> DiscordChatSession:
        async with self._sessions_lock:
            session = self._sessions.get(chat_id)
            if session:
                return session
            session = DiscordChatSession(
                chat_id,
                channel_label,
                self.settings_getter,
                calendar_manager=self.calendar_manager,
                reminder_manager=self.reminder_manager,
                spotify_manager=self.spotify_manager,
                personality=self.personality,
            )
            self._sessions[chat_id] = session
            return session

    async def _peek_session(self, chat_id: int) -> Optional[DiscordChatSession]:
        async with self._sessions_lock:
            return self._sessions.get(chat_id)

    async def _drop_session(self, chat_id: int):
        async with self._sessions_lock:
            session = self._sessions.pop(chat_id, None)
        if session:
            await session.stop()

    async def _cleanup_idle_sessions(self):
        while True:
            await asyncio.sleep(60.0)
            now = time.monotonic()
            stale_ids = []
            async with self._sessions_lock:
                for chat_id, session in self._sessions.items():
                    if (now - session.last_activity_ts) > self.session_idle_sec:
                        stale_ids.append(chat_id)
            for chat_id in stale_ids:
                await self._drop_session(chat_id)

    async def start_bot(self):
        try:
            # Note: client.start() is a blocking coroutine, so it should be run in a task
            await self.start(self.token)
        except Exception as e:
            logger.error(f"[Discord] Failed to start bot: {e}")

    async def stop_bot(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
        await self.close()