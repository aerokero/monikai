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

# These ids are compatibility aliases used by the legacy MonikAI bridge.  The
# actual model catalog lives in Odysseus' ModelEndpoint table; the aliases are
# kept here only so older sessions and the built-in providers continue to work.
_COMPAT_ENDPOINT_IDS = frozenset({"gemini-text", "ollama-local"})
_LEGACY_COMPANION_ENDPOINT_IDS = frozenset({"monika-native"})


class ConversationConfigRequest(BaseModel):
    """Shared text-author selection used by the static and Live clients."""

    text_model: Optional[str] = None
    text_endpoint_id: Optional[str] = None
    text_persona_id: Optional[str] = None
    response_language: Optional[str] = None


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
    from backend.core.response_language import response_language_instruction

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
    return "\n\n".join(
        part for part in (
            active_persona,
            OPERATIONAL_PROMPT,
            response_language_instruction(),
        ) if part
    ).strip()


def _configured_model_items(request: Request) -> List[Dict[str, Any]]:
    """Return user-visible Odysseus endpoints in the legacy picker shape.

    ``/api/models`` used to be a compatibility-only list containing the two
    built-in providers.  That made endpoints added in Odysseus (notably
    OpenRouter with its pinned model allow-list) invisible to the chat picker.
    Keep the response shape expected by the static UI, but source the data from
    the same ModelEndpoint records as Settings and native session creation.
    """
    try:
        from core.database import ModelEndpoint, SessionLocal
        from src.auth_helpers import effective_user, owner_filter
        from src.endpoint_resolver import build_chat_url
        from routes.model_routes import (
            _classify_endpoint,
            _curate_models,
            _effective_endpoint_kind,
            _match_provider_curated,
            _model_display_name,
            _normalize_base,
            _picker_models_for_endpoint,
        )
    except Exception as exc:
        logger.debug("Configured model catalog unavailable: %s", exc)
        return []

    try:
        owner = effective_user(request) or ""
    except Exception:
        owner = ""

    is_admin = False
    try:
        auth_manager = getattr(request.app.state, "auth_manager", None)
        if owner and auth_manager is not None and getattr(auth_manager, "is_admin", None):
            is_admin = bool(auth_manager.is_admin(owner))
    except Exception:
        is_admin = False

    items: List[Dict[str, Any]] = []
    db = SessionLocal()
    try:
        query = db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled == True)  # noqa: E712
        if owner and not is_admin:
            query = owner_filter(query, ModelEndpoint, owner)

        for endpoint in query.order_by(ModelEndpoint.created_at).all():
            endpoint_id = str(getattr(endpoint, "id", "") or "")
            # The old Monika adapter is intentionally not a model choice.  Its
            # character layer belongs to the persona picker, while Gemini and
            # other real text engines belong here.
            if endpoint_id in _LEGACY_COMPANION_ENDPOINT_IDS:
                continue
            # Built-in aliases are emitted below by the compatibility layer;
            # do not show them twice if a migrated database also contains rows.
            if endpoint_id in _COMPAT_ENDPOINT_IDS:
                continue

            base_url = _normalize_base(getattr(endpoint, "base_url", "") or "")
            if not base_url:
                continue
            endpoint_kind = _effective_endpoint_kind(endpoint, base_url)
            try:
                model_ids, pinned = _picker_models_for_endpoint(endpoint, base_url, endpoint_kind)
            except Exception:
                model_ids, pinned = [], []
            if not model_ids:
                # The picker has no useful row for an endpoint with no cached
                # or pinned models. The Settings panel still exposes it for a
                # manual refresh/probe.
                continue

            curated_key = _match_provider_curated(base_url, None)
            models, extra = _curate_models(model_ids, curated_key)
            # Explicitly pinned models are the user's allow-list and must stay
            # in the primary section rather than being buried as extras.
            for model_id in pinned:
                if model_id not in models:
                    models.append(model_id)
            extra = [model_id for model_id in extra if model_id not in pinned]

            items.append({
                "host": "custom",
                "port": 0,
                "url": build_chat_url(base_url),
                "models": models,
                "models_display": [_model_display_name(model_id) for model_id in models],
                "models_extra": extra,
                "models_extra_display": [_model_display_name(model_id) for model_id in extra],
                "endpoint_id": endpoint_id,
                "endpoint_name": getattr(endpoint, "name", None) or endpoint_id,
                "category": _classify_endpoint(base_url, endpoint_kind),
                "endpoint_kind": endpoint_kind,
                "model_type": getattr(endpoint, "model_type", None) or "llm",
                "supports_tools": getattr(endpoint, "supports_tools", None),
            })
    except Exception as exc:
        logger.warning("Failed to build configured model catalog: %s", exc)
    finally:
        db.close()
    return items


def _configured_default_chat(request: Request) -> Optional[Dict[str, Any]]:
    """Resolve the Odysseus default endpoint/model for the compatibility API."""
    try:
        from core.database import ModelEndpoint, SessionLocal
        from src.auth_helpers import effective_user, owner_filter
        from src.endpoint_resolver import build_chat_url
        from src.settings import load_settings
        from routes.model_routes import (
            _effective_endpoint_kind,
            _model_display_name,
            _normalize_base,
            _picker_models_for_endpoint,
        )
    except Exception as exc:
        logger.debug("Configured default model unavailable: %s", exc)
        return None

    try:
        owner = effective_user(request) or ""
    except Exception:
        owner = ""
    settings = load_settings() or {}
    endpoint_id = str(settings.get("default_endpoint_id") or "").strip()
    model_id = _canonical_model(settings.get("default_model"))

    # In authenticated multi-user mode, use a personal default when present;
    # the global default is inherited only when the operator enabled sharing.
    is_admin = False
    try:
        auth_manager = getattr(request.app.state, "auth_manager", None)
        if owner and auth_manager is not None and getattr(auth_manager, "is_admin", None):
            is_admin = bool(auth_manager.is_admin(owner))
    except Exception:
        is_admin = False
    if owner and not is_admin:
        try:
            from routes.prefs_routes import _load_for_user
            prefs = _load_for_user(owner) or {}
            personal_endpoint = str(prefs.get("default_endpoint_id") or "").strip()
            personal_model = _canonical_model(prefs.get("default_model"))
            if personal_endpoint:
                endpoint_id = personal_endpoint
            if personal_model:
                model_id = personal_model
            if not settings.get("share_defaults_with_users", False):
                if not personal_endpoint:
                    endpoint_id = ""
                if not personal_model:
                    model_id = ""
        except Exception:
            pass

    if not endpoint_id:
        return None

    db = SessionLocal()
    try:
        query = db.query(ModelEndpoint).filter(
            ModelEndpoint.id == endpoint_id,
            ModelEndpoint.is_enabled == True,  # noqa: E712
        )
        if owner and not is_admin:
            query = owner_filter(query, ModelEndpoint, owner)
        endpoint = query.first()
        if endpoint is None or str(getattr(endpoint, "id", "")) in _LEGACY_COMPANION_ENDPOINT_IDS:
            return None

        base_url = _normalize_base(getattr(endpoint, "base_url", "") or "")
        if not base_url:
            return None
        endpoint_kind = _effective_endpoint_kind(endpoint, base_url)
        visible, _ = _picker_models_for_endpoint(endpoint, base_url, endpoint_kind)
        if not model_id or (visible and model_id not in visible):
            model_id = visible[0] if visible else ""
        if not model_id:
            return None
        return {
            "endpoint_id": endpoint.id,
            "endpoint_name": getattr(endpoint, "name", None) or endpoint.id,
            "endpoint_url": build_chat_url(base_url),
            "model": model_id,
            "model_display": _model_display_name(model_id),
            "provider": getattr(endpoint, "name", None) or "configured",
        }
    except Exception as exc:
        logger.debug("Failed to resolve configured default model: %s", exc)
        return None
    finally:
        db.close()


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

    @app.get("/api/conversation-config")
    async def get_conversation_config():
        """Return the shared text model/persona selection.

        The model picker and the Live client can run on different frontend
        origins, so localStorage alone is not a reliable hand-off. This small
        server-side config contains text routing and response-language
        preferences; prompts and provider secrets remain in Odysseus' stores.
        """
        from backend.core.settings_store import SETTINGS

        return {
            "text_model": _canonical_model(SETTINGS.get("text_model") or DEFAULT_TEXT_MODEL),
            "text_endpoint_id": str(SETTINGS.get("text_endpoint_id") or "gemini-text").strip(),
            "text_persona_id": str(SETTINGS.get("text_persona_id") or "monika").strip(),
            "response_language": str(SETTINGS.get("response_language") or "auto").strip().lower(),
        }

    @app.patch("/api/conversation-config")
    async def update_conversation_config(req: ConversationConfigRequest):
        """Persist text routing independently from voice transport settings."""
        from backend.core.settings_store import SETTINGS, save_settings

        changed = False
        for key in ("text_model", "text_endpoint_id", "text_persona_id", "response_language"):
            value = getattr(req, key)
            if value is None:
                continue
            normalized = str(value).strip()
            if not normalized:
                continue
            if len(normalized) > 256:
                raise HTTPException(status_code=400, detail=f"{key} is too long")
            if key == "text_model":
                normalized = _canonical_model(normalized)
            if key == "response_language":
                from backend.core.response_language import normalize_response_language

                requested_language = str(value or "").strip().lower()
                if requested_language not in {"auto", "en", "pl", "zh", "ja"}:
                    raise HTTPException(status_code=400, detail="Unsupported response_language")
                normalized = normalize_response_language(requested_language)
            if SETTINGS.get(key) != normalized:
                SETTINGS[key] = normalized
                changed = True
        if changed:
            save_settings()
            if req.response_language is not None:
                try:
                    from backend.core.runtimes.v2_runtime import get as get_v2_runtime

                    runtime = get_v2_runtime()
                    if runtime is not None:
                        await runtime.refresh_prompt()
                except Exception:
                    logger.debug("Unable to refresh v2 prompt after language change", exc_info=True)
        return {
            "ok": True,
            "text_model": _canonical_model(SETTINGS.get("text_model") or DEFAULT_TEXT_MODEL),
            "text_endpoint_id": str(SETTINGS.get("text_endpoint_id") or "gemini-text").strip(),
            "text_persona_id": str(SETTINGS.get("text_persona_id") or "monika").strip(),
            "response_language": str(SETTINGS.get("response_language") or "auto").strip().lower(),
        }

    @app.get("/api/models")
    async def get_models(request: Request, refresh: bool = False, background: bool = False):
        # Keep the two built-in aliases for compatibility, then append the
        # authoritative Odysseus endpoint catalog.  Previously this handler
        # returned only the hard-coded aliases, so models selected in the
        # Odysseus Settings panel could never reach the chat picker.
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

        configured_items = _configured_model_items(request)
        existing_endpoint_ids = {item.get("endpoint_id") for item in items}
        items.extend(
            item for item in configured_items
            if item.get("endpoint_id") not in existing_endpoint_ids
        )

        configured_default = _configured_default_chat(request)

        return {
            "ok": True,
            "items": items,
            "models": [model for item in items for model in item.get("models", [])],
            "default_model": (
                configured_default.get("model")
                if configured_default
                else DEFAULT_TEXT_MODEL
            ),
        }

    @app.get("/api/default-chat")
    async def get_default_chat(request: Request):
        configured_default = _configured_default_chat(request)
        if configured_default:
            return configured_default
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
