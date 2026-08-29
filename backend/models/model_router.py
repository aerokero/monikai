"""Unified Model Router for MonikAI Workspace.

Supports:
- Local models via Ollama and OpenAI-compatible servers (vLLM, llama.cpp, LM Studio).
- Cloud providers: OpenRouter, Anthropic, OpenAI, Google Gemini.
- Task-based routing (agent, research, digest, chat).
- Usage/cost tracking and fallback providers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant"
    content: str
    name: Optional[str] = None


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: float = 0.0
    raw: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    """Abstract base provider for LLM inference."""

    name: str

    @abstractmethod
    async def complete(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        pass


class OllamaProvider(LLMProvider):
    """Provider for local Ollama server."""

    name = "ollama"

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self.base_url = (base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.default_model = default_model or os.environ.get("MONIKAI_OLLAMA_MODEL", "qwen2.5:7b")
        self._client: Optional[httpx.AsyncClient] = None

    def _http(self, timeout: float = 60.0) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(timeout, connect=5.0),
            )
        return self._client

    async def complete(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"

        start_t = time.perf_counter()
        resp = await self._http(timeout_s).post("/api/chat", json=payload, timeout=timeout_s)
        resp.raise_for_status()
        latency_ms = (time.perf_counter() - start_t) * 1000.0

        data = resp.json()
        content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        return LLMResponse(
            content=content,
            model=target_model,
            provider=self.name,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated_cost_usd=0.0,  # Local
            ),
            latency_ms=latency_ms,
            raw=data,
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        async with httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout_s, connect=5.0)) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk_json = json.loads(line)
                        chunk_text = chunk_json.get("message", {}).get("content", "")
                        if chunk_text:
                            yield chunk_text
                    except Exception:
                        continue

    async def health(self) -> Dict[str, Any]:
        try:
            resp = await self._http(5.0).get("/api/tags", timeout=5.0)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            return {
                "ok": True,
                "provider": self.name,
                "models": models,
                "default_model": self.default_model,
            }
        except Exception as e:
            return {"ok": False, "provider": self.name, "error": str(e), "models": []}


class OpenRouterProvider(LLMProvider):
    """Provider for OpenRouter (Claude, DeepSeek, GPT-4o, Llama)."""

    name = "openrouter"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.default_model = default_model or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.7-sonnet")
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://monikai.dev",
            "X-Title": "MonikAI Workspace",
            "Content-Type": "application/json",
        }

    async def complete(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("OpenRouter API key is not configured")

        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        start_t = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=10.0)) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            latency_ms = (time.perf_counter() - start_t) * 1000.0
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "")
        usage_data = data.get("usage") or {}
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
        total_tokens = usage_data.get("total_tokens", prompt_tokens + completion_tokens)

        # Estimate cost if available
        return LLMResponse(
            content=content,
            model=target_model,
            provider=self.name,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=0.0,
            ),
            latency_ms=latency_ms,
            raw=data,
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise ValueError("OpenRouter API key is not configured")

        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except Exception:
                        continue

    async def health(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.api_key),
            "provider": self.name,
            "configured": bool(self.api_key),
            "default_model": self.default_model,
        }


class OpenAICompatibleProvider(LLMProvider):
    """Generic OpenAI-compatible provider (vLLM, llama.cpp, OpenAI, Groq, LM Studio)."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "sk-placeholder",
        default_model: str = "default",
        name: str = "openai_compatible",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.name = name

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        start_t = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0)) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            latency_ms = (time.perf_counter() - start_t) * 1000.0
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "")
        usage_data = data.get("usage") or {}
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)

        return LLMResponse(
            content=content,
            model=target_model,
            provider=self.name,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            latency_ms=latency_ms,
            raw=data,
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except Exception:
                        continue

    async def health(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                resp.raise_for_status()
                models = [m.get("id", "") for m in resp.json().get("data", [])]
                return {"ok": True, "provider": self.name, "models": models}
        except Exception as e:
            return {"ok": False, "provider": self.name, "error": str(e), "models": []}


class ModelRouter:
    """Central manager and router for all text/agent LLM providers."""

    def __init__(self, settings_provider: Optional[Any] = None):
        self._providers: Dict[str, LLMProvider] = {}
        self._default_provider_name: str = "ollama"
        self._task_routing: Dict[str, str] = {}
        self._settings_provider = settings_provider
        self._initialize_default_providers()

    def _initialize_default_providers(self) -> None:
        # 1. Ollama (default local)
        self.register_provider(OllamaProvider())
        # 2. OpenRouter (default cloud)
        self.register_provider(OpenRouterProvider())
        # 3. Local vLLM/llama.cpp (optional)
        vllm_url = os.environ.get("VLLM_URL")
        if vllm_url:
            self.register_provider(OpenAICompatibleProvider(base_url=vllm_url, name="vllm"))

    def register_provider(self, provider: LLMProvider) -> None:
        self._providers[provider.name] = provider
        logger.info(f"Registered LLM provider: {provider.name}")

    def get_provider(self, name: Optional[str] = None) -> Optional[LLMProvider]:
        if not name:
            name = self._default_provider_name
        return self._providers.get(name)

    def set_default_provider(self, name: str) -> bool:
        if name in self._providers:
            self._default_provider_name = name
            return True
        return False

    def set_task_provider(self, task: str, provider_name: str) -> bool:
        if provider_name in self._providers:
            self._task_routing[task] = provider_name
            return True
        return False

    async def complete(
        self,
        messages: Union[List[LLMMessage], List[Dict[str, str]]],
        task: str = "agent",
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        fallback_providers: Optional[List[str]] = None,
    ) -> LLMResponse:
        """Route and execute a completion request with fallback support."""
        # Normalize messages
        formatted_messages: List[LLMMessage] = []
        for msg in messages:
            if isinstance(msg, LLMMessage):
                formatted_messages.append(msg)
            elif isinstance(msg, dict):
                formatted_messages.append(LLMMessage(role=msg.get("role", "user"), content=msg.get("content", "")))

        target_provider_name = provider_name or self._task_routing.get(task, self._default_provider_name)
        provider = self._providers.get(target_provider_name)

        providers_to_try = [target_provider_name]
        if fallback_providers:
            providers_to_try.extend([p for p in fallback_providers if p != target_provider_name])
        elif target_provider_name == "openrouter" and "ollama" in self._providers:
            providers_to_try.append("ollama")

        last_error = None
        for p_name in providers_to_try:
            p = self._providers.get(p_name)
            if not p:
                continue
            try:
                # If falling back to another provider, clear custom model ID unless compatible
                target_model = model if p_name == target_provider_name else None
                return await p.complete(
                    messages=formatted_messages,
                    model=target_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            except Exception as e:
                logger.warning(f"ModelRouter: Provider '{p_name}' failed with {e}. Trying fallback...")
                last_error = e

        raise RuntimeError(f"All providers failed for task '{task}'. Last error: {last_error}")

    async def stream(
        self,
        messages: Union[List[LLMMessage], List[Dict[str, str]]],
        task: str = "chat",
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens from chosen provider."""
        formatted_messages: List[LLMMessage] = []
        for msg in messages:
            if isinstance(msg, LLMMessage):
                formatted_messages.append(msg)
            elif isinstance(msg, dict):
                formatted_messages.append(LLMMessage(role=msg.get("role", "user"), content=msg.get("content", "")))

        target_provider_name = provider_name or self._task_routing.get(task, self._default_provider_name)
        provider = self._providers.get(target_provider_name)
        if not provider:
            raise ValueError(f"Provider '{target_provider_name}' is not registered")

        async for chunk in provider.stream(
            messages=formatted_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    async def health_all(self) -> Dict[str, Any]:
        """Check health and status of all registered providers."""
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.health()
        return {
            "default_provider": self._default_provider_name,
            "task_routing": self._task_routing,
            "providers": results,
        }


# Global singleton instance
_GLOBAL_ROUTER: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _GLOBAL_ROUTER
    if _GLOBAL_ROUTER is None:
        _GLOBAL_ROUTER = ModelRouter()
    return _GLOBAL_ROUTER
