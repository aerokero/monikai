"""HTTP routes for Model Router and Provider Hub in MonikAI Workspace."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import HTTPException
from pydantic import BaseModel

from backend.models.model_router import LLMMessage, get_model_router


class ModelSelectRequest(BaseModel):
    task: Optional[str] = "agent"  # "agent", "research", "chat", "digest", "default"
    provider: str
    model: Optional[str] = None


class ModelTestRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt: str = "Odpowiedz krótko: Czy działasz poprawnie?"


def register_models_http_routes(app):
    @app.get("/api/v1/models")
    async def list_models():
        router = get_model_router()
        health_info = await router.health_all()
        return {
            "status": "ok",
            "default_provider": health_info.get("default_provider"),
            "task_routing": health_info.get("task_routing"),
            "providers": health_info.get("providers"),
        }

    @app.post("/api/v1/models/select")
    async def select_model(req: ModelSelectRequest):
        router = get_model_router()
        if req.task == "default":
            success = router.set_default_provider(req.provider)
        else:
            success = router.set_task_provider(req.task or "agent", req.provider)

        if not success:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")

        return {"ok": True, "task": req.task, "provider": req.provider}

    @app.post("/api/v1/models/test")
    async def test_model(req: ModelTestRequest):
        router = get_model_router()
        try:
            resp = await router.complete(
                messages=[LLMMessage(role="user", content=req.prompt)],
                provider_name=req.provider,
                model=req.model,
                timeout_s=30.0,
            )
            return {
                "ok": True,
                "provider": resp.provider,
                "model": resp.model,
                "content": resp.content,
                "latency_ms": round(resp.latency_ms, 2),
                "tokens": resp.usage.total_tokens,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
