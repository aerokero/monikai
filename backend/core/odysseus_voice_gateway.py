"""In-process gateway from Live voice turns to native Odysseus chat."""

from __future__ import annotations

import json
import logging
import base64
import binascii
import mimetypes
import os
import secrets
from typing import Any, Dict, List, Optional

import httpx

from backend.conversation.voice_quality import voice_transcript_is_usable


logger = logging.getLogger(__name__)

_VOICE_SILENCE_MARKERS = {
    "[voice_silence]",
    "voice_silence",
    "[silent]",
}


class OdysseusVoiceGateway:
    """Use the mounted native agent route as the sole voice response author.

    Live remains useful for microphone transport and input transcription.  It
    is intentionally not asked to write the assistant reply.  Calling the
    native route through ASGI keeps the exact same model, persona, memory,
    tools and policy as the Agent composer in the normal Odysseus chat UI
    without opening a loopback network connection or duplicating generation
    code.
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
        self._default_model = str(model or os.getenv("ODYSSEUS_LIVE_TEXT_MODEL") or "gemini-2.5-flash").strip()
        self._default_endpoint_id = str(endpoint_id or os.getenv("ODYSSEUS_LIVE_TEXT_ENDPOINT_ID") or "gemini-text").strip()
        self._default_persona_id = str(persona_id or os.getenv("ODYSSEUS_LIVE_PERSONA_ID") or "monika").strip()
        self.model = self._default_model
        self.endpoint_id = self._default_endpoint_id
        self.persona_id = self._default_persona_id
        self.session_id = str(session_id or os.getenv("ODYSSEUS_LIVE_SESSION_ID") or "monikai-live").strip()
        # The native chat route is reached through an in-process ASGI request.
        # Keep a per-process marker so only this gateway can enable the
        # Live-Voice-only Home Assistant auto-approval policy.
        self._voice_transport_token = secrets.token_urlsafe(32)

    def configure(
        self,
        *,
        model: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        if model is not None:
            self.model = str(model).strip() or self._default_model
        if endpoint_id is not None:
            self.endpoint_id = str(endpoint_id).strip() or self._default_endpoint_id
        if persona_id is not None:
            self.persona_id = str(persona_id).strip() or self._default_persona_id
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

        # The bridge runs in single-user mode. Native route ownership and
        # upload ownership must use the same primary user as the existing
        # workspace sessions; otherwise a freshly created voice/channel
        # session is created ownerless and the native route rejects it.
        owner = None
        auth_manager = getattr(getattr(self.app, "state", None), "auth_manager", None)
        get_primary_user = getattr(auth_manager, "get_primary_user", None)
        if callable(get_primary_user):
            try:
                owner = get_primary_user()
            except Exception:
                owner = None

        try:
            session = manager.get_session(session_id)
        except (KeyError, LookupError):
            session = manager.create_session(
                session_id=session_id,
                name="Live Voice",
                endpoint_url=endpoint_url,
                model=model,
                owner=owner,
            )

        session.endpoint_url = endpoint_url
        session.model = model
        session.headers = {}
        if owner and not getattr(session, "owner", None):
            # Claim only legacy ownerless channel sessions in single-user
            # mode; never overwrite an existing owner's session.
            session.owner = owner

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
                if owner and not stored.owner:
                    stored.owner = owner
                db.commit()
        finally:
            db.close()
        return session

    @staticmethod
    def _stream_result(response: httpx.Response) -> str:
        """Extract the user-facing answer from the native Agent SSE stream."""

        answer_parts: list[str] = []
        tool_names: list[str] = []
        stream_error: Optional[str] = None
        asked_question: Optional[str] = None
        approval_resolution: Optional[str] = None

        for line in response.text.splitlines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            event_type = event.get("type")
            if event_type == "tool_start":
                tool = str(event.get("tool") or "").strip()
                if tool and tool not in tool_names:
                    tool_names.append(tool)
            elif event_type == "ask_user":
                data = event.get("data") or {}
                if isinstance(data, dict):
                    asked_question = (
                        str(
                            data.get("voice_prompt")
                            or data.get("question")
                            or ""
                        ).strip()
                        or None
                    )
                    notice = str(data.get("notice") or "").strip()
                    if notice and asked_question and notice not in asked_question:
                        asked_question = f"{notice} {asked_question}"
            elif event_type == "agent_terminal":
                data = event.get("data") or {}
                failure = data.get("failure") if isinstance(data, dict) else None
                if isinstance(failure, dict):
                    stream_error = str(failure.get("message") or "Agent run failed").strip()
                else:
                    stream_error = "Agent run failed"
            elif event_type == "tool_approval_resolved":
                if str((event.get("decision") or "")).strip().lower() == "deny":
                    approval_resolution = "Dobrze, nie wykonam tej czynności."
            elif event_type == "error" or event.get("error"):
                stream_error = "Agent run failed"

            # Thinking deltas are useful to the web UI but must never be spoken.
            if "delta" in event and not event.get("thinking"):
                answer_parts.append(str(event.get("delta") or ""))

        if stream_error:
            raise RuntimeError(stream_error)

        answer = "".join(answer_parts).strip()
        if answer.casefold() in _VOICE_SILENCE_MARKERS:
            # The voice prompt gives the text author a closed way to say that
            # an ASR fragment has no recoverable meaning. Never speak the
            # marker and never turn it into the generic tool fallback below.
            return ""
        if not answer and asked_question:
            # Voice has no clickable approval/clarification card. Speaking the
            # question keeps the interaction usable; the next spoken turn can
            # resolve the pending approval in the same canonical session.
            answer = asked_question
        if not answer and approval_resolution:
            answer = approval_resolution
        if not answer and tool_names:
            # The native agent uses this same fallback when a tool completed
            # without a final prose delta. Keep the voice channel responsive.
            answer = "Done."
        if not answer:
            raise RuntimeError("Odysseus returned an empty voice response")
        logger.info("[VOICE AGENT] completed tools=%s answer_chars=%d", tool_names, len(answer))
        return answer

    async def generate(
        self,
        text: str,
        *,
        attachment_ids: Optional[List[str]] = None,
        timeout_sec: float = 120.0,
        model: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        prompt = str(text or "").strip()
        normalized_attachment_ids = [
            str(item).strip()
            for item in (attachment_ids or [])
            if str(item or "").strip()
        ]
        if not prompt and not normalized_attachment_ids:
            raise ValueError("voice turn text or attachments cannot be empty")
        if prompt and not voice_transcript_is_usable(prompt):
            # This is the final cheap boundary before a voice transcript can
            # reach context building, search, or tools. Providers that do not
            # expose confidence still get protection for empty/explicitly
            # unintelligible results; confidence-aware providers reject those
            # earlier in their STT adapter.
            logger.info("[VOICE STT] dropping unusable transcript before generation")
            return ""
        self.configure(
            model=model,
            endpoint_id=endpoint_id,
            persona_id=persona_id,
            session_id=session_id,
        )

        # Keep route selection observable without logging endpoint credentials.
        # In particular, a voice turn must be diagnosable as using the same
        # model the web picker selected rather than an implicit provider.
        logger.info(
            "[VOICE ROUTE] endpoint=%s model=%s persona=%s",
            self.endpoint_id,
            self.model,
            self.persona_id or "monika",
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
            # Live voice is always the Agent channel. Keep the normal user and
            # administrator privilege gates in the native route, but expose
            # the same optional tool families as an Agent composer turn.
            "mode": "agent",
            "allow_web_search": "true",
            "allow_bash": "true",
            "voice_mode": True,
            "voice_transport_token": self._voice_transport_token,
        }
        if normalized_attachment_ids:
            # The native route accepts attachment IDs, never inline bytes. The
            # upload route has already performed type/size/ownership checks.
            payload["attachments"] = json.dumps(normalized_attachment_ids)
        transport = httpx.ASGITransport(app=self.app)
        timeout = httpx.Timeout(max(5.0, float(timeout_sec or 120.0)))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://odysseus.internal",
            timeout=timeout,
        ) as client:
            # Use the same form endpoint the browser's Agent mode
            # uses. The non-streaming /api/chat route is deliberately text-only
            # and cannot execute native tools.
            response = await client.post("/api/chat_stream", data=payload)

        if response.status_code >= 400:
            try:
                detail: Any = response.json() if response.content else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                detail = response.text[:500]
            raise RuntimeError(f"Odysseus voice turn failed ({response.status_code}): {detail}")
        answer = self._stream_result(response)
        return answer

    async def upload_attachments(
        self,
        attachments: Optional[List[Dict[str, Any]]],
        *,
        session_id: Optional[str] = None,
        timeout_sec: float = 90.0,
    ) -> List[Dict[str, Any]]:
        """Persist raw channel attachments through the native upload route.

        Telegram/other non-browser channels receive bytes from their provider,
        while the native chat pipeline deliberately consumes only durable
        upload IDs. Keeping this conversion here makes every channel use the
        exact same upload validation, vision and document-processing code.
        Existing ``id`` references are passed through unchanged.
        """
        items = [item for item in (attachments or []) if isinstance(item, dict)]
        if not items:
            return []

        ordered: List[Optional[Dict[str, Any]]] = []
        multipart = []
        for item in items:
            existing_id = str(item.get("id") or item.get("attachment_id") or "").strip()
            if existing_id and not item.get("data"):
                ordered.append({**item, "id": existing_id})
                continue

            encoded = item.get("data")
            if not encoded:
                raise ValueError(f"attachment {item.get('name') or 'unnamed'} has no data")
            if isinstance(encoded, bytes):
                encoded = encoded.decode("ascii", errors="strict")
            encoded = str(encoded).strip()
            if encoded.startswith("data:") and "," in encoded:
                encoded = encoded.split(",", 1)[1]
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError(f"attachment {item.get('name') or 'unnamed'} is not valid base64") from exc
            if not raw:
                raise ValueError(f"attachment {item.get('name') or 'unnamed'} is empty")

            name = str(item.get("name") or "attachment.bin").strip() or "attachment.bin"
            mime = str(item.get("mime_type") or item.get("mime") or "").strip().lower()
            mime = mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
            multipart.append(("files", (name, raw, mime)))
            ordered.append(None)

        if not multipart:
            return [item for item in ordered if item is not None]

        form = {}
        if session_id:
            form["session_id"] = str(session_id)
        transport = httpx.ASGITransport(app=self.app)
        timeout = httpx.Timeout(max(5.0, float(timeout_sec or 90.0)))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://odysseus.internal",
            timeout=timeout,
        ) as client:
            response = await client.post("/api/upload", data=form, files=multipart)

        if response.status_code >= 400:
            try:
                detail: Any = response.json() if response.content else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                detail = response.text[:500]
            raise RuntimeError(f"Odysseus attachment upload failed ({response.status_code}): {detail}")

        try:
            result = response.json()
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Odysseus attachment upload returned invalid JSON") from exc
        uploaded = result.get("files") if isinstance(result, dict) else None
        if not isinstance(uploaded, list) or len(uploaded) != len(multipart):
            raise RuntimeError("Odysseus attachment upload returned incomplete file metadata")
        if not all(isinstance(item, dict) for item in uploaded):
            raise RuntimeError("Odysseus attachment upload returned invalid file metadata")
        uploaded_iter = iter(uploaded)
        result_items: List[Dict[str, Any]] = []
        for item in ordered:
            result_items.append(item if item is not None else next(uploaded_iter))
        return result_items
