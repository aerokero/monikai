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
