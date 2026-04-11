#!/usr/bin/env python3
"""
PHASE A Data Migration Script
Cleanup: Mark low-importance entries as inactive, preserve high-value entries.
"""

import json
import sqlite3
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
MEMORY_DIR = DATA_DIR / "memory"
ENTRIES_PATH = MEMORY_DIR / "entries.jsonl"
DB_PATH = MEMORY_DIR / "index" / "memory.db"

def score_entry_importance(entry: dict) -> float:
    """Score importance (0-1) based on entry content."""
    W_ACTIONABLE = 0.4
    W_CONFIDENCE = 0.3
    W_ENTITIES = 0.2
    W_TAGS = 0.1
    
    # Actionability
    actionable = 0.3
    content_lower = entry.get("content", "").lower()
    if any(kw in content_lower for kw in ["ma", "będzie", "może", "trzeba", "2026", "kwiecień", "maj"]):
        actionable = 1.0
    elif entry.get("type") in ["event", "action", "deadline", "plan"]:
        actionable = 0.9
    elif entry.get("type") in ["fact", "preference"]:
        actionable = 0.6
    elif entry.get("type") == "memory_note":
        actionable = 0.2
    
    # Confidence
    conf = min(1.0, max(0.0, entry.get("confidence", 0.6)))
    
    # Entity count
    entities = entry.get("entities", [])
    entity_score = min(1.0, len(entities) / 3.0)
    
    # Tag specificity
    tags = entry.get("tags", [])
    tag_score = 0.0
    meaningful_tags = [t.lower() for t in tags if t and not t.startswith("topic:")]
    if meaningful_tags:
        tag_score = 0.7 + (0.3 * min(len(meaningful_tags) / 5.0, 1.0))
    
    score = (
        W_ACTIONABLE * actionable +
        W_CONFIDENCE * conf +
        W_ENTITIES * entity_score +
        W_TAGS * tag_score
    )
    return min(1.0, max(0.0, score))

def main():
    print("[MIGRATION] Phase A Data Migration")
    print(f"[MIGRATION] Reading from: {ENTRIES_PATH}")
    
    # 1. Read JSONL and score entries
    entries_by_id = {}
    invalid_count = 0
    low_importance = []
    
    if not ENTRIES_PATH.exists():
        print("[MIGRATION] No entries.jsonl found, skipping")
        return
    
    with open(ENTRIES_PATH, 'r', encoding='utf-8') as f:
        for line_idx, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                entry_json = json.loads(line)
                op = entry_json.get("op")
                if op == "add":
                    entry = entry_json.get("entry", {})
                    entry_id = entry.get("id")
                    
                    if not entry_id:
                        print(f"[MIGRATION] Line {line_idx}: Missing entry ID")
                        invalid_count += 1
                        continue
                    
                    # Check for corruption
                    if not entry.get("type") or not str(entry.get("type")).strip():
                        print(f"[MIGRATION] Line {line_idx}: {entry_id} has empty type (CORRUPTION)")
                        invalid_count += 1
                        continue
                    
                    # Score importance
                    importance = score_entry_importance(entry)
                    entry["importance_score"] = importance
                    entries_by_id[entry_id] = entry
                    
                    # Track low-importance
                    if importance < 0.4:
                        low_importance.append((entry_id, entry.get("content", "")[:50], importance))
            except json.JSONDecodeError as e:
                print(f"[MIGRATION] Line {line_idx}: JSON error: {e}")
                invalid_count += 1
    
    print(f"[MIGRATION] Loaded {len(entries_by_id)} valid entries")
    print(f"[MIGRATION] Invalid entries: {invalid_count}")
    print(f"[MIGRATION] Low-importance entries (<0.4): {len(low_importance)}")
    
    # Show sample of low-importance
    for entry_id, content, score in low_importance[:10]:
        print(f"  - {entry_id} (score={score:.2f}): {content}")
    
    if len(low_importance) > 10:
        print(f"  ... and {len(low_importance) - 10} more")
    
    # 2. Update SQLite with importance scores
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    try:
        # Add importance_score column if not exists
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if "importance_score" not in columns:
            print("[MIGRATION] Adding importance_score column to SQLite...")
            conn.execute("ALTER TABLE entries ADD COLUMN importance_score REAL DEFAULT 0.5")
            conn.commit()
        
        # Update scores
        for entry_id, entry in entries_by_id.items():
            importance = entry.get("importance_score", 0.5)
            conn.execute(
                "UPDATE entries SET importance_score = ? WHERE id = ?",
                (importance, entry_id)
            )
        conn.commit()
        print(f"[MIGRATION] Updated {len(entries_by_id)} entries in SQLite")
        
        # Mark low-importance as inactive
        low_important_ids = [eid for eid, _, _ in low_importance]
        for entry_id in low_important_ids:
            conn.execute(
                "UPDATE entries SET status = 'inactive' WHERE id = ? AND status = 'active'",
                (entry_id,)
            )
        conn.commit()
        print(f"[MIGRATION] Marked {len(low_important_ids)} low-importance entries as inactive")
        
        # Statistics
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entries WHERE status = 'active'")
        active_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM entries WHERE status = 'inactive'")
        inactive_count = cursor.fetchone()[0]
        cursor.execute("SELECT AVG(importance_score) FROM entries WHERE status = 'active'")
        avg_importance = cursor.fetchone()[0] or 0.0
        
        print(f"[MIGRATION] Final statistics:")
        print(f"  - Active entries: {active_count}")
        print(f"  - Inactive entries: {inactive_count}")
        print(f"  - Average importance (active): {avg_importance:.2f}")
        
    finally:
        conn.close()
    
    print("[MIGRATION] ✅ Phase A migration complete!")
    print("[MIGRATION] Next: Run application to test integration")

if __name__ == "__main__":
    main()
