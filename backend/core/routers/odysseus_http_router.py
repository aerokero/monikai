"""Odysseus API Router - Bridges Odysseus UI frontend with MonikAI + ModelRouter engine."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_ODY_ROOT = Path(__file__).resolve().parents[2] / "odysseus"
if str(_ODY_ROOT) not in sys.path:
    sys.path.insert(0, str(_ODY_ROOT))

from backend.models.model_router import get_model_router
from backend.services.docs_service import get_docs_service
from backend.services.email_service import get_email_service
from backend.audio.tts_router import get_tts_router

logger = logging.getLogger(__name__)


# The model picker is a routing control, not a character selector.  Keep the
# old id only as a migration alias for sessions created by older versions.
LEGACY_COMPANION_MODEL = "monika-companion"
DEFAULT_TEXT_MODEL = (os.getenv("MONIKAI_TEXT_MODEL") or "gemini-2.5-flash").strip()
GEMINI_TEXT_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-pro",
)
GEMINI_TEXT_MODEL_DISPLAY = {
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
}


def _canonical_model(model: Any) -> str:
    """Return a real model id, translating only the removed legacy alias."""
    value = str(model or "").strip()
    if value == LEGACY_COMPANION_MODEL:
        return DEFAULT_TEXT_MODEL
    if value.startswith("models/"):
        return value[7:]
    return value


def _is_ollama_route(endpoint_id: Any, endpoint_url: Any) -> bool:
    """Identify the built-in Ollama route selected by the model picker."""
    if str(endpoint_id or "").strip() == "ollama-local":
        return True
    try:
        return urlparse(str(endpoint_url or "")).port == 11434
    except ValueError:
        return False


def _preset_system_prompt(app: FastAPI, preset_id: Any) -> str:
    """Resolve the active persona without making it part of model routing.

    The native preset manager is initialized by the Odysseus bridge.  The
    standalone router tests (and early startup) do not have it, so an absent
    manager simply means that no additional preset layer is active.
    """
    preset_key = str(preset_id or "").strip()
    if not preset_key:
        return ""

    manager = getattr(getattr(app, "state", None), "preset_manager", None)
    if manager is None:
        return ""

    try:
        preset = manager.get(preset_key)
    except Exception:
        preset = None
    if not isinstance(preset, dict) or preset.get("enabled") is False:
        return ""

    prompt = str(preset.get("system_prompt") or "").strip()
    character_name = str(
        preset.get("character_name") or preset.get("name") or ""
    ).strip()
    if character_name:
        name_line = f"Your name is {character_name}."
        prompt = f"{name_line} {prompt}".strip()
    return prompt


def _build_system_prompt(app: FastAPI, form_data: Dict[str, Any]) -> str:
    """Build operational + active-persona instructions as separate layers."""
    from backend.core.system_prompt import OPERATIONAL_PROMPT, current_system_prompt

    explicit_persona = str(
        form_data.get("custom_system_prompt")
        or form_data.get("system_prompt")
        or form_data.get("persona_prompt")
        or ""
    ).strip()
    active_persona = explicit_persona or _preset_system_prompt(
        app, form_data.get("preset_id")
    )

    # No active preset keeps the application's normal Monika character layer.
    # Once a persona is explicitly selected, replace that character layer and
    # retain the character-agnostic operational rules exactly once.
    if not active_persona:
        return current_system_prompt()
    return f"{active_persona}\n\n{OPERATIONAL_PROMPT}".strip()


def _ensure_native_session(session_id: str, prompt: str = "", model: str = DEFAULT_TEXT_MODEL):
    """Ensure Odysseus session exists in the real SQLite database."""
    try:
        import core.database as db
        from core.database import Session as DbSession, ChatMessage, utcnow_naive

        session_id = str(session_id or "default").strip() or "default"
        db_sess = db.SessionLocal()
        try:
            row = db_sess.query(DbSession).filter(DbSession.id == session_id).first()
            now = utcnow_naive()
            title = (prompt or "Rozmowa z Moniką").strip().replace("\n", " ")
            if not title:
                title = "Rozmowa z Moniką"
            if row is None:
                row = DbSession(
                    id=session_id,
                    name=(title[:32] + "...") if len(title) > 32 else title,
                    endpoint_url="/api/chat_stream",
                    model=_canonical_model(model) or DEFAULT_TEXT_MODEL,
                    rag=False,
                    archived=False,
                    headers={},
                    owner="bartosz",
                    created_at=now,
                    updated_at=now,
                    last_accessed=now,
                    last_message_at=now,
                    message_count=0,
                )
                db_sess.add(row)
            else:
                if not row.owner:
                    row.owner = "bartosz"
                if not row.name or row.name in ("Monika Chat", "Nobody", "New Chat") or str(row.name).startswith("New Chat"):
                    row.name = (title[:32] + "...") if len(title) > 32 else title
                row.endpoint_url = row.endpoint_url or "/api/chat_stream"
                row.model = _canonical_model(model) or row.model or DEFAULT_TEXT_MODEL
                row.updated_at = now
                row.last_accessed = now
            db_sess.commit()
            return row
        finally:
            db_sess.close()
    except Exception:
        return None


def register_odysseus_http_routes(app: FastAPI, emit_to_frontend=None):
    """Registers API routes expected by the Odysseus native frontend."""

    @app.get("/api/models")
    async def get_models(request: Request, refresh: bool = False, background: bool = False):
        router = get_model_router()
        status = router.get_status() if router else {}
        providers = status.get("providers", {})

        gemini_item = {
            "category": "api",
            "endpoint_id": "gemini-text",
            "endpoint_name": "Google Gemini",
            "url": "/api/chat_stream",
            "models": list(GEMINI_TEXT_MODELS),
            "models_display": [GEMINI_TEXT_MODEL_DISPLAY.get(model, model) for model in GEMINI_TEXT_MODELS],
            "models_extra": [],
            "models_extra_display": [],
            "model_type": "llm",
            "supports_tools": True,
        }

        items = [gemini_item]

        for p_name, p_data in providers.items():
            if p_name == "ollama":
                items.append({
                    "category": "local",
                    "endpoint_id": "ollama-local",
                    "endpoint_name": "Local Ollama",
                    "url": "http://localhost:11434/v1/chat/completions",
                    "models": ["llama3.2", "qwen2.5-coder", "mistral"],
                    "models_display": ["Llama 3.2", "Qwen 2.5 Coder", "Mistral"],
                    "models_extra": [],
                    "models_extra_display": [],
                    "model_type": "llm",
                    "supports_tools": True,
                })

        return {
            "ok": True,
            "items": items,
            "models": [model for item in items for model in item.get("models", [])],
            "default_model": DEFAULT_TEXT_MODEL,
        }

    @app.get("/api/default-chat")
    async def get_default_chat():
        return {
            "endpoint_id": "gemini-text",
            "endpoint_name": "Google Gemini",
            "endpoint_url": "/api/chat_stream",
            "model": DEFAULT_TEXT_MODEL,
            "model_display": GEMINI_TEXT_MODEL_DISPLAY.get(DEFAULT_TEXT_MODEL, DEFAULT_TEXT_MODEL),
            "provider": "google",
        }

    @app.post("/api/chat_stream")
    async def chat_stream(request: Request):
        """SSE endpoint for streaming responses into Odysseus UI."""
        form_data = {}
        try:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                form_data = await request.json()
            else:
                form = await request.form()
                form_data = {k: v for k, v in form.items()}
        except Exception:
            pass

        prompt = form_data.get("message") or form_data.get("prompt") or ""
        session_id = form_data.get("session") or form_data.get("session_id", "default")
        model = _canonical_model(
            form_data.get("selected_model")
            or form_data.get("model")
            or DEFAULT_TEXT_MODEL
        )
        selected_endpoint_id = str(form_data.get("selected_endpoint_id") or "").strip()
        selected_endpoint_url = str(form_data.get("selected_endpoint_url") or "").strip()
        temperature_raw = form_data.get("temperature") or form_data.get("temp") or 0.8
        try:
            temperature = float(temperature_raw)
        except Exception:
            temperature = 0.8

        async def event_generator():
            router = get_model_router()
            response_text = "Jestem tutaj z Tobą i słucham! ✨"

            try:
                from backend.conversation.providers import GeminiTextProvider, TextGenerationRequest

                # Persona is resolved independently from the selected model.
                system_prompt = _build_system_prompt(request.app, form_data)

                # Fetch past messages from real Odysseus database for full conversational memory
                past_context = ""
                try:
                    import core.database as db
                    db_sess = db.SessionLocal()
                    from core.database import ChatMessage as DbMsg
                    db_msgs = db_sess.query(DbMsg).filter(DbMsg.session_id == session_id).order_by(DbMsg.timestamp.asc()).all()
                    if db_msgs:
                        for m in db_msgs[-8:]:
                            role_label = "Użytkownik" if m.role == "user" else "Monika"
                            past_context += f"{role_label}: {m.content}\n"
                    db_sess.close()
                except Exception as hist_err:
                    logger.debug("History query error: %s", hist_err)

                _ensure_native_session(session_id, prompt, model)

                full_user_prompt = f"Historia rozmowy:\n{past_context}\nUżytkownik: {prompt}" if past_context else prompt

                # Generate from the selected engine/model.  The old route
                # always sent Gemini requests as gemini-2.5-flash, which made
                # selecting Pro or a local Ollama model purely cosmetic.
                if prompt.strip():
                    gemini_api_key = os.getenv("GEMINI_API_KEY")
                    if gemini_api_key and not _is_ollama_route(selected_endpoint_id, selected_endpoint_url):
                        try:
                            gemini_provider = GeminiTextProvider(api_key=gemini_api_key)
                            req = TextGenerationRequest(
                                model=model,
                                prompt=full_user_prompt,
                                system_instruction=system_prompt,
                            )
                            ans = await gemini_provider.generate(req)
                            if ans and ans.strip():
                                response_text = ans.strip()
                        except Exception as gemini_err:
                            logger.error("Gemini provider generation error: %s", gemini_err, exc_info=True)
                    elif router:
                        try:
                            res = await router.complete(
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": full_user_prompt}
                                ],
                                task="chat",
                                provider_name="ollama" if _is_ollama_route(selected_endpoint_id, selected_endpoint_url) else None,
                                model=model,
                                temperature=temperature,
                            )
                            if res and getattr(res, "content", None):
                                response_text = res.content.strip()
                        except Exception as router_err:
                            logger.error("Router provider generation error: %s", router_err, exc_info=True)

                # Stream tokens with delta format
                words = response_text.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'delta': chunk})}\n\n"
                    await asyncio.sleep(0.02)

                # Persist to Odysseus SQLite session & chat_messages tables
                try:
                    import uuid
                    import core.database as db
                    from core.database import utcnow_naive, ChatMessage
                    db_sess = db.SessionLocal()
                    sess_row = db_sess.query(db.Session).filter(db.Session.id == session_id).first()
                    if sess_row is None:
                        sess_row = _ensure_native_session(session_id, prompt, model)
                    now = utcnow_naive()
                    if sess_row:
                        user_msg = ChatMessage(
                            id=str(uuid.uuid4()),
                            session_id=session_id,
                            role="user",
                            content=prompt,
                            timestamp=now,
                        )
                        db_sess.add(user_msg)

                        asst_msg = ChatMessage(
                            id=str(uuid.uuid4()),
                            session_id=session_id,
                            role="assistant",
                            content=response_text,
                            timestamp=now,
                            meta_data=json.dumps({"model": model}),
                        )
                        db_sess.add(asst_msg)

                        sess_row.last_accessed = now
                        sess_row.last_message_at = now
                        sess_row.updated_at = now
                        sess_row.model = _canonical_model(model) or sess_row.model or DEFAULT_TEXT_MODEL
                        sess_row.message_count = (sess_row.message_count or 0) + 2

                        clean_title = prompt.strip().replace("\n", " ")
                        if clean_title and (not sess_row.name or sess_row.name in ("Monika Chat", "Nobody", "New Chat") or str(sess_row.name).startswith("New Chat")):
                            sess_row.name = (clean_title[:32] + "...") if len(clean_title) > 32 else clean_title

                        db_sess.commit()
                    db_sess.close()
                except Exception as db_save_err:
                    logger.error("Database message persist error: %s", db_save_err)

                # Send [DONE] token required by Odysseus SSE parser
                yield "data: [DONE]\n\n"

            except Exception as err:
                yield f"data: {json.dumps({'error': str(err)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
