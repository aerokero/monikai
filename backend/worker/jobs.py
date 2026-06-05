"""Background worker job definitions.

Jobs are persisted in the `jobs` table in monika.db so the worker process
survives restarts. The main process enqueues jobs; the worker polls and runs them.

Phase 1: job models + CompactionJob + ReflectionJob (stub for Phase 3).
The worker process itself (polling loop) is implemented in Phase 4.

Usage (enqueue from main process):
    job = CompactionJob()
    await enqueue(job, db_path=db_path)

Running (from worker):
    await job.run(db_path=db_path)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Base job
# ---------------------------------------------------------------------------

class BaseJob(BaseModel):
    id: str = Field(default_factory=lambda: f"job_{uuid4().hex[:12]}")
    kind: str
    payload: dict = Field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=_utcnow)

    async def run(self, db_path: Path | None = None) -> dict:
        """Execute the job. Returns a result dict stored in the DB on success."""
        raise NotImplementedError(f"{type(self).__name__}.run() not implemented")


# ---------------------------------------------------------------------------
# Concrete jobs
# ---------------------------------------------------------------------------

class CompactionJob(BaseJob):
    """Runs the STM → LTM compaction pipeline."""
    kind: str = "CompactionJob"

    async def run(self, db_path: Path | None = None) -> dict:
        from backend.soul.memory.compaction import run_compaction

        stm_age_hours: int = self.payload.get("stm_age_hours", 168)
        importance_threshold: float = self.payload.get("importance_threshold", 150.0)
        promote_top_n: int = self.payload.get("promote_top_n", 20)

        result = await run_compaction(
            db_path=db_path,
            stm_age_hours=stm_age_hours,
            importance_threshold=importance_threshold,
            promote_top_n=promote_top_n,
        )
        return {
            "promoted_episodic": result.promoted_episodic,
            "promoted_semantic": result.promoted_semantic,
            "discarded": result.discarded,
            "skipped": result.skipped,
            "cumulative_importance": result.cumulative_importance,
        }


class ReflectionJob(BaseJob):
    """Runs the "3 questions" reflection cycle (Phase 3).

    Stub — logs a warning and exits cleanly. Phase 3 implements the Ollama call.
    """
    kind: str = "ReflectionJob"

    async def run(self, db_path: Path | None = None) -> dict:
        logger.warning(
            "ReflectionJob: not yet implemented (Phase 3). "
            "Enqueued %s will be marked done without effect.",
            self.id,
        )
        return {"status": "noop", "reason": "not_implemented_until_phase3"}


class ImportanceJob(BaseJob):
    """Rescore a batch of entries with Ollama (Phase 3). Stub in Phase 1."""
    kind: str = "ImportanceJob"

    async def run(self, db_path: Path | None = None) -> dict:
        logger.warning("ImportanceJob: not yet implemented (Phase 3).")
        return {"status": "noop"}


# ---------------------------------------------------------------------------
# Registry & dispatch
# ---------------------------------------------------------------------------

def _get_narrative_job_class() -> type[BaseJob]:
    from backend.worker.narrative_job import NarrativeJob
    return NarrativeJob


_JOB_REGISTRY: dict[str, type[BaseJob]] = {
    "CompactionJob": CompactionJob,
    "ReflectionJob": ReflectionJob,
    "ImportanceJob": ImportanceJob,
}

# NarrativeJob is registered lazily to avoid circular imports at module load.
_LAZY_JOB_REGISTRY: dict[str, object] = {
    "NarrativeJob": _get_narrative_job_class,
}


def deserialise(kind: str, payload: str | dict) -> BaseJob:
    """Reconstruct a job from DB row data."""
    cls = _JOB_REGISTRY.get(kind)
    if cls is None:
        lazy = _LAZY_JOB_REGISTRY.get(kind)
        if lazy is not None:
            cls = lazy()  # type: ignore[assignment]
    if cls is None:
        raise ValueError(f"Unknown job kind: {kind!r}")
    p = json.loads(payload) if isinstance(payload, str) else payload
    return cls(kind=kind, payload=p)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

async def enqueue(
    job: BaseJob,
    db_path: Path | None = None,
) -> str:
    """Persist a job to the jobs table and return its ID."""
    from backend.soul.db import get_db

    async with get_db(db_path) as conn:
        await conn.execute(
            """
            INSERT INTO jobs (id, kind, payload, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.kind,
                json.dumps(job.payload),
                job.status.value,
                _iso(job.created_at),
            ),
        )
        await conn.commit()
    logger.info("Enqueued %s (%s)", job.id, job.kind)
    return job.id


async def mark_running(job_id: str, db_path: Path | None = None) -> None:
    from backend.soul.db import get_db
    async with get_db(db_path) as conn:
        await conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
            (_iso(_utcnow()), job_id),
        )
        await conn.commit()


async def mark_done(
    job_id: str,
    result: dict | None = None,
    db_path: Path | None = None,
) -> None:
    from backend.soul.db import get_db
    async with get_db(db_path) as conn:
        await conn.execute(
            "UPDATE jobs SET status = 'done', finished_at = ? WHERE id = ?",
            (_iso(_utcnow()), job_id),
        )
        await conn.commit()


async def mark_failed(
    job_id: str,
    error: str,
    db_path: Path | None = None,
) -> None:
    from backend.soul.db import get_db
    async with get_db(db_path) as conn:
        await conn.execute(
            "UPDATE jobs SET status = 'failed', finished_at = ?, error = ? WHERE id = ?",
            (_iso(_utcnow()), error[:2000], job_id),
        )
        await conn.commit()
