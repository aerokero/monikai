"""Odysseus API Router - Bridges Odysseus UI frontend with MonikAI + ModelRouter engine."""

from __future__ import annotations

import asyncio
import json
import logging
import os
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
        model = form_data.get("selected_model") or form_data.get("model", "monika-companion")
        custom_system_prompt = form_data.get("custom_system_prompt") or form_data.get("system_prompt") or form_data.get("persona_prompt") or ""
        temperature_raw = form_data.get("temperature") or form_data.get("temp") or 0.8
        try:
            temperature = float(temperature_raw)
        except Exception:
            temperature = 0.8

        async def event_generator():
            router = get_model_router()
            response_text = "Jestem tutaj z Tobą i słucham! ✨"

            try:
                # Load Monika's authentic system prompt with lore, memories, and integrations
                from backend.core.system_prompt import current_system_prompt
                from backend.conversation.providers import GeminiTextProvider, TextGenerationRequest
                
                base_prompt = current_system_prompt()
                if custom_system_prompt and custom_system_prompt.strip():
                    system_prompt = f"{base_prompt}\n\n[AKTYWNA PERSONA / INSTRUKCJA SPECJALNA]:\n{custom_system_prompt.strip()}"
                else:
                    system_prompt = base_prompt

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

                full_user_prompt = f"Historia rozmowy:\n{past_context}\nUżytkownik: {prompt}" if past_context else prompt

                # Generate from Gemini AI or ModelRouter
                if prompt.strip():
                    gemini_api_key = os.getenv("GEMINI_API_KEY")
                    if gemini_api_key:
                        try:
                            gemini_provider = GeminiTextProvider(api_key=gemini_api_key)
                            req = TextGenerationRequest(
                                model="gemini-2.5-flash",
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
                                    {"role": "user", "content": prompt}
                                ],
                                task="chat",
                                model=model,
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
                        sess_row.message_count = (sess_row.message_count or 0) + 2

                        clean_title = prompt.strip().replace("\n", " ")
                        if clean_title and (not sess_row.name or sess_row.name in ("Monika Chat", "Nobody", "New Chat") or sess_row.name.startswith("New Chat")):
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
