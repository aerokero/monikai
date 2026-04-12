# Memory System - Deep Dive

Complete explanation of MonikAI's episodic memory architecture and design decisions.

## Why Episodic Memory?

MonikAI needs to remember conversations to feel connected. Unlike typical AI that forgets each session, MonikAI maintains a growing history of interactions.

**Design Goals:**
- ✅ Remember past conversations and references
- ✅ Search memories by topic, date, person
- ✅ Organize memories into themes (journal, topics, roleplay)
- ✅ Fast retrieval (milliseconds, not seconds)
- ✅ Local storage (no cloud dependency)
- ✅ Survive across sessions and restarts

## Architecture: JSONL + SQLite FTS

**Why this combination?**

### JSONL (JSON Lines) - Append-Only Log
```
data/user_memory/memory/entries.jsonl

{"id": "mem_001", "timestamp": "2026-04-12T10:00:00Z", "content": "User told me...", "page": "journal"}
{"id": "mem_002", "timestamp": "2026-04-12T10:15:00Z", "content": "User asked about...", "page": "topics"}
```

**Advantages:**
- **Append-only** - Never overwrite, new entries at end
- **Simple to debug** - Human readable JSON
- **Fast writes** - Just append line to file
- **Crash-safe** - Partial writes still valid
- **Movable** - Can backup/transfer easily

### SQLite FTS (Full-Text Search) - Index
SQLite Full-Text Search index provides:
- **Keyword matching** - Search for "Python" finds all mentions
- **Substring search** - Find "prog" matches "programming" and "progress"
- **Phrase search** - Find "machine learning" as exact phrase
- **Ranking** - Most relevant results first
- **Millisecond lookups** - Index makes it instant

## Data Flow

### Adding a Memory

```
1. User says: "I'm learning Python and building web apps"

2. Backend receives conversation turn
   ↓
3. Extract entities (NLP):
   - Topics: ["Python", "web development"]
   - Entities: ["programming skill"]
   - Sentiment: positive
   ↓
4. Create memory entry:
   {
     "id": "mem_20260412_001",
     "timestamp": "2026-04-12T10:30:00Z",
     "content": "User is learning Python and building web apps",
     "page": "topics",  (or "journal", "roleplay")
     "entities": ["Python", "web development"],
     "metadata": {
       "source": "conversation",
       "turn_index": 5,
       "user_sentiment": 0.8
     }
   }
   ↓
5. Append to entries.jsonl
   ↓
6. Index in SQLite FTS:
   INSERT INTO fts_entries(rowid, content, entities)
   VALUES(1, "User is learning Python...", "Python,web development")
```

### Retrieving Memories

**Example: User asks "What did I tell you about my interests?"**

```
1. Query: "interests"
   ↓
2. SQLite FTS Search:
   SELECT * FROM fts_entries WHERE content MATCH "interests"
   ORDER BY rank
   ↓
3. Returns top 5 matching entries:
   - mem_001: "User interested in gaming" (score: 0.95)
   - mem_003: "Loves music production" (score: 0.87)
   - mem_005: "Digital art enthusiast" (score: 0.82)
   ↓
4. Load full content from entries.jsonl
   ↓
5. Return to Gemini for context
```

## Organization: Pages

Memories organized into logical pages:

### 📖 Journal Page
- **Purpose**: Chronological diary entries
- **Structure**: Organized by date
- **Example:**
  ```
  journal/
  ├── 2026-04-12.md  (Today's entries)
  ├── 2026-04-11.md
  └── earlier/
      └── 2026-03-*.md
  ```

### 📚 Topics Page
- **Purpose**: Group memories by subject
- **Structure**: Organized by topic
- **Example:**
  ```
  topics/
  ├── programming.md (All mentions of coding)
  ├── gaming.md (Game-related memories)
  ├── relationships.md (People mentioned)
  └── ...
  ```

### 🎭 Roleplay Page
- **Purpose**: Fictional/scenario-based memories
- **Structure**: By character or scenario
- **Example:**
  ```
  roleplay/
  ├── adventure_fantasy.md
  ├── detective_mystery.md
  └── ...
  ```

## How It Works in Practice

### Scenario 1: User Mentions Past Event

```
User: "Remember when I told you I was moving last month?"

1. Memory Engine searches for entries with:
   - Keywords: "moving", "move", "relocating"
   - Time range: ~30 days ago
   
2. Finds: "User mentioned moving to new apartment"
   
3. Retrieves context and provides to Gemini:
   "Earlier conversation: User is relocating to new city"
   
4. Gemini can reference it:
   "Yes! How's the new place treating you?"
```

### Scenario 2: Personality Hook
```
User: "I just learned a new programming language!"

1. Message processed by personality.py
   ↓
2. NLP extracts:
   - Interest: programming
   - Emotion: excited
   ↓
3. Memory added:
   {
     "content": "User learned new programming language enthusiastically",
     "entities": ["programming"],
     "page": "topics"
   }
   ↓
4. Also triggers progression system:
   - Activity logger notes: "User interested in programming"
   - Creates recommended quest: "Teach me about your language"
   - May unlock: "Programming Buddy" achievement
```

## Technical details

### JSONL Format
Each line is complete JSON document:
```json
{"id": "mem_001", "timestamp": "2026-04-12T10:00:00Z", ...}
{"id": "mem_002", "timestamp": "2026-04-12T10:05:00Z", ...}
```

**Advantages over single JSON file:**
- Don't need to parse/rewrite entire file
- Can append incrementally
- Partial corruption doesn't affect whole file
- Easy to stream/process line-by-line

### SQLite FTS Indexing
```sql
-- Create FTS virtual table
CREATE VIRTUAL TABLE fts_entries USING fts5(
  content,
  entities,
  page,
  timestamp
);

-- Add entry
INSERT INTO fts_entries VALUES (
  'User learned Python',
  'Python',
  'topics',
  '2026-04-12T10:00:00Z'
);

-- Search
SELECT * FROM fts_entries 
WHERE content MATCH 'python'
ORDER BY rank;
```

**Why FTS5?**
- Handles natural language (stemming, etc.)
- Phrase search: `"machine learning"`
- Boolean: `python AND web`
- Fast: O(log n) lookup
- Integrated in SQLite (no external DB)

## Persistence Strategy

### Write Pattern
1. New memory created in RAM
2. Immediately appended to `entries.jsonl`
3. Separately indexed in SQLite
4. Both operations async (don't block response)

### Recovery
If crash occurs:
- JSONL file is append-only → never corrupted mid-entry
- SQLite can rebuild from JSONL if needed
- User never loses memories

### Cleanup
- Old memories (>1 year) optionally archived
- Index periodically optimized (VACUUM)
- Manual export for backup

## Future Enhancements

### Semantic Search
- Vector embeddings of memories
- Search by meaning, not keywords
- "Find memories about being happy" (semantic, not exact match)

### Memory Chains
- Link related memories
- Build inference paths
- "You seemed stressed then, but happy now - why?"

### Selective Forgetting
- Option to "forget" certain memories
- Respect privacy concerns
- User-controlled memory lifecycle

---

**Related:** [Personality System](./Personality-System) | [Backend](./Backend) | [Progression System](./Progression-System)
