"""In-process gateway from Live voice turns to native Odysseus chat."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx


class OdysseusVoiceGateway:
    """Use the mounted native chat route as the sole voice response author.

    Live remains useful for microphone transport and input transcription.  It
    is intentionally not asked to write the assistant reply.  Calling the
    native route through ASGI keeps the exact same model, persona, memory and
    tool policy as the normal Odysseus chat UI without opening a loopback
    network connection or duplicating generation code.
    """

    def __init__(
        self,
        app,
        *,
        model: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.app = app
        self.model = str(model or os.getenv("ODYSSEUS_LIVE_TEXT_MODEL") or "gemini-2.5-flash").strip()
        self.endpoint_id = str(endpoint_id or os.getenv("ODYSSEUS_LIVE_TEXT_ENDPOINT_ID") or "gemini-text").strip()
        self.persona_id = str(persona_id or os.getenv("ODYSSEUS_LIVE_PERSONA_ID") or "monika").strip()
        self.session_id = str(session_id or os.getenv("ODYSSEUS_LIVE_SESSION_ID") or "monikai-live").strip()

    def configure(
        self,
        *,
        model: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        if model:
            self.model = str(model).strip()
        if endpoint_id:
            self.endpoint_id = str(endpoint_id).strip()
        if persona_id:
            self.persona_id = str(persona_id).strip()
        if session_id:
            self.session_id = str(session_id).strip()

    def _endpoint(self):
        components = getattr(getattr(self.app, "state", None), "odysseus_components", {}) or {}
        if not components:
            raise RuntimeError("Odysseus backend is not initialized")

        from core.database import ModelEndpoint, SessionLocal
        from src.endpoint_resolver import build_chat_url, normalize_base

        db = SessionLocal()
        try:
            row = db.query(ModelEndpoint).filter(ModelEndpoint.id == self.endpoint_id).first()
            if row is None or not row.is_enabled:
                raise RuntimeError(f"Odysseus endpoint '{self.endpoint_id}' is not available")
            return row, build_chat_url(normalize_base(row.base_url or ""))
        finally:
            db.close()

    def _ensure_session(self, session_id: str, row, endpoint_url: str, model: str):
        components = getattr(self.app.state, "odysseus_components", {})
        manager = components.get("session_manager")
        if manager is None:
            raise RuntimeError("Odysseus session manager is not initialized")

        try:
            session = manager.get_session(session_id)
        except (KeyError, LookupError):
            session = manager.create_session(
                session_id=session_id,
                name="Live Voice",
                endpoint_url=endpoint_url,
                model=model,
                owner=None,
            )

        session.endpoint_url = endpoint_url
        session.model = model
        session.headers = {}

        # Keep the DB row in sync with the in-memory session.  Native auth
        # resolution still obtains the encrypted provider key from the
        # endpoint row, so no secret is copied into the Live payload.
        from core.database import Session as DbSession, SessionLocal

        db = SessionLocal()
        try:
            stored = db.query(DbSession).filter(DbSession.id == session_id).first()
            if stored is not None:
                stored.endpoint_url = endpoint_url
                stored.model = model
                db.commit()
        finally:
            db.close()
        return session

    async def generate(
        self,
        text: str,
        *,
        timeout_sec: float = 120.0,
        model: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        prompt = str(text or "").strip()
        if not prompt:
            raise ValueError("voice turn text cannot be empty")
        self.configure(
            model=model,
            endpoint_id=endpoint_id,
            persona_id=persona_id,
            session_id=session_id,
        )

        row, endpoint_url = self._endpoint()
        active_session_id = self.session_id
        self._ensure_session(active_session_id, row, endpoint_url, self.model)

        payload = {
            "message": prompt,
            "session": active_session_id,
            "preset_id": self.persona_id or "monika",
            "use_web": False,
            "use_research": False,
            "selected_endpoint_id": self.endpoint_id,
        }
        transport = httpx.ASGITransport(app=self.app)
        timeout = httpx.Timeout(max(5.0, float(timeout_sec or 120.0)))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://odysseus.internal",
            timeout=timeout,
        ) as client:
            response = await client.post("/api/chat", json=payload)

        if response.status_code >= 400:
            detail = response.json() if response.content else {}
            raise RuntimeError(f"Odysseus voice turn failed ({response.status_code}): {detail}")
        data: Any = response.json()
        answer = str(data.get("response") or "").strip() if isinstance(data, dict) else ""
        if not answer:
            raise RuntimeError("Odysseus returned an empty voice response")
        return answer

