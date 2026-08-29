import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models.model_router import (
    LLMMessage,
    LLMResponse,
    LLMUsage,
    LLMProvider,
    get_model_router,
)
from backend.services.docs_service import DocsService, get_docs_service
from backend.services.email_service import EmailService, get_email_service
from backend.core.routers.workspace_http_router import register_workspace_http_routes


class MockDocsLLMProvider(LLMProvider):
    name = "mock_docs_llm"

    async def complete(self, messages, model=None, temperature=0.7, max_tokens=None, response_format=None, timeout_s=60.0):
        return LLMResponse(
            content='{"proposed_content": "# Raport zaktualizowany\\n\\nNowa treść z naniesionymi poprawkami.", "explanation": "Dodano zaktualizowany nagłówek i nową treść."}',
            model="mock-docs-v1",
            provider=self.name,
            usage=LLMUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
        )

    async def stream(self, messages, model=None, temperature=0.7, max_tokens=None, timeout_s=60.0):
        yield "token"

    async def health(self):
        return {"ok": True, "provider": self.name, "models": ["mock-docs-v1"]}


@pytest.mark.asyncio
async def test_docs_service_crud_and_ai_diff(tmp_path: Path):
    router = get_model_router()
    mock_p = MockDocsLLMProvider()
    router.register_provider(mock_p)
    router.set_default_provider("mock_docs_llm")

    service = DocsService(data_dir=tmp_path)
    
    # 1. Create doc
    doc = service.create_document(title="Plan Projektu", content="# Plan Projektu\n\nPoczątkowa treść.")
    assert doc.id is not None
    assert doc.title == "Plan Projektu"
    assert len(service.list_documents()) == 1

    # 2. AI Propose Edit
    diff = await service.propose_ai_edit(doc.id, instruction="Zaktualizuj nagłówek i treść")
    assert diff is not None
    assert diff.additions > 0
    assert "zaktualizowany" in diff.proposed_content
    assert doc.pending_diff is not None

    # 3. Accept Diff
    updated_doc = service.accept_pending_diff(doc.id)
    assert updated_doc is not None
    assert updated_doc.content == diff.proposed_content
    assert len(updated_doc.revisions) == 2
    assert updated_doc.pending_diff is None


@pytest.mark.asyncio
async def test_email_service_draft_first(tmp_path: Path):
    service = EmailService(data_dir=tmp_path)

    # 1. Create draft (strictly pending approval)
    draft = service.create_draft(
        to="bartosz@example.com",
        subject="Spotkanie projektowe MonikAI",
        body="Cześć! Przygotowałem podsumowanie prac nad Odysseuszem.",
    )
    assert draft.id is not None
    assert draft.status == "pending_approval"
    assert len(service.list_drafts(status="pending_approval")) == 1

    # 2. Approve and send
    result = await service.approve_and_send(draft.id)
    assert result["ok"] is True
    assert draft.status == "sent"
    assert draft.sent_at is not None


def test_workspace_http_endpoints():
    app = FastAPI()
    register_workspace_http_routes(app)
    client = TestClient(app)

    # Docs endpoints
    docs_res = client.get("/api/v1/docs/list")
    assert docs_res.status_code == 200
    assert "documents" in docs_res.json()

    create_res = client.post("/api/v1/docs/create", json={"title": "Notatka testowa", "content": "Test"})
    assert create_res.status_code == 200
    doc_id = create_res.json()["document"]["id"]

    get_res = client.get(f"/api/v1/docs/get/{doc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["document"]["title"] == "Notatka testowa"

    # Email endpoints
    draft_res = client.post(
        "/api/v1/email/drafts/create",
        json={"to": "test@test.com", "subject": "Temat", "body": "Treść"},
    )
    assert draft_res.status_code == 200
    draft_id = draft_res.json()["draft"]["id"]

    approve_res = client.post(f"/api/v1/email/drafts/approve/{draft_id}")
    assert approve_res.status_code == 200
    assert approve_res.json()["ok"] is True
