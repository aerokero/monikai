import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models.model_router import (
    LLMMessage,
    LLMResponse,
    LLMUsage,
    LLMProvider,
    ModelRouter,
    OllamaProvider,
    OpenRouterProvider,
    get_model_router,
)
from backend.core.routers.models_http_router import register_models_http_routes


class MockProvider(LLMProvider):
    name = "mock_provider"

    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.call_count = 0

    async def complete(self, messages, model=None, temperature=0.7, max_tokens=None, response_format=None, timeout_s=60.0):
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Mock provider simulated failure")
        return LLMResponse(
            content=f"Mock response to: {messages[-1].content}",
            model=model or "mock-model-v1",
            provider=self.name,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=42.0,
        )

    async def stream(self, messages, model=None, temperature=0.7, max_tokens=None, timeout_s=60.0):
        yield "Mock "
        yield "stream "
        yield "token"

    async def health(self):
        return {"ok": not self.should_fail, "provider": self.name, "models": ["mock-model-v1"]}


@pytest.mark.asyncio
async def test_model_router_complete_and_task_routing():
    router = ModelRouter()
    mock_p1 = MockProvider()
    mock_p2 = MockProvider()
    mock_p2.name = "mock_research"

    router.register_provider(mock_p1)
    router.register_provider(mock_p2)
    router.set_default_provider("mock_provider")
    router.set_task_provider("research", "mock_research")

    # Complete using default
    resp = await router.complete(
        messages=[LLMMessage(role="user", content="Hello")],
        task="agent",
    )
    assert resp.provider == "mock_provider"
    assert "Hello" in resp.content
    assert mock_p1.call_count == 1

    # Complete using task routing
    resp_research = await router.complete(
        messages=[{"role": "user", "content": "Research query"}],
        task="research",
    )
    assert resp_research.provider == "mock_research"
    assert mock_p2.call_count == 1


@pytest.mark.asyncio
async def test_model_router_fallback():
    router = ModelRouter()
    failing_p = MockProvider(should_fail=True)
    failing_p.name = "failing_primary"
    backup_p = MockProvider(should_fail=False)
    backup_p.name = "backup_provider"

    router.register_provider(failing_p)
    router.register_provider(backup_p)

    resp = await router.complete(
        messages=[LLMMessage(role="user", content="Test fallback")],
        provider_name="failing_primary",
        fallback_providers=["backup_provider"],
    )
    assert resp.provider == "backup_provider"
    assert failing_p.call_count == 1
    assert backup_p.call_count == 1


@pytest.mark.asyncio
async def test_model_router_streaming():
    router = ModelRouter()
    mock_p = MockProvider()
    router.register_provider(mock_p)
    router.set_default_provider("mock_provider")

    chunks = []
    async for token in router.stream(
        messages=[LLMMessage(role="user", content="Stream test")],
        provider_name="mock_provider",
    ):
        chunks.append(token)

    assert "".join(chunks) == "Mock stream token"


def test_models_http_endpoints():
    app = FastAPI()
    register_models_http_routes(app)
    client = TestClient(app)

    res = client.get("/api/v1/models")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "default_provider" in data
    assert "providers" in data

    # Test select endpoint
    select_res = client.post(
        "/api/v1/models/select",
        json={"task": "research", "provider": "ollama"},
    )
    assert select_res.status_code == 200
    assert select_res.json()["ok"] is True
