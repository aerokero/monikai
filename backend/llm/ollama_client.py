"""Async Ollama client — the workhorse behind Monika's background cognition.

Every "thinking in the background" task (session digests, importance scoring,
reflections, inner-state narration) goes through this module. It talks to a
local Ollama server over HTTP and supports structured output via JSON schema.

Design rules:
- Failures degrade, never crash: callers get ``None`` and log a warning.
- No fake data: if Ollama is unreachable or returns garbage, the caller must
  skip its task — never substitute a template.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("MONIKAI_OLLAMA_MODEL", "qwen3:8b")

# Background jobs are latency-tolerant; digest of a long session can take a while.
DEFAULT_TIMEOUT_S = 180.0


@dataclass
class OllamaClient:
    """Thin async wrapper around the Ollama chat API."""

    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S
    retries: int = 1
    # qwen3 supports an explicit thinking phase; off by default for speed —
    # structured extraction doesn't benefit enough to pay the token cost.
    think: bool = False
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_s, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Return {"ok": bool, "models": [...], "model_available": bool}."""
        try:
            resp = await self._http().get("/api/tags")
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            return {
                "ok": True,
                "models": models,
                "model_available": any(
                    m == self.model or m.split(":")[0] == self.model
                    for m in models
                ),
            }
        except Exception as exc:
            logger.warning("ollama: health check failed: %s", exc)
            return {"ok": False, "models": [], "model_available": False}

    async def generation_speed(self) -> float | None:
        """Measure current generation speed in tokens/s with a tiny probe.

        Background jobs use this to yield when the GPU is busy (e.g. a game
        is running and Ollama spills to CPU). Returns None if the probe fails.
        """
        try:
            resp = await self._http().post(
                "/api/generate",
                json={
                    "model": self.model,
                    "prompt": "Policz od 1 do 20, same liczby po przecinku.",
                    "stream": False,
                    "think": self.think,
                    "options": {"num_predict": 24, "temperature": 0.0},
                },
                timeout=httpx.Timeout(120.0, connect=5.0),
            )
            resp.raise_for_status()
            data = resp.json()
            eval_count = data.get("eval_count", 0)
            eval_ns = data.get("eval_duration", 0)
            if eval_count and eval_ns:
                return eval_count / (eval_ns / 1e9)
            return None
        except Exception as exc:
            logger.debug("ollama: speed probe failed: %r", exc)
            return None

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def chat(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: dict | None = None,
        model: str | None = None,
        temperature: float = 0.3,
        num_ctx: int | None = None,
        timeout_s: float | None = None,
    ) -> str | None:
        """One-shot chat completion. Returns the raw content string or None.

        When ``schema`` is given, Ollama constrains output to that JSON schema
        (structured outputs) — use :meth:`chat_json` to get it parsed.
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "think": self.think,
            "options": {"temperature": temperature},
        }
        # NOTE: full JSON-schema grammars are pathologically slow in Ollama
        # (measured: 15 min vs 15 s on the same prompt). Prefer format="json"
        # (pass schema="json") + pydantic validation on the caller side;
        # reserve dict schemas for trivial grammars only.
        if schema is not None:
            payload["format"] = schema
        if num_ctx is not None:
            payload["options"]["num_ctx"] = num_ctx

        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = await self._http().post(
                    "/api/chat",
                    json=payload,
                    timeout=httpx.Timeout(timeout_s or self.timeout_s, connect=5.0),
                )
                resp.raise_for_status()
                content = resp.json().get("message", {}).get("content", "")
                if content.strip():
                    return content
                last_exc = ValueError("empty response content")
            except Exception as exc:  # noqa: BLE001 — degrade, don't crash
                last_exc = exc
                if attempt < self.retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
        logger.warning(
            "ollama: chat failed after %d attempt(s): %r",
            self.retries + 1,
            last_exc,
        )
        return None

    async def chat_json(
        self,
        prompt: str,
        schema: dict | str = "json",
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        num_ctx: int | None = None,
        timeout_s: float | None = None,
    ) -> dict | list | None:
        """Structured-output chat. Returns parsed JSON or None on any failure."""
        content = await self.chat(
            prompt,
            system=system,
            schema=schema,
            model=model,
            temperature=temperature,
            num_ctx=num_ctx,
            timeout_s=timeout_s,
        )
        if content is None:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("ollama: invalid JSON in structured output: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Module-level shared client
# ---------------------------------------------------------------------------

_shared: OllamaClient | None = None


def get_client() -> OllamaClient:
    """Shared client for background jobs (one connection pool per process)."""
    global _shared
    if _shared is None:
        _shared = OllamaClient()
    return _shared


async def shutdown() -> None:
    global _shared
    if _shared is not None:
        await _shared.close()
        _shared = None
