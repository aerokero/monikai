"""Stanford Generative Agents retrieval formula.

retrieval_score = α·recency + β·importance + γ·relevance
                  (all three components normalised to [0, 1])

recency    = 0.995 ** hours_since_last_access
importance = entry.importance / 10
relevance  = normalised BM25 score (proxy for cosine similarity in Phase 1;
             Phase 3 replaces with actual embedding cosine)

References:
  Park et al. (2023) "Generative Agents: Interactive Simulacra of Human Behavior"
  https://arxiv.org/abs/2304.03442
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.soul.models import MemoryEntry
from backend.soul.memory import store

logger = logging.getLogger(__name__)

_DECAY_BASE = 0.995  # per hour; ~50 % relevance after ~138 hours (≈ 6 days)


# ---------------------------------------------------------------------------
# Retrieval result
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    entry: MemoryEntry
    score: float          # composite retrieval score [0, 1]
    recency: float
    importance: float
    relevance: float
    bm25_raw: float = 0.0


# ---------------------------------------------------------------------------
# Scoring components
# ---------------------------------------------------------------------------

def recency_score(entry: MemoryEntry) -> float:
    ref = entry.last_accessed or entry.created_at
    now = datetime.now(tz=timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - ref).total_seconds() / 3600.0)
    return _DECAY_BASE ** hours


def importance_score(entry: MemoryEntry) -> float:
    return entry.importance / 10.0


def _normalise_bm25(scores: list[float]) -> list[float]:
    """Normalise a list of BM25 absolute scores to [0, 1]."""
    if not scores:
        return []
    max_s = max(scores)
    if max_s == 0:
        return [0.0] * len(scores)
    return [s / max_s for s in scores]


def composite_score(
    recency: float,
    importance: float,
    relevance: float,
    α: float = 1.0,
    β: float = 1.0,
    γ: float = 1.0,
) -> float:
    total_weight = α + β + γ
    return (α * recency + β * importance + γ * relevance) / total_weight


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def retrieve(
    query: str,
    limit: int = 5,
    types: list[str] | None = None,
    α: float = 1.0,
    β: float = 1.0,
    γ: float = 1.0,
    db_path: Path | None = None,
) -> list[RetrievalResult]:
    """Retrieve the top-k most relevant memories for a query.

    Scoring: composite of recency + importance + BM25 relevance.
    touch() is called on every returned entry to update last_accessed.

    Parameters
    ----------
    query:  User utterance or search phrase.
    limit:  Number of entries to return.
    types:  Restrict to these memory types (None = all).
    α, β, γ: Weights for recency, importance, relevance.
    """
    # Use a generous candidate pool so scoring can re-rank effectively.
    fts_limit = max(limit * 4, 20)
    hits = await store.search_fts(query, types=types, limit=fts_limit, db_path=db_path)

    if not hits:
        return []

    entries = [e for e, _ in hits]
    raw_bm25 = [s for _, s in hits]
    norm_bm25 = _normalise_bm25(raw_bm25)

    results: list[RetrievalResult] = []
    for entry, bm25, rel_norm in zip(entries, raw_bm25, norm_bm25):
        rec = recency_score(entry)
        imp = importance_score(entry)
        score = composite_score(rec, imp, rel_norm, α, β, γ)
        results.append(RetrievalResult(
            entry=entry,
            score=score,
            recency=rec,
            importance=imp,
            relevance=rel_norm,
            bm25_raw=bm25,
        ))

    results.sort(key=lambda r: r.score, reverse=True)
    top = results[:limit]

    # Touch all returned entries so recency stays fresh.
    for r in top:
        await store.touch(r.entry.id, db_path=db_path)

    return top


def format_for_prompt(results: list[RetrievalResult]) -> str:
    """Format retrieval results as a context block for the LLM prompt."""
    if not results:
        return ""
    lines = ["Relevant memory snippets:"]
    for r in results:
        e = r.entry
        tag_str = ", ".join(e.tags) if e.tags else ""
        suffix = f" [tags: {tag_str}]" if tag_str else ""
        lines.append(f"- [{e.type}] {e.content}{suffix}")
    lines.append("Use these for context. Do not mention memory retrieval unless asked.")
    return "\n".join(lines)
