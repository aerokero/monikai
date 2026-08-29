"""Search Service supporting SearXNG, DuckDuckGo, and Tavily with fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    engine: str = "general"
    score: float = 1.0


class SearchService:
    """Unified web search service with multiple provider fallbacks."""

    def __init__(
        self,
        searxng_url: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
    ):
        self.searxng_url = (searxng_url or os.environ.get("SEARXNG_URL", "http://localhost:8080")).rstrip("/")
        self.tavily_api_key = tavily_api_key or os.environ.get("TAVILY_API_KEY", "")

    async def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        """Perform search trying SearXNG first, then Tavily if configured, then DuckDuckGo fallback."""
        # 1. Try SearXNG
        results = await self._search_searxng(query, max_results)
        if results:
            return results

        # 2. Try Tavily
        if self.tavily_api_key:
            results = await self._search_tavily(query, max_results)
            if results:
                return results

        # 3. Fallback: DuckDuckGo HTML
        return await self._search_duckduckgo(query, max_results)

    async def _search_searxng(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            url = f"{self.searxng_url}/search"
            params = {
                "q": query,
                "format": "json",
                "language": "auto",
                "safesearch": 0,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_results = data.get("results", [])
                    results = []
                    for item in raw_results[:max_results]:
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                snippet=item.get("content", "") or item.get("snippet", ""),
                                engine=item.get("engine", "searxng"),
                                score=float(item.get("score", 1.0) or 1.0),
                            )
                        )
                    if results:
                        return results
        except Exception as e:
            logger.debug(f"SearXNG search failed or unavailable: {e}")
        return []

    async def _search_tavily(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": self.tavily_api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0)) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    for item in data.get("results", []):
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                snippet=item.get("content", ""),
                                engine="tavily",
                                score=float(item.get("score", 1.0)),
                            )
                        )
                    return results
        except Exception as e:
            logger.debug(f"Tavily search failed: {e}")
        return []

    async def _search_duckduckgo(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0), follow_redirects=True) as client:
                resp = await client.post(url, data=data, headers=headers)
                if resp.status_code == 200:
                    html = resp.text
                    results = []
                    # Simple regex extraction from DDG HTML
                    pattern = re.compile(
                        r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                        r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>',
                        re.DOTALL | re.IGNORECASE,
                    )
                    # Extract links with unescape
                    for match in re.finditer(r'<a class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
                        raw_url = match.group(1)
                        snippet_clean = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                        # Clean DuckDuckGo uddg param
                        if "uddg=" in raw_url:
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                            target_url = parsed.get("uddg", [raw_url])[0]
                        else:
                            target_url = raw_url
                        
                        results.append(
                            SearchResult(
                                title=snippet_clean[:60] + "...",
                                url=target_url,
                                snippet=snippet_clean,
                                engine="duckduckgo",
                            )
                        )
                        if len(results) >= max_results:
                            break
                    return results
        except Exception as e:
            logger.warning(f"DuckDuckGo fallback search error: {e}")
        return []


# Global search service instance
_GLOBAL_SEARCH_SERVICE: Optional[SearchService] = None


def get_search_service() -> SearchService:
    global _GLOBAL_SEARCH_SERVICE
    if _GLOBAL_SEARCH_SERVICE is None:
        _GLOBAL_SEARCH_SERVICE = SearchService()
    return _GLOBAL_SEARCH_SERVICE
