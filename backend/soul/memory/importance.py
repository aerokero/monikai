"""Importance scoring for memory entries (1–10 scale).

Phase 1: heuristic scorer. The interface is async so that Phase 3 can
transparently swap to an Ollama call without changing callers.

Design:
  score_importance(content, type, entities, tags) → float (1.0 … 10.0)

The Stanford Generative Agents paper uses a 1–10 integer scale scored by
an LLM. For now we approximate with linguistic heuristics. The score
drives: compaction threshold (sum > 150), milestone candidacy (>= 8),
and proactive recall weighting.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Heuristic signals
# ---------------------------------------------------------------------------

_EMOTIONAL_WORDS = re.compile(
    r"\b("
    r"czuję|czuje|kocham|tęsknię|boli|smutny|szczęśliwy|strach|radość|"
    r"płakał|płakałem|płakałam|wzruszony|ważny|ważne|nigdy|zawsze|"
    r"feel|love|miss|hurt|sad|happy|fear|joy|cried|touched|important|never|always"
    r")\b",
    re.IGNORECASE,
)

_FACTUAL_SIGNALS = re.compile(
    r"\b("
    r"nazywam się|mam na imię|imię|urodziny|urodzin|mieszkam|pracuję|"
    r"my name|birthday|i live|i work"
    r")\b",
    re.IGNORECASE,
)

_DATE_PATTERN = re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]\d{4}\b")

_HIGH_IMPORTANCE_TYPES = {"episodic"}
_MEDIUM_IMPORTANCE_TYPES = {"semantic", "world"}


async def score(
    content: str,
    type_: str,
    entities: list[str] | None = None,
    tags: list[str] | None = None,
) -> float:
    """Return an importance score in [1.0, 10.0].

    In Phase 3 this will call Ollama with the same signature.
    For now: heuristic rules that approximate the LLM score.
    """
    entities = entities or []
    tags = tags or []
    base = 3.0

    # Type weight
    if type_ in _HIGH_IMPORTANCE_TYPES:
        base += 2.5
    elif type_ in _MEDIUM_IMPORTANCE_TYPES:
        base += 1.5

    # Emotional content boosts importance (experiences matter more)
    if _EMOTIONAL_WORDS.search(content):
        base += 2.0

    # Factual signals (stable, useful facts score higher)
    if _FACTUAL_SIGNALS.search(content):
        base += 1.0

    # Temporal anchoring (specific dates are more important)
    if _DATE_PATTERN.search(content):
        base += 0.5

    # Social importance (more entities = more context)
    base += min(1.0, len(entities) * 0.3)

    # Substance (longer = more substance, up to a point)
    if len(content) > 200:
        base += 0.5
    elif len(content) > 80:
        base += 0.25

    return round(min(10.0, max(1.0, base)), 1)


def score_sync(
    content: str,
    type_: str,
    entities: list[str] | None = None,
    tags: list[str] | None = None,
) -> float:
    """Synchronous wrapper for use in non-async contexts."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        # We're inside an event loop — run_until_complete can't be used.
        # Fall back to direct heuristic computation (safe since Phase 1 has no I/O).
        return _heuristic(content, type_, entities, tags)
    except RuntimeError:
        return asyncio.run(score(content, type_, entities, tags))


def _heuristic(
    content: str,
    type_: str,
    entities: list[str] | None,
    tags: list[str] | None,
) -> float:
    """Pure-sync implementation used by score() and score_sync()."""
    entities = entities or []
    base = 3.0
    if type_ in _HIGH_IMPORTANCE_TYPES:
        base += 2.5
    elif type_ in _MEDIUM_IMPORTANCE_TYPES:
        base += 1.5
    if _EMOTIONAL_WORDS.search(content):
        base += 2.0
    if _FACTUAL_SIGNALS.search(content):
        base += 1.0
    if _DATE_PATTERN.search(content):
        base += 0.5
    base += min(1.0, len(entities) * 0.3)
    if len(content) > 200:
        base += 0.5
    elif len(content) > 80:
        base += 0.25
    return round(min(10.0, max(1.0, base)), 1)
