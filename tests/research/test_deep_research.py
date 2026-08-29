import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models.model_router import (
    LLMMessage,
    LLMResponse,
    LLMUsage,
    LLMProvider,
    get_model_router,
)
from backend.services.search_service import SearchResult, SearchService
from backend.agents.deep_research import DeepResearchEngine, get_deep_research_engine
from backend.core.routers.research_http_router import register_research_http_routes


class MockResearchLLMProvider(LLMProvider):
    name = "mock_research_llm"

    async def complete(self, messages, model=None, temperature=0.7, max_tokens=None, response_format=None, timeout_s=60.0):
        prompt = messages[-1].content
        if "subqueries" in prompt.lower() or (response_format and response_format.get("type") == "json_object"):
            return LLMResponse(
                content='{"subqueries": ["architektura odyseusza", "monikai visual novel", "deep research benchmark"]}',
                model="mock-research-v1",
                provider=self.name,
                usage=LLMUsage(prompt_tokens=50, completion_tokens=30, total_tokens=80, estimated_cost_usd=0.0002),
            )
        return LLMResponse(
            content=(
                "# Raport Badawczy: Fuzja MonikAI i Odysseus AI\n\n"
                "## Podsumowanie Wykonawcze\nFuzja przebiega pomyślnie z pełnym zachowaniem VN i MCP [1].\n\n"
                "## Kluczowe Odkrycia\n- Protokół MCP zapewnia modularność narzędzi [2].\n\n"
                "## Bibliografia\n[1] https://odysseusai.dev\n[2] https://modelcontextprotocol.io\n"
            ),
            model="mock-research-v1",
            provider=self.name,
            usage=LLMUsage(prompt_tokens=200, completion_tokens=150, total_tokens=350, estimated_cost_usd=0.001),
        )

    async def stream(self, messages, model=None, temperature=0.7, max_tokens=None, timeout_s=60.0):
        yield "token"

    async def health(self):
        return {"ok": True, "provider": self.name, "models": ["mock-research-v1"]}


@pytest.mark.asyncio
async def test_deep_research_engine(tmp_path: Path):
    router = get_model_router()
    mock_p = MockResearchLLMProvider()
    router.register_provider(mock_p)
    router.set_task_provider("research", "mock_research_llm")

    engine = DeepResearchEngine(data_dir=tmp_path)

    # Mock search service to avoid external internet calls during unit tests
    mock_search = AsyncMock()
    mock_search.search.return_value = [
        SearchResult(title="Odysseus AI Docs", url="https://odysseusai.dev/docs", snippet="Self hosted AI workspace"),
        SearchResult(title="Model Context Protocol", url="https://modelcontextprotocol.io", snippet="Standard protocol for AI tools"),
    ]
    engine.search_service = mock_search

    # Mock scraping
    engine._scrape_url = AsyncMock(return_value="To jest przykładowa treść strony internetowej na temat AI workspace.")

    progress_history = []
    task = await engine.execute_research(
        topic="Integracja MonikAI i Odysseus",
        depth="standard",
        on_progress=lambda t: progress_history.append(t.progress),
    )

    assert task.status == "completed"
    assert task.progress == 1.0
    assert task.report_markdown is not None
    assert "Raport Badawczy" in task.report_markdown
    assert len(task.subqueries) == 3
    assert len(task.sources) >= 2
    assert task.cost_tracker.total_tokens > 0
    assert task.cost_tracker.estimated_cost_usd > 0.0


def test_research_http_endpoints():
    app = FastAPI()
    register_research_http_routes(app)
    client = TestClient(app)

    # List tasks
    res = client.get("/api/v1/research/list")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "tasks" in data

    # Start research (with mock engine)
    start_res = client.post("/api/v1/research/start", json={"topic": "Test Topic", "depth": "quick"})
    assert start_res.status_code == 200
    assert start_res.json()["ok"] is True
