"""STM → LTM compaction pipeline.

Triggered when the cumulative importance of recent STM entries exceeds a
threshold (~150, per Stanford Generative Agents). Promotes meaningful
entries to long-term memory (episodic / semantic), discards the rest.

Phase 1: heuristic promotion (no LLM rewriting).
Phase 3: LLM rewrites content in Monika's first-person voice for episodic,
         extracts clean facts for semantic.

Usage (from worker):
    result = await run_compaction(db_path=db_path)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.soul.events import CompactionDone, bus
from backend.soul.memory import store
from backend.soul.models import MemoryEntry

logger = logging.getLogger(__name__)

_IMPORTANCE_THRESHOLD = 150.0  # Stanford: reflection triggers at ~150
_DEFAULT_STM_AGE_HOURS = 168   # 7 days


@dataclass
class CompactionResult:
    promoted_episodic: int = 0
    promoted_semantic: int = 0
    discarded: int = 0
    skipped: bool = False        # True when threshold not reached
    cumulative_importance: float = 0.0
    promoted_ids: list[str] = field(default_factory=list)


async def run_compaction(
    db_path: Path | None = None,
    stm_age_hours: int = _DEFAULT_STM_AGE_HOURS,
    importance_threshold: float = _IMPORTANCE_THRESHOLD,
    promote_top_n: int = 20,
) -> CompactionResult:
    """Run the compaction pipeline.

    Parameters
    ----------
    stm_age_hours:        Only process STM entries older than this.
    importance_threshold: Minimum cumulative importance to trigger compaction.
    promote_top_n:        Maximum entries to promote (rest are discarded).
    """
    result = CompactionResult()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=stm_age_hours)
    stm_entries = await store.get_stm(older_than=cutoff, db_path=db_path)

    if not stm_entries:
        logger.debug("Compaction: no STM entries to process")
        result.skipped = True
        return result

    result.cumulative_importance = sum(e.importance for e in stm_entries)
    logger.info(
        "Compaction check: %d STM entries, cumulative importance=%.1f (threshold=%.1f)",
        len(stm_entries),
        result.cumulative_importance,
        importance_threshold,
    )

    if result.cumulative_importance < importance_threshold:
        logger.debug("Compaction: below threshold, skipping")
        result.skipped = True
        return result

    # Sort by importance descending — most important survive.
    stm_entries.sort(key=lambda e: e.importance, reverse=True)

    to_promote = stm_entries[:promote_top_n]
    to_discard = stm_entries[promote_top_n:]

    for entry in to_promote:
        new_type = _classify_entry(entry)
        await store.promote(entry.id, new_type, db_path=db_path)
        result.promoted_ids.append(entry.id)
        if new_type == "episodic":
            result.promoted_episodic += 1
        else:
            result.promoted_semantic += 1

    if to_discard:
        discarded_ids = [e.id for e in to_discard]
        result.discarded = await store.delete_batch(discarded_ids, db_path=db_path)

    logger.info(
        "Compaction done: +%d episodic, +%d semantic, -%d discarded",
        result.promoted_episodic,
        result.promoted_semantic,
        result.discarded,
    )

    await bus.emit(CompactionDone(
        entries_kept=result.promoted_episodic + result.promoted_semantic,
        entries_discarded=result.discarded,
    ))

    return result


def _classify_entry(entry: MemoryEntry) -> str:
    """Decide whether an entry should become 'episodic' or 'semantic'.

    Phase 1 heuristic:
    - High importance (>= 7) + emotional/personal content → episodic
    - Otherwise → semantic

    Phase 3: LLM call will replace this.
    """
    if entry.importance >= 7.0 and _is_personal(entry.content):
        return "episodic"
    return "semantic"


def _is_personal(content: str) -> bool:
    import re
    personal_markers = re.compile(
        r"\b("
        r"czuję|czuje|powiedział|powiedziałem|pamiętam|poczułem|"
        r"feel|said|remember|felt|told me|i told"
        r")\b",
        re.IGNORECASE,
    )
    return bool(personal_markers.search(content))
