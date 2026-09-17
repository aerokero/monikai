"""Conversation/session boundary for the always-on server microphone."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.core import monikai
from backend.core.session_manager import SessionManager


class ServerVoiceSessionStore:
    """Persist wake-activated voice conversations in the normal session store."""

    channel = "server_voice"

    def __init__(
        self,
        workspace_root: Path,
        *,
        emit_event: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> None:
        self.manager = SessionManager(
            workspace_root,
            write_mode="immediate",
            auto_start=False,
        )
        self.emit_event = emit_event
        self.active = False

    async def _emit(self, event: str, payload: Dict[str, Any]) -> None:
        if not self.emit_event:
            return
        try:
            result = self.emit_event(event, payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # Session persistence must never fail because no browser is open.
            pass

    async def begin(self) -> str:
        if self.active and self.manager.get_current_session_id():
            return str(self.manager.get_current_session_id())
        now = datetime.now()
        session_id = self.manager.start_new_session(
            session_id=f"voice_{now.strftime('%Y%m%d_%H%M%S_%f')[:-3]}",
            channel=self.channel,
            extra_meta={"source": "server_microphone", "finalized": False},
        )
        self.active = True
        await self._emit(
            "server_voice_session_started",
            {"id": session_id, "channel": self.channel},
        )
        return session_id

    async def record_turn(self, user_text: str, assistant_text: str) -> str:
        session_id = await self.begin()
        user_text = str(user_text or "").strip()
        assistant_text = str(assistant_text or "").strip()
        if user_text:
            self.manager.log_chat("User", user_text)
        if assistant_text:
            self.manager.log_chat("AI", assistant_text)
        await self.publish_turn(user_text, assistant_text, session_id=session_id)
        return session_id

    async def publish_turn(
        self,
        user_text: str,
        assistant_text: str,
        *,
        session_id: Optional[str] = None,
    ) -> None:
        """Notify open web clients after another component persisted the turn."""
        await self._emit(
            "server_voice_turn",
            {
                "session_id": session_id or self.manager.get_current_session_id(),
                "channel": self.channel,
                "user": str(user_text or "").strip(),
                "assistant": str(assistant_text or "").strip(),
            },
        )

    async def end(self) -> None:
        if not self.active:
            return
        session_id = self.manager.get_current_session_id()
        self.manager.flush_current_session()
        self.manager.update_meta(
            ended_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            finalized=True,
        )
        self.active = False
        await self._emit(
            "server_voice_session_finished",
            {"id": session_id, "channel": self.channel},
        )

    def close(self) -> None:
        self.manager.close()


class ServerVoiceChatSession:
    """Run server-microphone text turns through Monika's normal tool pipeline."""

    def __init__(
        self,
        *,
        session_store: ServerVoiceSessionStore,
        settings_getter: Callable[[], Dict[str, Any]],
        calendar_manager=None,
        reminder_manager=None,
        spotify_manager=None,
        personality=None,
        kasa_agent=None,
        hue_agent=None,
        home_assistant_agent=None,
        conversation_gateway=None,
    ) -> None:
        self.session_store = session_store
        self.settings_getter = settings_getter
        self.calendar_manager = calendar_manager
        self.reminder_manager = reminder_manager
        self.spotify_manager = spotify_manager
        self.personality = personality
        self.kasa_agent = kasa_agent
        self.hue_agent = hue_agent
        self.home_assistant_agent = home_assistant_agent
        self.conversation_gateway = conversation_gateway
        self.audio_loop = None
        self.run_task = None
        self.lock = asyncio.Lock()

    def _conversation_route(self) -> tuple[str, str, str]:
        """Return the route currently selected for text conversations.

        The model picker persists its selection in MonikAI's conversation
        settings.  The native Odysseus settings store is kept as a fallback
        for older installs that do not have the conversation-specific keys
        yet.  Resolve this on every turn instead of freezing the first route
        seen when the microphone session was started; a model switch in the
        web UI should apply to the next spoken turn as well.
        """
        settings = self.settings_getter() or {}
        model = str(settings.get("text_model") or "").strip()
        endpoint_id = str(settings.get("text_endpoint_id") or "").strip()
        persona_id = str(settings.get("text_persona_id") or "").strip()

        if not model or not endpoint_id:
            try:
                from src.settings import load_settings

                native_settings = load_settings() or {}
                if not endpoint_id:
                    endpoint_id = str(native_settings.get("default_endpoint_id") or "").strip()
                if not model:
                    model = str(native_settings.get("default_model") or "").strip()
            except Exception:
                # The gateway still owns its safe application defaults when
                # an older/test runtime has no native settings module.
                pass

        return model, endpoint_id, persona_id

    async def ensure_started(self) -> None:
        if self.conversation_gateway is None:
            raise RuntimeError("Native Odysseus gateway is not configured for server voice")
        if not self.session_store.manager.get_current_session_id():
            await self.session_store.begin()

    async def ask(self, text: str) -> str:
        async with self.lock:
            await self.ensure_started()
            session_id = self.session_store.manager.get_current_session_id()
            model, endpoint_id, persona_id = self._conversation_route()
            return await self.conversation_gateway.generate(
                text,
                timeout_sec=120.0,
                model=model,
                endpoint_id=endpoint_id,
                persona_id=persona_id,
                session_id=str(session_id or ""),
            )

    @property
    def uses_canonical_history(self) -> bool:
        return self.conversation_gateway is not None

    async def stop(self) -> None:
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
