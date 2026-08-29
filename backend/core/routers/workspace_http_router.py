"""HTTP API endpoints for Workspace Docs, Email, and Calendar."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from pydantic import BaseModel

from backend.services.docs_service import get_docs_service
from backend.services.email_service import get_email_service


class CreateDocRequest(BaseModel):
    title: str
    content: Optional[str] = ""
    filename: Optional[str] = None


class UpdateDocRequest(BaseModel):
    content: str
    commit_message: Optional[str] = "Edycja użytkownika"


class AIEditDocRequest(BaseModel):
    instruction: str


class CreateDraftRequest(BaseModel):
    to: str
    subject: str
    body: str


def register_workspace_http_routes(app, get_calendar_manager=None, emit_to_frontend=None):
    # -------------------------------------------------------------
    # DOCS ENDPOINTS
    # -------------------------------------------------------------
    @app.get("/api/v1/docs/list")
    async def list_docs():
        docs_svc = get_docs_service()
        return {"status": "ok", "documents": docs_svc.list_documents()}

    @app.post("/api/v1/docs/create")
    async def create_doc(req: CreateDocRequest):
        docs_svc = get_docs_service()
        doc = docs_svc.create_document(title=req.title, content=req.content or "", filename=req.filename)
        return {"ok": True, "document": asdict(doc)}

    @app.get("/api/v1/docs/get/{doc_id}")
    async def get_doc(doc_id: str):
        docs_svc = get_docs_service()
        doc = docs_svc.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Dokument nie został znaleziony")
        return {"ok": True, "document": asdict(doc)}

    @app.post("/api/v1/docs/update/{doc_id}")
    async def update_doc(doc_id: str, req: UpdateDocRequest):
        docs_svc = get_docs_service()
        doc = docs_svc.update_document(doc_id, content=req.content, commit_message=req.commit_message or "Edycja")
        if not doc:
            raise HTTPException(status_code=404, detail="Dokument nie został znaleziony")
        return {"ok": True, "document": asdict(doc)}

    @app.post("/api/v1/docs/ai_edit/{doc_id}")
    async def ai_edit_doc(doc_id: str, req: AIEditDocRequest):
        docs_svc = get_docs_service()
        diff = await docs_svc.propose_ai_edit(doc_id, instruction=req.instruction)
        if not diff:
            raise HTTPException(status_code=404, detail="Dokument nie został znaleziony")
        return {"ok": True, "diff": asdict(diff)}

    @app.post("/api/v1/docs/accept_diff/{doc_id}")
    async def accept_diff(doc_id: str):
        docs_svc = get_docs_service()
        doc = docs_svc.accept_pending_diff(doc_id)
        if not doc:
            raise HTTPException(status_code=400, detail="Brak oczekującego diffa dla tego dokumentu")
        return {"ok": True, "document": asdict(doc)}

    @app.post("/api/v1/docs/reject_diff/{doc_id}")
    async def reject_diff(doc_id: str):
        docs_svc = get_docs_service()
        ok = docs_svc.reject_pending_diff(doc_id)
        return {"ok": ok}

    # -------------------------------------------------------------
    # EMAIL ENDPOINTS (DRAFT-FIRST)
    # -------------------------------------------------------------
    @app.get("/api/v1/email/drafts")
    async def list_drafts(status: Optional[str] = None):
        email_svc = get_email_service()
        return {"status": "ok", "drafts": email_svc.list_drafts(status=status)}

    @app.post("/api/v1/email/drafts/create")
    async def create_draft(req: CreateDraftRequest):
        email_svc = get_email_service()
        draft = email_svc.create_draft(to=req.to, subject=req.subject, body=req.body)
        if emit_to_frontend:
            try:
                await emit_to_frontend(
                    "email_draft_created",
                    {"draft": asdict(draft), "message": f"Wymagane potwierdzenie wysłania maila do {req.to}"},
                )
            except Exception:
                pass
        return {"ok": True, "draft": asdict(draft)}

    @app.post("/api/v1/email/drafts/approve/{draft_id}")
    async def approve_draft(draft_id: str):
        email_svc = get_email_service()
        res = await email_svc.approve_and_send(draft_id)
        return res

    @app.post("/api/v1/email/drafts/reject/{draft_id}")
    async def reject_draft(draft_id: str):
        email_svc = get_email_service()
        ok = email_svc.reject_draft(draft_id)
        return {"ok": ok}
