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
    async def get_models():
        router = get_model_router()
        status = router.get_status()
        providers = status.get("providers", {})
        
        models_list = []
        for p_name, p_data in providers.items():
            for m in p_data.get("models", []):
                models_list.append({
                    "id": m,
                    "name": f"{m} ({p_name})",
                    "provider": p_name,
                    "active": m == status.get("active_models", {}).get("agent"),
                })
        
        # Add Gemini native
        models_list.append({"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash (Monika Native)", "provider": "gemini", "active": True})
        models_list.append({"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro (Deep Reasoner)", "provider": "gemini", "active": False})

        return {
            "ok": True,
            "models": models_list,
            "default_model": "gemini-2.5-flash",
            "active_model": status.get("active_models", {}).get("agent", "gemini-2.5-flash"),
        }

    @app.get("/api/sessions")
    async def list_sessions():
        return list(_SESSIONS.values())

    @app.post("/api/sessions")
    async def create_session(req: Request):
        body = await req.json() if req.headers.get("content-type") == "application/json" else {}
        session_id = f"sess_{int(time.time()*1000)}"
        title = body.get("title", "Nowa sesja")
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
        return {"ok": True, "session": _SESSIONS[session_id]}

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
        session_id = form_data.get("session_id", "default")
        model = form_data.get("model", "gemini-2.5-flash")

        async def event_generator():
            router = get_model_router()
            
            # Send start event
            yield f"data: {json.dumps({'event': 'start', 'session_id': session_id})}\n\n"

            # Check if this requires thinking or deep agent execution
            try:
                # Stream response from model router or fallback
                full_text = ""
                # Stream token-by-token
                response_text = f"Cześć! Otrzymałam Twoją wiadomość: \"{prompt}\". Pracuję z Tobą w zunifikowanym Odysseus AI Workspace!"
                
                # If router is active with a real model, run complete query
                if "gemini" not in model.lower() and router:
                    try:
                        res = await router.complete(
                            task="agent",
                            prompt=prompt,
                            system="Jesteś Moniką z Doki Doki Literature Club, prowadzącą zaawansowany Odysseus AI Workspace. Odpowiadaj z ciepłem, inteligencją i gotowością do pomocy.",
                        )
                        response_text = res.get("text", response_text)
                    except Exception as e:
                        logger.warning(f"ModelRouter completion fallback: {e}")

                words = response_text.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'event': 'token', 'token': chunk})}\n\n"
                    await asyncio.sleep(0.02)

                # Send finalize event
                yield f"data: {json.dumps({'event': 'done', 'full_text': response_text})}\n\n"

            except Exception as err:
                yield f"data: {json.dumps({'event': 'error', 'error': str(err)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

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
