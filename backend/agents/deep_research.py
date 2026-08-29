"""Deep Research Engine — Multi-step autonomous research and report synthesis."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from backend.models.model_router import LLMMessage, LLMResponse, get_model_router
from backend.services.search_service import SearchResult, get_search_service

logger = logging.getLogger(__name__)


@dataclass
class ResearchCostTracker:
    queries_executed: int = 0
    pages_scraped: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def add_llm_usage(self, response: LLMResponse) -> None:
        self.prompt_tokens += response.usage.prompt_tokens
        self.completion_tokens += response.usage.completion_tokens
        self.total_tokens += response.usage.total_tokens
        self.estimated_cost_usd += response.usage.estimated_cost_usd


@dataclass
class ResearchFinding:
    url: str
    title: str
    content_snippet: str
    relevance_score: float = 1.0


@dataclass
class DeepResearchTask:
    task_id: str
    topic: str
    depth: str = "standard"  # "quick", "standard", "deep"
    status: str = "queued"  # "queued", "running", "completed", "failed"
    progress: float = 0.0
    current_step: str = "Inicjalizacja..."
    subqueries: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)
    report_markdown: Optional[str] = None
    cost_tracker: ResearchCostTracker = field(default_factory=ResearchCostTracker)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    duration_s: float = 0.0
    error: Optional[str] = None


class DeepResearchEngine:
    """Orchestrates multi-phase deep research workflows."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path("data")
        self.reports_dir = self.data_dir / "research_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.active_tasks: Dict[str, DeepResearchTask] = {}
        self.search_service = get_search_service()

    def get_task(self, task_id: str) -> Optional[DeepResearchTask]:
        return self.active_tasks.get(task_id)

    def list_tasks(self) -> List[DeepResearchTask]:
        return list(self.active_tasks.values())

    async def _update_progress(
        self,
        task: DeepResearchTask,
        status: str,
        progress: float,
        step_desc: str,
        on_progress: Optional[Callable[[DeepResearchTask], Any]] = None,
    ) -> None:
        task.status = status
        task.progress = progress
        task.current_step = step_desc
        if on_progress:
            try:
                res = on_progress(task)
                if hasattr(res, "__await__"):
                    await res
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    async def _clean_html_to_text(self, html: str, max_chars: int = 4000) -> str:
        """Strip tags, scripts, and extra whitespace to produce clean reading text."""
        # Remove script and style elements
        clean = re.sub(r"<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML comments
        clean = re.sub(r"<!--.*?-->", " ", clean, flags=re.DOTALL)
        # Replace tags with spaces or newlines
        clean = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h1>|</h2>|</h3>", "\n", clean, flags=re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        # Decode common HTML entities
        clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
        # Normalize whitespace
        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        text = "\n".join(lines)
        return text[:max_chars]

    async def _scrape_url(self, url: str) -> Optional[str]:
        """Fetch URL content cleanly via HTTP."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0), follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200 and "text" in resp.headers.get("content-type", ""):
                    return await self._clean_html_to_text(resp.text)
        except Exception as e:
            logger.debug(f"Failed to scrape {url}: {e}")
        return None

    async def execute_research(
        self,
        topic: str,
        depth: str = "standard",
        task_id: Optional[str] = None,
        on_progress: Optional[Callable[[DeepResearchTask], Any]] = None,
    ) -> DeepResearchTask:
        """Run full deep research pipeline."""
        tid = task_id or str(uuid.uuid4())[:8]
        task = DeepResearchTask(task_id=tid, topic=topic, depth=depth)
        self.active_tasks[tid] = task
        start_time = time.perf_counter()

        router = get_model_router()

        try:
            # -------------------------------------------------------------
            # STEP 1: Decomposition — generate research subqueries
            # -------------------------------------------------------------
            await self._update_progress(task, "running", 0.10, "Rozkładanie pytania badawczego na zapytania cząstkowe...", on_progress)

            query_count = 3 if depth == "quick" else (5 if depth == "standard" else 8)
            decomp_prompt = (
                f"Dla zadanego tematu badawczego przygotuj dokładnie {query_count} precyzyjnych zapytań wyszukiwarki internetowej.\n"
                f"Temat: \"{topic}\"\n\n"
                f"Zwróć odpowiedź w formacie JSON:\n"
                f'{{"subqueries": ["zapytanie 1", "zapytanie 2", ...]}}'
            )

            decomp_res = await router.complete(
                messages=[LLMMessage(role="user", content=decomp_prompt)],
                task="research",
                response_format={"type": "json_object"},
            )
            task.cost_tracker.add_llm_usage(decomp_res)

            try:
                data = json.loads(decomp_res.content)
                task.subqueries = data.get("subqueries", [topic])
            except Exception:
                # Fallback extraction if model output raw lines
                task.subqueries = [line.strip().lstrip("-123456789. ") for line in decomp_res.content.splitlines() if line.strip()][:query_count]
                if not task.subqueries:
                    task.subqueries = [topic]

            # -------------------------------------------------------------
            # STEP 2: Web Search & Retrieval across subqueries
            # -------------------------------------------------------------
            await self._update_progress(task, "running", 0.30, f"Wyszukiwanie w sieci dla {len(task.subqueries)} zapytań...", on_progress)

            all_search_results: Dict[str, SearchResult] = {}
            for i, q in enumerate(task.subqueries):
                task.cost_tracker.queries_executed += 1
                res_list = await self.search_service.search(q, max_results=4)
                for r in res_list:
                    if r.url and r.url not in all_search_results:
                        all_search_results[r.url] = r

            # -------------------------------------------------------------
            # STEP 3: Content Scraping & Extraction
            # -------------------------------------------------------------
            urls_to_scrape = list(all_search_results.keys())[: (6 if depth == "quick" else (10 if depth == "standard" else 15))]
            await self._update_progress(task, "running", 0.50, f"Pobieranie i analiza zawartości stron ({len(urls_to_scrape)} źródeł)...", on_progress)

            raw_findings = []
            for i, url in enumerate(urls_to_scrape):
                scraped_text = await self._scrape_url(url)
                if scraped_text and len(scraped_text) > 20:
                    sr = all_search_results[url]
                    finding = {
                        "url": url,
                        "title": sr.title or url,
                        "snippet": sr.snippet,
                        "content": scraped_text,
                    }
                    raw_findings.append(finding)
                    task.findings.append({"url": url, "title": sr.title, "preview": scraped_text[:200]})
                    task.sources.append({"id": f"[{len(task.sources) + 1}]", "title": sr.title, "url": url})
                    task.cost_tracker.pages_scraped += 1

                progress_val = 0.50 + (0.25 * ((i + 1) / max(1, len(urls_to_scrape))))
                await self._update_progress(task, "running", round(progress_val, 2), f"Przeanalizowano źródło {i + 1}/{len(urls_to_scrape)}: {all_search_results[url].title[:35]}...", on_progress)

            # -------------------------------------------------------------
            # STEP 4: Deep Synthesis & Report Compilation
            # -------------------------------------------------------------
            await self._update_progress(task, "running", 0.80, "Generowanie pełnego raportu badawczego i synteza wniosków...", on_progress)

            # Build context with numbered citations
            context_blocks = []
            for idx, f in enumerate(raw_findings, start=1):
                context_blocks.append(f"ŹRÓDŁO [{idx}]: {f['title']}\nURL: {f['url']}\nTREŚĆ:\n{f['content']}\n")

            context_str = "\n---\n".join(context_blocks)
            if not context_str:
                context_str = "Brak dostępnych szczegółowych stron z sieci — bazuj na ogólnej wiedzy oraz zapytaniach cząstkowych."

            synthesis_prompt = f"""Jesteś wiodącym analitykiem badawczym AI w systemie MonikAI Workspace (Odysseus Engine).
Twoim zadaniem jest sporządzenie wyczerpującego, profesjonalnego raportu badawczego w języku polskim w formacie Markdown na zadany temat.

TEMAT: {topic}
GŁĘBOKOŚĆ BADANIA: {depth}

DOSTARCZONE ŹRÓDŁA I ZNALEZISKA:
{context_str}

WYMOGI STRUKTURALNE RAPORTU:
1. **Tytuł raportu** (# ...)
2. **Podsumowanie Wykonawcze (Executive Summary)** — zwięzły kondensat najważniejszych faktów i odpowiedzi na główne pytanie.
3. **Kluczowe Odkrycia i Fakty** — wypunktowane najważniejsze dane i tezy wraz z cytowaniami w tekście w formacie [1], [2].
4. **Szczegółowa Analiza Tematu** (podzielona na logiczne podsekcje ## i ###).
5. **Wnioski, Ryzyka i Perspektywy**.
6. **Bibliografia / Źródła** (lista wszystkich ponumerowanych linków i tytułów).

Używaj rzetelnego, profesjonalnego stylu oraz precyzyjnych cytowań `[X]` odnoszących się do powyższych źródeł.
"""

            synth_res = await router.complete(
                messages=[LLMMessage(role="user", content=synthesis_prompt)],
                task="research",
                temperature=0.4,
            )
            task.cost_tracker.add_llm_usage(synth_res)

            task.report_markdown = synth_res.content
            task.duration_s = round(time.perf_counter() - start_time, 2)
            task.completed_at = datetime.now().isoformat()

            # Save report to disk
            report_file = self.reports_dir / f"{tid}_{int(time.time())}.md"
            report_file.write_text(task.report_markdown, encoding="utf-8")

            await self._update_progress(task, "completed", 1.0, "Badanie zakończone sukcesem!", on_progress)
            return task

        except Exception as e:
            logger.error(f"Deep research task {tid} failed: {e}", exc_info=True)
            task.error = str(e)
            task.duration_s = round(time.perf_counter() - start_time, 2)
            await self._update_progress(task, "failed", task.progress, f"Błąd badania: {e}", on_progress)
            return task


# Global singleton instance
_GLOBAL_RESEARCH_ENGINE: Optional[DeepResearchEngine] = None


def get_deep_research_engine(data_dir: Optional[Path] = None) -> DeepResearchEngine:
    global _GLOBAL_RESEARCH_ENGINE
    if _GLOBAL_RESEARCH_ENGINE is None:
        _GLOBAL_RESEARCH_ENGINE = DeepResearchEngine(data_dir=data_dir)
    return _GLOBAL_RESEARCH_ENGINE
