import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Iterator

# A new user/AI turn after this much silence starts a NEW conversation.
# The digest pipeline treats 15 min idle as "safe to digest", so a split
# conversation gets picked up naturally on the next scan.
CONVERSATION_IDLE_SPLIT_SEC = 45 * 60

# Channels that are continuous streams (no natural "end of conversation"):
# one log per channel per day, digested as a daily recap — not a conversation.
STREAM_DIR_PREFIX = "stream_"


class SessionManager:
    """Global session manager (no projects).

    Two kinds of threads (v3 Phase G):
    - conversation: app chat / voice session; has a beginning and an end,
      lives in the sidebar, digested per session.
    - stream: continuous channel (minecraft, telegram); one directory per
      channel per day (``stream_<channel>``), digested as a daily recap.
    """

    def __init__(
        self,
        workspace_root: Path,
        write_mode: str = "immediate",
        stream_channel: Optional[str] = None,
    ):
        self.workspace_root = Path(workspace_root)
        self.sessions_dir = self.workspace_root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_id: Optional[str] = None
        self.current_session_path: Optional[Path] = None
        self.write_mode = write_mode if write_mode in {"session_end", "immediate"} else "session_end"
        self._pending_turns: List[Dict] = []
        self._last_turn_ts: float = 0.0
        self._session_has_turns: bool = False
        # Stream mode: every log_chat() goes to the channel's continuous
        # per-day log; no conversation session is ever created (Telegram).
        self.stream_channel = stream_channel
        if not stream_channel:
            self.start_new_session()

    def start_new_session(
        self,
        session_id: Optional[str] = None,
        *,
        channel: str = "app",
        extra_meta: Optional[Dict] = None,
    ) -> str:
        self.flush_current_session()

        ts = datetime.now()
        if not session_id:
            session_id = f"sess_{ts.strftime('%Y%m%d_%H%M%S_%f')[:-3]}"

        day_dir = self.sessions_dir / ts.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)

        base_session_id = session_id
        session_path = day_dir / session_id
        suffix = 2
        while session_path.exists():
            session_id = f"{base_session_id}_{suffix}"
            session_path = day_dir / session_id
            suffix += 1
        session_path.mkdir(parents=True, exist_ok=False)

        self.current_session_id = session_id
        self.current_session_path = session_path
        self._session_has_turns = False
        self._last_turn_ts = 0.0
        self._ensure_meta(ts, channel=channel, extra_meta=extra_meta)
        return session_id

    def _ensure_meta(
        self,
        ts: datetime,
        *,
        channel: str = "app",
        extra_meta: Optional[Dict] = None,
    ) -> None:
        if not self.current_session_path:
            return
        meta_path = self.current_session_path / "meta.json"
        if meta_path.exists():
            return
        payload = {
            "session_id": self.current_session_id,
            "kind": "conversation",
            "channel": channel,
            "started_at": ts.astimezone().isoformat(timespec="seconds"),
        }
        if extra_meta:
            payload.update(extra_meta)
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def update_meta(self, **kwargs) -> None:
        """Merge keys into the current session's meta.json (e.g. mode,
        ended_at, finalized). Creates the file if missing."""
        if not self.current_session_path:
            return
        self.update_meta_for(self.current_session_path, **kwargs)

    @staticmethod
    def update_meta_for(session_path: Path, **kwargs) -> None:
        """Merge keys into an arbitrary session's meta.json."""
        meta_path = Path(session_path) / "meta.json"
        try:
            payload = (
                json.loads(meta_path.read_text(encoding="utf-8"))
                if meta_path.exists()
                else {}
            )
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        payload.update(kwargs)
        try:
            meta_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    def get_current_session_turns(self, limit: int = 10) -> List[Dict]:
        """Return up to ``limit`` most recent turns from the CURRENT session
        only (in-memory pending + this session's turns.jsonl), oldest first.
        Used for auto-finalizing a session summary."""
        if limit <= 0:
            return []

        if self.stream_channel:
            return self.get_stream_turns(self.stream_channel, limit=limit)

        current_path = self.get_current_session_path()
        if not current_path:
            return []

        turns: List[Dict] = []
        log_file = current_path / "turns.jsonl"
        if log_file.exists():
            try:
                for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not line.strip():
                        entry = json.loads(line)
                        if isinstance(entry, dict):
                            turns.append(entry)
                    except Exception:
                        continue
            except Exception:
                pass

        for entry in self._pending_turns:
            if isinstance(entry, dict):
                turns.append(entry)

        return turns[-limit:]

    def get_current_session_id(self) -> Optional[str]:
        if self.stream_channel:
            try:
                return self.get_stream_path(self.stream_channel).name
            except Exception:
                return f"{STREAM_DIR_PREFIX}{self.stream_channel}"
        return self.current_session_id

    def get_current_session_path(self) -> Optional[Path]:
        if self.stream_channel:
            try:
                return self.get_stream_path(self.stream_channel)
            except Exception:
                return None
        return self.current_session_path

    def get_session_path(self, session_id: str) -> Optional[Path]:
        if not session_id:
            return None
        if self.current_session_id == session_id and self.current_session_path:
            return self.current_session_path
        # Search on disk
        for day_dir in sorted(self.sessions_dir.iterdir(), reverse=True):
            if not day_dir.is_dir():
                continue
            for sess_dir in sorted(day_dir.iterdir(), reverse=True):
                if sess_dir.is_dir() and sess_dir.name == session_id:
                    return sess_dir
        return None

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def _should_autosplit(self) -> bool:
        if not self._session_has_turns or self._last_turn_ts <= 0:
            return False
        return (time.time() - self._last_turn_ts) > CONVERSATION_IDLE_SPLIT_SEC

    def log_chat(self, sender: str, text: str) -> None:
        if self.stream_channel:
            self.log_stream(self.stream_channel, sender, text)
            return
        if not self.current_session_path:
            return
        # A turn after a long silence belongs to a fresh conversation.
        if self._should_autosplit():
            self.start_new_session()

        entry = {
            "timestamp": time.time(),
            "sender": sender,
            "text": text,
            "session_id": self.current_session_id,
        }
        self._pending_turns.append(entry)
        self._session_has_turns = True
        self._last_turn_ts = entry["timestamp"]

        if self.write_mode == "immediate":
            self.flush_current_session()

    def flush_current_session(self) -> None:
        if not self.current_session_path or not self._pending_turns:
            return

        log_file = self.current_session_path / "turns.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            for entry in self._pending_turns:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._pending_turns.clear()

    def close(self) -> None:
        self.flush_current_session()

    def flush_session(self, session_id: Optional[str] = None) -> None:
        if not session_id or session_id == self.current_session_id:
            self.flush_current_session()

    # ------------------------------------------------------------------
    # Streams (minecraft, telegram, ...)
    # ------------------------------------------------------------------

    def get_stream_path(self, channel: str) -> Path:
        """Directory of today's stream for ``channel`` — created on first use."""
        day = datetime.now()
        day_dir = self.sessions_dir / day.strftime("%Y-%m-%d")
        stream_dir = day_dir / f"{STREAM_DIR_PREFIX}{channel}"
        if not stream_dir.exists():
            stream_dir.mkdir(parents=True, exist_ok=True)
            meta = {
                "session_id": f"{STREAM_DIR_PREFIX}{channel}_{day.strftime('%Y%m%d')}",
                "kind": "stream",
                "channel": channel,
                "started_at": day.astimezone().isoformat(timespec="seconds"),
            }
            (stream_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        return stream_dir

    def log_stream(self, channel: str, sender: str, text: str) -> None:
        """Append a turn to today's continuous log of ``channel``.

        Streams write straight to disk (no buffering) — they are append-only
        side channels and their volume is not latency-critical.
        """
        if not text:
            return
        try:
            stream_dir = self.get_stream_path(channel)
            entry = {
                "timestamp": time.time(),
                "sender": sender,
                "text": text,
                "session_id": stream_dir.name,
            }
            with open(stream_dir / "turns.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_stream_turns(self, channel: str, limit: int = 10) -> List[Dict]:
        """Most recent turns of today's ``channel`` stream, oldest first.

        Streams are the conversation of record for channels that never open a
        session (Telegram), so this is what their history reads must use."""
        if limit <= 0 or not channel:
            return []

        day_dir = self.sessions_dir / datetime.now().strftime("%Y-%m-%d")
        log_file = day_dir / f"{STREAM_DIR_PREFIX}{channel}" / "turns.jsonl"
        if not log_file.exists():
            return []

        turns: List[Dict] = []
        try:
            for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if isinstance(entry, dict):
                    turns.append(entry)
        except Exception:
            return []

        return turns[-limit:]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_recent_chat_history(self, limit: int = 10) -> List[Dict]:
        """Most recent conversation turns across sessions, oldest first.

        Streams (minecraft/telegram logs) are excluded — cross-session
        context should be conversational, not in-game chat spam.
        """
        if limit <= 0:
            return []

        results: List[Dict] = []

        # Newest in-memory entries first (not yet flushed to disk).
        for entry in reversed(self._pending_turns):
            if isinstance(entry, dict):
                results.append(entry)
            if len(results) >= limit:
                return list(reversed(results))

        for turns_path in self._iter_turns_files_desc():
            try:
                lines = turns_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue

            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict):
                        results.append(entry)
                    if len(results) >= limit:
                        return list(reversed(results))
                except Exception:
                    continue

        return list(reversed(results))

    def _iter_turns_files_desc(self, include_streams: bool = False) -> Iterator[Path]:
        if not self.sessions_dir.exists():
            return

        day_dirs = [d for d in self.sessions_dir.iterdir() if d.is_dir()]
        day_dirs.sort(reverse=True)

        for day_dir in day_dirs:
            sess_dirs = [d for d in day_dir.iterdir() if d.is_dir()]
            if not include_streams:
                sess_dirs = [d for d in sess_dirs if not d.name.startswith(STREAM_DIR_PREFIX)]
            sess_dirs.sort(reverse=True)
            for sess_dir in sess_dirs:
                turns = sess_dir / "turns.jsonl"
                if turns.exists():
                    yield turns
