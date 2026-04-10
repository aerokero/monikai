import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core import monikai


TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_TRANSCRIBE_MODEL = os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-2.5-flash")
TELEGRAM_COMMANDS = [
    {"command": "start", "description": "Start rozmowy z Moniką"},
    {"command": "help", "description": "Pokaż listę komend"},
    {"command": "reset", "description": "Zresetuj bieżącą sesję"},
    {"command": "status", "description": "Pokaż status sesji"},
    {"command": "memory", "description": "Pokaż ostatnie wpisy pamięci"},
    {"command": "forget", "description": "Usuń ostatni wpis pamięci"},
    {"command": "mood", "description": "Pokaż nastrój Moniki"},
    {"command": "notes", "description": "Pokaż lub dopisz do notatek"},
    {"command": "remind", "description": "Utwórz przypomnienie"},
]


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class TelegramChatSession:
    def __init__(
        self,
        chat_id: int,
        user_label: str,
        settings_getter: Callable[[], Dict[str, Any]],
        *,
        calendar_manager=None,
        reminder_manager=None,
        spotify_manager=None,
        personality=None,
    ):
        self.chat_id = int(chat_id)
        self.user_label = str(user_label or f"telegram:{chat_id}")
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
                    "System Notification: You are chatting with the user over Telegram text messages. "
                    "Respond in plain text only. Keep replies concise by default. "
                    "On Telegram, you may sound a little more casual, warm, lowercase and playful than in voice mode, "
                    "if it feels natural for the moment. Keep that text style consistent across messages instead of "
                    "swinging between tweet-like casual and generic assistant phrasing. "
                    "Reply in the user's current language by default, and switch languages naturally if the user does. "
                    "Prefer short, natural replies. Avoid forced holiday mentions, forced cleverness, support-tone phrasing, "
                    "and random foreign insertions that do not sound organic in the current language. "
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

    async def ask_with_attachments(
        self,
        text: Optional[str],
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        async with self.lock:
            await self.ensure_started()
            self.last_activity_ts = time.monotonic()
            reply = await self.audio_loop.submit_user_turn(
                text=text,
                attachments=attachments or [],
                timeout_sec=120.0,
            )
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
            f"Sesja: {'aktywna' if active else 'nieaktywna'}\n"
            f"Czat: {self.chat_id}\n"
            f"Ostatnia aktywność: {last_age}s temu"
        )

    def get_mood_summary(self) -> str:
        state = getattr(getattr(self, "personality", None), "state", None)
        if not state:
            return "Nie mam teraz aktywnego statusu nastroju."
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
            return "Nie mam jeszcze zapisanych świeżych wpisów pamięci."
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
            return f"Nie udało się usunąć wpisu pamięci: {status}"
        content = str(target.get("content") or "").strip().replace("\n", " ")
        if len(content) > 120:
            content = content[:117].rstrip() + "..."
        return f"Usunęłam ostatni wpis pamięci: [{target.get('type')}] {content}"

    def get_notes_text(self, max_chars: int = 1800) -> str:
        if not self.audio_loop:
            return "Notatki nie są teraz dostępne."
        notes_path = getattr(self.audio_loop, "notes_path", None)
        if not notes_path:
            return "Notatki nie są teraz dostępne."
        try:
            if not notes_path.exists():
                notes_path.write_text("", encoding="utf-8")
            content = notes_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            return f"Nie udało się odczytać notatek: {exc}"
        if not content:
            return "Notatki są puste."
        if len(content) > max_chars:
            content = content[: max(0, max_chars - 3)].rstrip() + "..."
        return content

    def _pages_dir(self) -> Optional[Path]:
        engine = getattr(self.audio_loop, "memory_engine", None) if self.audio_loop else None
        pages_dir = getattr(engine, "pages_dir", None)
        if not pages_dir:
            return None
        try:
            return Path(pages_dir).resolve()
        except Exception:
            return None

    def _list_note_pages(self, limit: int = 24) -> List[str]:
        pages_dir = self._pages_dir()
        if not pages_dir or not pages_dir.exists():
            return []
        paths: List[str] = []
        for path in sorted(pages_dir.rglob("*.md")):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(pages_dir).as_posix()
            except Exception:
                rel = path.name
            paths.append(rel)
        return paths[: max(1, min(int(limit or 24), 100))]

    def list_notes_catalog(self, limit: int = 24) -> str:
        paths = self._list_note_pages(limit=limit)
        if not paths:
            return "Nie mam jeszcze żadnych stron notatek."
        lines = ["Dostępne notatki/strony:", *[f"- {path}" for path in paths]]
        lines.append("")
        lines.append("Użycie:")
        lines.append("/notes <ścieżka> - pokaż stronę")
        lines.append("/notes add <tekst> - dopisz do notes.md")
        lines.append("/notes add <ścieżka> | <tekst> - dopisz do wybranej strony")
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

    def get_note_page(self, selector: str, max_chars: int = 2200) -> str:
        if not self.audio_loop:
            return "Notatki nie są teraz dostępne."
        engine = getattr(self.audio_loop, "memory_engine", None)
        if not engine:
            return "Notatki nie są teraz dostępne."
        resolved = self._resolve_note_selector(selector)
        if not resolved:
            return "Nie znalazłam takiej notatki. Użyj /notes, żeby zobaczyć listę."
        try:
            content = engine.get_page(resolved).strip()
        except Exception as exc:
            return f"Nie udało się odczytać notatki: {exc}"
        if not content:
            return f"Strona {resolved} jest pusta."
        if len(content) > max_chars:
            content = content[: max(0, max_chars - 3)].rstrip() + "..."
        return f"[{resolved}]\n\n{content}"

    def append_notes(self, text: str) -> str:
        if not self.audio_loop:
            return "Notatki nie są teraz dostępne."
        notes_path = getattr(self.audio_loop, "notes_path", None)
        if not notes_path:
            return "Notatki nie są teraz dostępne."
        payload = str(text or "").strip()
        if not payload:
            return "Podaj tekst do dopisania, np. /notes kupić herbatę"
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
            return "Nie znalazłam takiej notatki. Użyj /notes, żeby zobaczyć listę."
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
                "/remind zadzwoń do mamy | 45m\n"
                "/remind wyjść z psem | 2026-03-15 18:30"
            )
        message, when_raw = [part.strip() for part in raw.split("|", 1)]
        if not message or not when_raw:
            return (
                "Użycie:\n"
                "/remind zadzwoń do mamy | 45m\n"
                "/remind wyjść z psem | 2026-03-15 18:30"
            )
        try:
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


class TelegramBotService:
    def __init__(
        self,
        token: str,
        settings_getter: Callable[[], Dict[str, Any]],
        *,
        calendar_manager=None,
        reminder_manager=None,
        spotify_manager=None,
        personality=None,
        allowed_chat_id: Optional[int] = None,
        allowed_chat_ids: Optional[List[int]] = None,
        allow_groups: bool = False,
        session_idle_sec: float = 1800.0,
    ):
        self.token = str(token or "").strip()
        self.settings_getter = settings_getter
        self.calendar_manager = calendar_manager
        self.reminder_manager = reminder_manager
        self.spotify_manager = spotify_manager
        self.personality = personality
        normalized_ids = set()
        if allowed_chat_id is not None:
            normalized_ids.add(int(allowed_chat_id))
        for item in allowed_chat_ids or []:
            if item is None:
                continue
            normalized_ids.add(int(item))
        self.allowed_chat_ids = normalized_ids
        self.allow_groups = bool(allow_groups)
        self.session_idle_sec = max(300.0, float(session_idle_sec or 1800.0))
        self._offset = 0
        self._stop_event = asyncio.Event()
        self._sessions: Dict[int, TelegramChatSession] = {}
        self._sessions_lock = asyncio.Lock()
        self._bot_username = ""

    @classmethod
    def from_env(
        cls,
        settings_getter: Callable[[], Dict[str, Any]],
        *,
        calendar_manager=None,
        reminder_manager=None,
        spotify_manager=None,
        personality=None,
    ):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return None
        raw_allowed = str(os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "")).strip()
        allowed_chat_id = int(raw_allowed) if raw_allowed else None
        raw_allowed_list = str(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")).strip()
        allowed_chat_ids: List[int] = []
        if raw_allowed_list:
            for part in raw_allowed_list.split(","):
                chunk = str(part or "").strip()
                if not chunk:
                    continue
                try:
                    allowed_chat_ids.append(int(chunk))
                except Exception:
                    continue
        try:
            session_idle_sec = float(os.getenv("TELEGRAM_SESSION_IDLE_SEC", "1800"))
        except Exception:
            session_idle_sec = 1800.0
        return cls(
            token,
            settings_getter,
            calendar_manager=calendar_manager,
            reminder_manager=reminder_manager,
            spotify_manager=spotify_manager,
            personality=personality,
            allowed_chat_id=allowed_chat_id,
            allowed_chat_ids=allowed_chat_ids,
            allow_groups=_env_flag("TELEGRAM_ALLOW_GROUPS", False),
            session_idle_sec=session_idle_sec,
        )

    async def _api_call(self, method: str, payload: Optional[Dict[str, Any]] = None, timeout_sec: float = 35.0) -> Dict[str, Any]:
        url = f"{TELEGRAM_API_BASE}/bot{self.token}/{method}"
        body = json.dumps(payload or {}).encode("utf-8")

        def _do_request():
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=max(5.0, float(timeout_sec or 35.0))) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8"))

        try:
            data = await asyncio.to_thread(_do_request)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Telegram API HTTP {exc.code}: {detail or exc.reason}") from exc
        except Exception as exc:
            raise RuntimeError(f"Telegram API request failed: {exc}") from exc

        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data

    async def _send_message(self, chat_id: int, text: str):
        message = str(text or "").strip() or "..."
        chunks = []
        while message:
            chunks.append(message[:TELEGRAM_MESSAGE_LIMIT])
            message = message[TELEGRAM_MESSAGE_LIMIT:]
        for chunk in chunks or ["..."]:
            await self._api_call("sendMessage", {"chat_id": chat_id, "text": chunk})

    async def _register_bot_metadata(self):
        try:
            me = await self._api_call("getMe", {}, timeout_sec=15.0)
            result = me.get("result") or {}
            self._bot_username = str(result.get("username") or "").strip()
        except Exception:
            self._bot_username = ""
        try:
            await self._api_call("setMyCommands", {"commands": TELEGRAM_COMMANDS}, timeout_sec=15.0)
        except Exception as exc:
            print(f"[TELEGRAM] Failed to register commands: {exc}")

    def _parse_command(self, text: str) -> Tuple[str, str]:
        raw = str(text or "").strip()
        if not raw.startswith("/"):
            return "", raw
        head, _, rest = raw.partition(" ")
        command = head[1:].strip()
        if "@" in command:
            cmd_name, _, cmd_target = command.partition("@")
            if self._bot_username and cmd_target.lower() != self._bot_username.lower():
                return "", raw
            command = cmd_name
        return command.lower(), rest.strip()

    def _is_chat_allowed(self, chat_id: int, chat_type: str) -> bool:
        if chat_type != "private" and not self.allow_groups:
            return False
        if self.allowed_chat_ids and int(chat_id) not in self.allowed_chat_ids:
            return False
        return True

    async def _send_typing(self, chat_id: int):
        try:
            await self._api_call("sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout_sec=10.0)
        except Exception:
            pass

    async def _download_telegram_file(self, file_path: str) -> bytes:
        url = f"{TELEGRAM_API_BASE}/file/bot{self.token}/{file_path}"

        def _do_request():
            with urllib.request.urlopen(url, timeout=25.0) as resp:
                return resp.read()

        try:
            return await asyncio.to_thread(_do_request)
        except Exception as exc:
            raise RuntimeError(f"Failed to download Telegram file: {exc}") from exc

    async def _transcribe_audio_bytes(self, raw: bytes, mime_type: str) -> str:
        payload = bytes(raw or b"")
        if not payload:
            return ""
        prompt = (
            "Transcribe this Telegram voice note as plain text. "
            "Preserve the original language. "
            "Do not add commentary, labels, quotes, timestamps, or markdown. "
            "If the audio is unintelligible, return an empty string."
        )
        try:
            response = await monikai.client.aio.models.generate_content(
                model=TELEGRAM_TRANSCRIBE_MODEL,
                contents=[
                    prompt,
                    monikai.types.Part.from_bytes(data=payload, mime_type=mime_type),
                ],
            )
        except Exception as exc:
            raise RuntimeError(f"Voice note transcription failed: {exc}") from exc
        text = str(getattr(response, "text", "") or "").strip()
        if text.lower() in {"", "unintelligible", "[unintelligible]"}:
            return ""
        return text

    async def _build_message_attachments(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        attachments: List[Dict[str, Any]] = []

        photos = message.get("photo") or []
        if isinstance(photos, list) and photos:
            best_photo = photos[-1]
            file_id = str(best_photo.get("file_id") or "").strip()
            if file_id:
                file_meta = await self._api_call("getFile", {"file_id": file_id}, timeout_sec=20.0)
                file_path = str((file_meta.get("result") or {}).get("file_path") or "").strip()
                if file_path:
                    raw = await self._download_telegram_file(file_path)
                    attachments.append(
                        {
                            "name": f"{file_id}.jpg",
                            "mime_type": "image/jpeg",
                            "data": base64.b64encode(raw).decode("utf-8"),
                            "size": len(raw),
                        }
                    )

        document = message.get("document") or {}
        mime_type = str(document.get("mime_type") or "").strip().lower()
        if document and mime_type.startswith("image/"):
            file_id = str(document.get("file_id") or "").strip()
            if file_id:
                file_meta = await self._api_call("getFile", {"file_id": file_id}, timeout_sec=20.0)
                file_path = str((file_meta.get("result") or {}).get("file_path") or "").strip()
                if file_path:
                    raw = await self._download_telegram_file(file_path)
                    attachments.append(
                        {
                            "name": str(document.get("file_name") or f"{file_id}.bin"),
                            "mime_type": mime_type or "application/octet-stream",
                            "data": base64.b64encode(raw).decode("utf-8"),
                            "size": len(raw),
                        }
                    )

        return attachments

    async def _build_audio_transcript(self, message: Dict[str, Any]) -> str:
        voice = message.get("voice") or {}
        if voice:
            file_id = str(voice.get("file_id") or "").strip()
            if file_id:
                file_meta = await self._api_call("getFile", {"file_id": file_id}, timeout_sec=20.0)
                file_path = str((file_meta.get("result") or {}).get("file_path") or "").strip()
                if file_path:
                    raw = await self._download_telegram_file(file_path)
                    mime_type = str(voice.get("mime_type") or "audio/ogg").strip() or "audio/ogg"
                    return await self._transcribe_audio_bytes(raw, mime_type)

        audio = message.get("audio") or {}
        if audio:
            file_id = str(audio.get("file_id") or "").strip()
            if file_id:
                file_meta = await self._api_call("getFile", {"file_id": file_id}, timeout_sec=20.0)
                file_path = str((file_meta.get("result") or {}).get("file_path") or "").strip()
                if file_path:
                    raw = await self._download_telegram_file(file_path)
                    mime_type = str(audio.get("mime_type") or "audio/mpeg").strip() or "audio/mpeg"
                    return await self._transcribe_audio_bytes(raw, mime_type)

        return ""

    async def _get_session(self, chat_id: int, user_label: str) -> TelegramChatSession:
        async with self._sessions_lock:
            session = self._sessions.get(chat_id)
            if session:
                return session
            session = TelegramChatSession(
                chat_id,
                user_label,
                self.settings_getter,
                calendar_manager=self.calendar_manager,
                reminder_manager=self.reminder_manager,
                spotify_manager=self.spotify_manager,
                personality=self.personality,
            )
            self._sessions[chat_id] = session
            return session

    async def _peek_session(self, chat_id: int) -> Optional[TelegramChatSession]:
        async with self._sessions_lock:
            return self._sessions.get(chat_id)

    async def _drop_session(self, chat_id: int):
        async with self._sessions_lock:
            session = self._sessions.pop(chat_id, None)
        if session:
            await session.stop()

    async def _cleanup_idle_sessions(self):
        while not self._stop_event.is_set():
            await asyncio.sleep(60.0)
            now = time.monotonic()
            stale_ids = []
            async with self._sessions_lock:
                for chat_id, session in self._sessions.items():
                    if (now - session.last_activity_ts) > self.session_idle_sec:
                        stale_ids.append(chat_id)
            for chat_id in stale_ids:
                await self._drop_session(chat_id)

    async def _handle_text(self, chat_id: int, user_label: str, text: str):
        session = await self._get_session(chat_id, user_label)
        await self._send_typing(chat_id)
        reply = await session.ask(text)
        await self._send_message(chat_id, reply)

    async def _handle_turn(
        self,
        chat_id: int,
        user_label: str,
        text: Optional[str],
        attachments: Optional[List[Dict[str, Any]]] = None,
    ):
        session = await self._get_session(chat_id, user_label)
        await self._send_typing(chat_id)
        if attachments:
            reply = await session.ask_with_attachments(text, attachments)
        else:
            reply = await session.ask(str(text or ""))
        await self._send_message(chat_id, reply)

    async def _handle_message(self, message: Dict[str, Any]):
        chat = message.get("chat") or {}
        chat_id = int(chat.get("id"))
        chat_type = str(chat.get("type") or "")
        if not self._is_chat_allowed(chat_id, chat_type):
            return

        user = message.get("from") or {}
        user_label = (
            str(user.get("username") or "").strip()
            or " ".join(part for part in [user.get("first_name"), user.get("last_name")] if part)
            or f"telegram:{chat_id}"
        )

        text = str(message.get("text") or message.get("caption") or "").strip()
        command, args = self._parse_command(text)
        if command == "start":
            await self._send_message(
                chat_id,
                (
                    "Monika jest gotowa na Telegramie.\n\n"
                    "Komendy:\n"
                    "/help\n/reset\n/status\n/memory\n/forget\n/mood\n/notes\n/remind"
                ),
            )
            return
        if command == "help":
            await self._send_message(
                chat_id,
                (
                    "Dostępne komendy:\n"
                    "/start - start i krótki onboarding\n"
                    "/help - lista komend\n"
                    "/reset - reset sesji Telegram\n"
                    "/status - status sesji\n"
                    "/memory - ostatnie wpisy pamięci\n"
                    "/forget - usuń ostatni wpis pamięci\n"
                    "/mood - nastrój Moniki\n"
                    "/notes - lista notatek i stron\n"
                    "/notes <ścieżka> - pokaż wybraną notatkę\n"
                    "/notes add <tekst> - dopisz do notes.md\n"
                    "/notes add <ścieżka> | <tekst> - dopisz do wybranej strony\n"
                    "/remind <wiadomość> | 45m\n"
                    "/remind <wiadomość> | 2026-03-15 18:30"
                ),
            )
            return
        if command == "reset":
            await self._drop_session(chat_id)
            await self._send_message(chat_id, "Zresetowalam biezaca sesje Telegram.")
            return
        if command == "status":
            session = await self._peek_session(chat_id)
            if not session:
                await self._send_message(chat_id, "Sesja: nieaktywna\nCzat: {0}\nOstatnia aktywność: brak".format(chat_id))
            else:
                await self._send_message(chat_id, session.get_status_summary())
            return
        if command == "memory":
            session = await self._get_session(chat_id, user_label)
            await session.ensure_started()
            await self._send_message(chat_id, session.get_memory_summary())
            return
        if command == "forget":
            session = await self._get_session(chat_id, user_label)
            await session.ensure_started()
            await self._send_message(chat_id, session.forget_last_memory())
            return
        if command == "mood":
            session = await self._get_session(chat_id, user_label)
            await session.ensure_started()
            await self._send_message(chat_id, session.get_mood_summary())
            return
        if command == "notes":
            session = await self._get_session(chat_id, user_label)
            await session.ensure_started()
            if not args:
                await self._send_message(chat_id, session.list_notes_catalog())
            elif args.lower().startswith("add "):
                payload = args[4:].strip()
                if "|" in payload:
                    selector, note_text = [part.strip() for part in payload.split("|", 1)]
                    await self._send_message(chat_id, session.append_note_page(selector, note_text))
                else:
                    await self._send_message(chat_id, session.append_notes(payload))
            else:
                await self._send_message(chat_id, session.get_note_page(args))
            return
        if command == "remind":
            session = await self._get_session(chat_id, user_label)
            await session.ensure_started()
            await self._send_message(chat_id, session.create_reminder_from_command(args))
            return

        if not text:
            try:
                text = await self._build_audio_transcript(message)
            except Exception as exc:
                await self._send_message(chat_id, f"Nie udało mi się odsłuchać voice note: {exc}")
                return
            if not text and (message.get("voice") or message.get("audio")):
                await self._send_message(chat_id, "Nie udało mi się zrozumieć tego voice note.")
                return

        attachments = await self._build_message_attachments(message)
        if not text and not attachments:
            await self._send_message(chat_id, "Na razie obsługiwany jest tekst, zdjęcia i voice notes.")
            return

        await self._handle_turn(chat_id, user_label, text, attachments)

    async def run(self):
        await self._register_bot_metadata()
        await self._api_call("deleteWebhook", {"drop_pending_updates": False}, timeout_sec=15.0)
        cleanup_task = asyncio.create_task(self._cleanup_idle_sessions())
        try:
            while not self._stop_event.is_set():
                try:
                    data = await self._api_call(
                        "getUpdates",
                        {
                            "offset": self._offset,
                            "timeout": 25,
                            "allowed_updates": ["message"],
                        },
                        timeout_sec=35.0,
                    )
                    for update in data.get("result") or []:
                        update_id = int(update.get("update_id", 0))
                        if update_id >= self._offset:
                            self._offset = update_id + 1
                        message = update.get("message")
                        if message:
                            try:
                                await self._handle_message(message)
                            except Exception as exc:
                                chat_id = ((message.get("chat") or {}).get("id"))
                                if chat_id:
                                    await self._send_message(int(chat_id), f"Blad Telegram bridge: {exc}")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    print(f"[TELEGRAM] Polling error: {exc}")
                    await asyncio.sleep(3.0)
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            async with self._sessions_lock:
                sessions = list(self._sessions.values())
                self._sessions.clear()
            for session in sessions:
                await session.stop()

    async def stop(self):
        self._stop_event.set()
