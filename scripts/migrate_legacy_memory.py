"""One-time migration: legacy entries.jsonl → monika.db (v3 Phase A).

The legacy `remember` pipeline dumped raw transcription fragments
("Kontekst: ...") into data/memory/entries.jsonl. This script runs the
whole file through Ollama once: keeps only durable, distilled facts,
discards noise, and writes survivors to the v3 memory store.

Run manually (Ollama must be up, GPU reasonably free):
    python scripts/migrate_legacy_memory.py [--dry-run]

The legacy file is left untouched; a report is printed. Re-running is safe
(store dedups by content hash).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.llm.ollama_client import get_client  # noqa: E402
from backend.soul.memory import store as mem_store  # noqa: E402
from backend.soul.models import MemoryEntry  # noqa: E402

LEGACY_PATH = ROOT / "data" / "memory" / "entries.jsonl"
DB_PATH = ROOT / "data" / "monika.db"

SYSTEM = """Dostajesz zrzut starej, zaśmieconej pamięci AI-kompanki (Monika) o użytkowniku (Bartek).
Wyciągnij z niego TYLKO trwałe, konkretne fakty warte zachowania — po polsku, jedno samodzielne
zdanie w trzeciej osobie na fakt. Odrzuć surowe fragmenty transkrypcji ("Kontekst: ..."),
duplikaty i rzeczy jednorazowe. Połącz wpisy mówiące o tym samym. Mniej znaczy lepiej."""


def load_legacy() -> list[str]:
    lines = []
    if not LEGACY_PATH.exists():
        return lines
    for raw in LEGACY_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw).get("entry", {})
        except json.JSONDecodeError:
            continue
        content = (entry.get("content") or "").strip()
        etype = entry.get("type") or "?"
        if content:
            lines.append(f"[{etype}] {content}")
    return lines


async def main(dry_run: bool) -> None:
    items = load_legacy()
    if not items:
        print("No legacy entries found — nothing to migrate.")
        return
    print(f"Legacy entries: {len(items)}")

    prompt = (
        "Stara pamięć:\n" + "\n".join(f"- {i}" for i in items)
        + "\n\nWyciągnij trwałe fakty. Odpowiedz WYŁĄCZNIE poprawnym JSON-em:"
        + ' {"facts": [{"content": str, "importance": 1-10, "entities": [str]}]}'
    )
    result = await get_client().chat_json(
        prompt, system=SYSTEM, num_ctx=8192, temperature=0.1, timeout_s=600.0
    )
    if result is None:
        print("FAILED: no result from Ollama. Nothing written.")
        return

    facts = result.get("facts", [])
    print(f"Distilled facts: {len(facts)}")
    stored = 0
    for f in facts:
        content = (f.get("content") or "").strip()
        if not content:
            continue
        importance = float(min(max(int(f.get("importance", 4)), 1), 10))
        print(f"  [{importance:.0f}] {content}")
        if dry_run:
            continue
        _, status = await mem_store.add(
            MemoryEntry(
                id="pending",
                type="semantic",
                content=content,
                importance=importance,
                perspective="factual",
                entities=[e for e in f.get("entities", []) if isinstance(e, str)],
                tags=["legacy_migration"],
                source_session="legacy_entries_jsonl",
            ),
            db_path=DB_PATH,
        )
        if status == "ok":
            stored += 1
    if dry_run:
        print("(dry-run: nothing written)")
    else:
        print(f"Stored {stored} new entries in {DB_PATH}")
    await get_client().close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.dry_run))
