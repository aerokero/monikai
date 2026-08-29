"""HTTP API routes for Odysseus Deep Research Engine."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from pydantic import BaseModel

from backend.agents.deep_research import get_deep_research_engine


class ResearchStartRequest(BaseModel):
    topic: str
    depth: Optional[str] = "standard"  # "quick", "standard", "deep"


def register_research_http_routes(app, emit_to_frontend=None):
    @app.post("/api/v1/research/start")
    async def start_research(req: ResearchStartRequest):
        if not req.topic.strip():
            raise HTTPException(status_code=400, detail="Temat badania nie może być pusty")

        engine = get_deep_research_engine()

        async def _progress_callback(task):
            if emit_to_frontend:
                try:
                    await emit_to_frontend(
                        "research_progress",
                        {
                            "task_id": task.task_id,
                            "topic": task.topic,
                            "status": task.status,
                            "progress": task.progress,
                            "current_step": task.current_step,
                            "sources_count": len(task.sources),
                            "cost": asdict(task.cost_tracker),
                        },
                    )
                except Exception:
                    pass

        # Run in background asyncio task
        task_future = asyncio.create_task(
            engine.execute_research(
                topic=req.topic,
                depth=req.depth or "standard",
                on_progress=_progress_callback,
            )
        )

        return {
            "ok": True,
            "message": "Rozpoczęto zadanie Deep Research",
            "topic": req.topic,
            "depth": req.depth,
        }

    @app.get("/api/v1/research/status/{task_id}")
    async def get_research_status(task_id: str):
        engine = get_deep_research_engine()
        task = engine.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Zadanie badania nie zostało znalezione")
        return {
            "ok": True,
            "task": asdict(task),
        }

    @app.get("/api/v1/research/report/{task_id}")
    async def get_research_report(task_id: str):
        engine = get_deep_research_engine()
        task = engine.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Zadanie badania nie zostało znalezione")
        if task.status != "completed":
            return {
                "ok": False,
                "status": task.status,
                "progress": task.progress,
                "current_step": task.current_step,
                "message": "Raport nie jest jeszcze gotowy",
            }
        return {
            "ok": True,
            "task_id": task.task_id,
            "topic": task.topic,
            "report_markdown": task.report_markdown,
            "sources": task.sources,
            "duration_s": task.duration_s,
            "cost": asdict(task.cost_tracker),
        }

    @app.get("/api/v1/research/list")
    async def list_research_tasks():
        engine = get_deep_research_engine()
        tasks = engine.list_tasks()
        return {
            "status": "ok",
            "count": len(tasks),
            "tasks": [
                {
                    "task_id": t.task_id,
                    "topic": t.topic,
                    "depth": t.depth,
                    "status": t.status,
                    "progress": t.progress,
                    "created_at": t.created_at,
                    "completed_at": t.completed_at,
                    "duration_s": t.duration_s,
                }
                for t in tasks
            ],
        }
