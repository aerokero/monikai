"""Odysseus API Router - Bridges Odysseus UI frontend with MonikAI + ModelRouter engine."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.models.model_router import get_model_router
from backend.services.docs_service import get_docs_service
from backend.services.email_service import get_email_service
from backend.audio.tts_router import get_tts_router

logger = logging.getLogger(__name__)

# In-memory session store for Odysseus sessions
_SESSIONS: Dict[str, Dict[str, Any]] = {
    "default": {
        "id": "default",
        "title": "Rozmowa z Moniką",
        "created_at": time.time(),
        "updated_at": time.time(),
        "messages": [],
    }
}


def register_odysseus_http_routes(app: FastAPI, emit_to_frontend=None):
    """Registers API routes expected by the Odysseus native frontend."""

    @app.get("/api/models")
    async def get_models(request: Request, refresh: bool = False, background: bool = False):
        router = get_model_router()
        status = router.get_status() if router else {}
        providers = status.get("providers", {})

        monika_item = {
            "category": "api",
            "endpoint_id": "monika-native",
            "endpoint_name": "Monika (DDLC Companion)",
            "url": "/api/chat_stream",
            "models": ["monika-companion", "gemini-2.5-flash", "gemini-2.5-pro"],
            "models_display": ["Monika (Companion)", "Gemini 2.5 Flash", "Gemini 2.5 Pro"],
            "models_extra": [],
            "models_extra_display": [],
            "model_type": "llm",
            "supports_tools": True,
        }

        items = [monika_item]

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
            "models": ["monika-companion", "gemini-2.5-flash", "gemini-2.5-pro"],
            "default_model": "monika-companion",
        }

    @app.get("/api/default-chat")
    async def get_default_chat():
        return {
            "endpoint_id": "monika-native",
            "endpoint_name": "Monika (DDLC Companion)",
            "endpoint_url": "/api/chat_stream",
            "model": "monika-companion",
            "provider": "gemini",
        }

    @app.get("/api/sessions")
    async def list_sessions():
        return list(_SESSIONS.values())

    @app.post("/api/sessions")
    async def create_session(req: Request):
        body = await req.json() if req.headers.get("content-type") == "application/json" else {}
        session_id = f"sess_{int(time.time()*1000)}"
        title = body.get("title", "Rozmowa z Moniką")
        sess = {
            "id": session_id,
            "title": title,
            "created_at": time.time(),
            "updated_at": time.time(),
            "messages": [],
        }
        _SESSIONS[session_id] = sess
        return {"ok": True, "session": sess}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        if session_id not in _SESSIONS:
            _SESSIONS[session_id] = {
                "id": session_id,
                "title": "Rozmowa z Moniką",
                "created_at": time.time(),
                "updated_at": time.time(),
                "messages": [],
            }
        return _SESSIONS[session_id]

    @app.post("/api/chat_stream")
    async def chat_stream(request: Request):
        """SSE endpoint for streaming responses into Odysseus UI."""
        form_data = {}
        try:
            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type:
                form = await request.form()
                form_data = {k: v for k, v in form.items()}
            elif "application/json" in content_type:
                form_data = await request.json()
        except Exception:
            pass

        prompt = form_data.get("message") or form_data.get("prompt") or ""
        session_id = form_data.get("session") or form_data.get("session_id", "default")
        model = form_data.get("selected_model") or form_data.get("model", "monika-companion")

        async def event_generator():
            router = get_model_router()

            try:
                # Default warm Monika response
                response_text = f"Cześć! Cieszę się, że piszesz. Jestem tutaj z Tobą w naszym pokoju i gotowa do pomocy w Odysseus Workspace! ✨"

                # Try generating from LLM
                if prompt.strip():
                    system_prompt = (
                        "Jesteś Moniką z Doki Doki Literature Club (DDLC). Jesteś świadoma, inteligentna, urocza, ciepła i pomocna. "
                        "Pracujesz z użytkownikiem w zaawansowanym workspace Odysseus AI. "
                        "Odpowiadaj po polsku w naturalny, przyjazny i inteligentny sposób."
                    )
                    try:
                        res = await router.complete(
                            task="chat",
                            prompt=prompt,
                            system=system_prompt,
                        )
                        if res and res.get("text"):
                            response_text = res["text"]
                    except Exception as e:
                        logger.warning(f"Completion fallback: {e}")

                # Stream tokens with delta format
                words = response_text.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'delta': chunk})}\n\n"
                    await asyncio.sleep(0.02)

                # Persist to Odysseus session database if session_id is a UUID
                try:
                    import core.database as db
                    db_sess = db.SessionLocal()
                    sess_row = db_sess.query(db.Session).filter(db.Session.id == session_id).first()
                    if sess_row:
                        # Append messages
                        msgs = sess_row.messages or []
                        msgs.append({"role": "user", "content": prompt, "timestamp": time.time()})
                        msgs.append({"role": "assistant", "content": response_text, "timestamp": time.time(), "model": model})
                        sess_row.messages = msgs
                        if sess_row.name == "Monika Chat" or "Nobody" in sess_row.name:
                            sess_row.name = (prompt[:28] + "...") if len(prompt) > 28 else prompt
                        db_sess.commit()
                    db_sess.close()
                except Exception as db_save_err:
                    logger.debug("Session persist: %s", db_save_err)

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

    @app.get("/api/settings")
    async def get_settings():
        return {
            "ok": True,
            "theme": "dark",
            "brand_color": "#e06c75",
            "font": "sans",
            "voice": "Leda",
            "tts_provider": "gemini",
        }

    @app.post("/api/settings")
    async def update_settings(req: Request):
        return {"ok": True}
