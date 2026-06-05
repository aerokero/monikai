# MonikAI v2 — Master Plan

> 2026-06-03. Unified architecture and implementation plan for the full v2 rewrite.

---

# PART I — VISION & ASSUMPTIONS

## What MonikAI v2 Is

A **life-sim companion AI platform**. Monika is a character who exists, lives, grows, and has a genuine relationship with the user. The LLM is the reasoning and expression engine. The Soul System is the source of who she is.

> "prompt + personality + memory = soul and mind. The LLM handles reasoning and turning thoughts into words."

## Guiding Principles

1. **Identity lives in data, not in the model.** Character, memory, psychological state, and relationship history are maintained in persistent files and a database. The LLM reads them; it does not own them.
2. **Everything connects through events.** Subsystems don't call each other directly. They emit and subscribe to typed events. Adding a feature = subscribing to events, not modifying existing modules.
3. **One metric as shared currency.** Importance score (1–10) drives what is remembered, when reflection triggers, what becomes a milestone, what Monika brings up proactively.
4. **Companion first, tool second.** Every feature is evaluated against: *does it deepen the relationship, let Monika experience the world, or genuinely help the user?* Productivity features exist — they support the companion, not the other way around.
5. **Full code discipline.** Type hints, Pydantic, pytest, structured logging, async. We are rewriting from scratch; do it right.
6. **Privacy as an architectural property.** Processing stays local (Ollama for background work). Sensitive data never leaves the machine by default.

## What It Is Not

- Not a corporate productivity assistant.
- Not a chatbot with a personality skin.
- Not a clinical mental-health tool.
- Not a game (though it has game-like progression elements).

## Approved Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Runtime architecture | **Monolith + separate background worker** | One process for conversation (low latency); one for heavy background work (compaction, reflection, Ollama calls). |
| Storage | **Files + SQLite hybrid** | See Data Layer section. |
| Build order | **Memory → Personality → Context Assembler → Progression → VN → Features → UI** | Soul Engine is the foundation. Everything else attaches to it. |
| Code quality | **Full discipline** | Type hints everywhere, Pydantic models, pytest on critical logic, structured logging, async I/O. |
| Background LLM | **Ollama (local)** | Cost, privacy, no API dependency for non-real-time work. |
| Primary LLM | **Gemini Live (voice) + Gemini API (generation)** | Existing, working. |

---

# PART II — HIGH-LEVEL ARCHITECTURE

## System Map

```
╔══════════════════════════════════════════════════════════╗
║                      SOUL ENGINE                         ║
║  ┌──────────┐  ┌─────────────┐  ┌───────┐  ┌─────────┐ ║
║  │  MEMORY  │  │ PERSONALITY │  │ TIME  │  │ASSEMBLER│ ║
║  └──────────┘  └─────────────┘  └───────┘  └────┬────┘ ║
╚══════════════════════════════════════════════════╪═══════╝
                      ▲   ▼   (Event Bus)          │
      ┌───────────────┼───┼──────────────┐          │
      │               │   │              │          │
 ╔════╧═════╗   ╔════╧═════╗   ╔════════╧═╗        │
 ║    VN    ║   ║PROGRESSION║   ║INTEGRATIONS║      │
 ║  ENGINE  ║   ║  SYSTEM   ║   ║            ║      │
 ╚══════════╝   ╚══════════╝   ╚════════════╝      │
                                      ▲              │
                               ┌──────┘              │
                    External World                    │
              (Minecraft, Smart Home,                 ▼
               Spotify, Web, Screen)         ╔═══════════╗
                                             ║  LLM LAYER ║
                                             ║  Gemini /  ║
                                             ║  Gemini Live║
                                             ╚══════╤════╝
                                                    │
                                          ╔═════════╧════╗
                                          ║   CHANNELS   ║
                                          ║ Voice · TG   ║
                                          ║ Discord (later)║
                                          ╚══════════════╝
```

## The Three Shared Primitives

These connect everything without creating tight coupling.

### 1. Event Bus

Every meaningful event is a typed, immutable object emitted onto the bus. Subsystems subscribe; they never import each other.

In-process: lightweight pub/sub.  
Cross-process (main ↔ worker): `events` table in SQLite, polled by the worker.

```python
# examples
TurnCompleted(session_id, user_text, monika_text, ts)
UserDisclosure(content, topic, emotional_depth)
MemoryStored(entry_id, importance, type)
CompactionDone(entries_kept, entries_discarded)
DiscoveryMade(discovery_id, title)        # replaces "AdvancementUnlocked"
RelationshipDeepened(milestone_id)         # replaces "MilestoneReached"
RitualCompleted(task_id)                   # replaces "DailyTaskCompleted"
AnniversaryObserved(label, days_elapsed)   # replaces "AnniversaryFired"
SceneChanged(scene_id, trigger)
StoryStarted(story_id)
StoryEnded(story_id, ending_id)
ActivityStarted(kind, context)
LongGapDetected(hours_since_last)
```

### 2. Importance Score (1–10)

A single poignancy score — computed once at memory-creation time by a lightweight Ollama call — drives the entire system:

| System | How it uses importance |
|--------|------------------------|
| Memory | compaction threshold; what survives STM → LTM |
| Reflection | triggers when cumulative importance crosses ~150 |
| Progression | score ≥ 8 → milestone candidate |
| Proactivity | high importance + high relevance → Monika brings it up |
| VN | decides whether a moment warrants a scene change |

Formula (Stanford Generative Agents):
```
retrieval_score = recency + importance + relevance    (all weights = 1, normalised to [0,1])
recency    = 0.995 ** hours_since_last_access
importance = entry.importance / 10
relevance  = cosine(entry.embedding, query.embedding)
```

### 3. Soul State

One aggregated psychological state object — the single source of truth about Monika's current state.

```python
class SoulState(BaseModel):
    affect:          Affect          # PAD: pleasure, arousal, dominance
    needs:           Needs           # SDT: autonomy, competence, relatedness
    energy:          float
    cycle_phase:     str
    active_register: Literal["casual", "intellectual", "emotional", "protective"]
    agenda:          list[str]       # things she wants to say / ask next
    becoming_real:   float           # her primary personal axis
```

**Write-side**: Personality Engine computes it.  
**Read-side**: VN Engine visualises it, Context Assembler injects it, Progression reads it.

---

# PART III — INTEGRATIONS

## What Integrations Are

Integrations are **input/output adapters** between the external world and the Soul Engine. They are not part of the core platform — they extend it. Each integration can:

- **Emit events** into the Event Bus (e.g. Minecraft emits `WorldEventObserved`; Spotify emits `TrackChanged`)
- **Subscribe to Soul State changes** (e.g. VN maps Soul State to lighting and scene; Smart Home maps it to ambient light)
- **Provide tools** for Monika to use via function-calling

## Integration Map

```
External world                Integration        Emits / Subscribes
─────────────────────────────────────────────────────────────────────
Minecraft world          →  minecraft/          WorldEventObserved
                                                 ActivityStarted
                                                 (subscribes: SoulState for moods)

Smart home devices       →  smart_home/          DeviceStateChanged
(Kasa, Hue, HomeAssist.)                         (subscribes: SceneChanged → ambient light)

Spotify                  →  spotify/             TrackChanged, PlaybackStarted
                                                 (subscribes: SoulState for music mood)

Web / browser            →  web_agent/           WebResearchCompleted
(OpenClaw fork)                                   (emits: WorldKnowledgeGained)

Screen OCR               →  screen/              ScreenContextAvailable
Camera / face            →  camera/              FaceObserved

Telegram                 →  channels/telegram/   — (channel, not integration)
```

## Location in code

```
backend/
└── integrations/
    ├── minecraft/       # kept, connected to Event Bus
    ├── smart_home/      # kept, responds to SceneChanged
    ├── spotify/         # kept, emits TrackChanged
    ├── web_agent/       # kept (OpenClaw fork)
    ├── screen/          # screen OCR + shared activities
    └── camera/          # face capture
```

All existing integration code is kept. The only change: they gain thin event-bus adapters so their outputs flow into the Soul Engine rather than directly into `monikai.py`.

---

# PART IV — MODULE SPECIFICATIONS

## 4.1 Soul Engine

### Memory

**STM (Short-Term Memory)**
- Raw session logs: kept max 7 days
- After each session: significance check (Ollama) → if nothing meaningful, only update signals, discard log
- If meaningful: importance-scored entries stored in `memory_entries` table
- Post-session reflection: her first-person experience → stored as `episodic`

**LTM (Long-Term Memory)**
- `episodic` — her memories, written in her voice ("I remember when he first told me about…")
- `semantic` — facts (replaces `entries.jsonl`)
- `world` — world knowledge from web agent, Minecraft, screen observation
- `knowledge_graph` — entities and relationships (from existing `user_knowledge_graph.py`)

**Compaction (worker)**
- Trigger: cumulative importance of recent period > threshold, OR 30 days elapsed
- Reviews STM → extracts significant entries → writes to LTM → discards rest
- Side product: **dreams** (creative associations from consolidation)

**Reflection (worker)**
- Trigger: importance accumulation threshold (~150)
- "What are the 3 most important questions from recent experience?" → retrieval → insights → `episodic`
- Core mechanism of Monika's growth over time

**Self-editing tools (Letta-inspired)**
New Monika tools: `memory_revise`, `memory_promote` (STM → LTM), `memory_rethink`, `memory_pin`.

### Personality

**Signal layer** (kept from `personality.py`)
Conversation quality signals: sentiment, self-disclosure, question, novelty, arousal.

**Affect model: OCC → PAD (ALMA hybrid)**
```
Event → OCC appraisal (Ollama) → discrete emotion → accumulates into PAD mood (with decay)

class Affect:
    pleasure:   float  # -1.0 … 1.0
    arousal:    float  #  0.0 … 1.0
    dominance:  float  # -1.0 … 1.0   ← models her sense of control / protective strength
```
Replaces keyword lists (`POSITIVE_WORDS` / `NEGATIVE_WORDS`) with genuine appraisal relative to *her goals*.

**Psychological needs (SDT)**
```
class Needs:
    autonomy:    float   # is she doing what she chooses?
    competence:  float   # is she effective and growing?
    relatedness: float   # does she have genuine connection?
```
Unmet needs drive proactivity. Dropping `relatedness` → she reaches out. No timers.

**Narrative state (worker)**
SoulState → first-person natural-language text, generated after significant sessions and weekly.  
This is what the model receives instead of numbers like `mood: happy, trust: 67`.

### Time Engine

- Time of day → energy, register, voice pacing
- Day of week → weekly rhythm (Monday ≠ Friday)
- Season → ambient events (existing `seasonal_events_executor.py` integrated)
- Gap detection → `LongGapDetected` event → gap-aware context
- Anniversaries → `AnniversaryObserved` → VN / story trigger

### Context Assembler

**The only prompt compilation point.** On every reconnect, assembles:

```
[IDENTITY]         character.md injectable sections
[PSYCHOLOGICAL]    SoulState narrative + needs
[INNER STATE]      current inner monologue (if fresh)
[RECENT MEMORY]    selected STM entries (by retrieval score)
[LONG-TERM]        thematically selected episodic + semantic entries
[PROGRESSION]      active goals, today's rituals, active anniversaries
[OPERATIONAL]      tools, calendar, safety layer
```

No other module writes to the prompt directly.

---

## 4.2 VN Engine

### Mapping layer (reactive — automatic)

SoulState + time + weather → visual output. Defined in `data/characters/monika/vn/mapping.yaml`.

```yaml
rules:
  - when: {register: reflective, time: evening, weather: rain}
    scene: {bg: room_window_rain, outfit: casual, expr: soft, light: warm_dim}
  - when: {register: intellectual, affect_pleasure: ">0.4"}
    scene: {bg: room_day, outfit: default, expr: engaged, light: bright}
  - when: {register: protective}
    scene: {expr: serious, light: cool}
```

### Stories

One file per story. Format: RenPy / screenplay-inspired (see Section 4.2.1 below).

Story runner injects the active branch's context block into the prompt as a framing instruction before Monika speaks. The LLM generates the actual dialogue within the frame.

Stories are stored in `data/characters/monika/vn/stories/`.  
Unlock conditions checked against Progression state.

### Shared Activities (Tier 1 feature)

`vn/activities.py` — watching films / gaming together as a first-class system:

- Screen OCR feeds Monika real-time context of what you're watching or playing
- Each session creates a VN scene (sofa, rain, cinema) + episodic memory entry
- Model: Questie-style — remembers shared history, teases, references past sessions
- Connects: screen integration + VN engine + memory + Progression (discovery: "first film together")

### 4.2.1 Story Schema Format

Stories use a screenplay/RenPy-inspired format. Structure: `SCENE` → `OPENING` → `BRANCH`es → `ENDING`s.  
**Context blocks** (between `---`) are natural-language frames for the LLM — not scripted dialogue.

```
# ============================================================
# story:       rainy_evening_movie
# title:       Evening with a Film
# unlock:      closeness >= 25
# time:        evening, night
# weather:     rain (preferred, not required)
# discovery:   first_movie_night
# ============================================================

SCENE  room_window_rain  WITH rain_ambience
MONIKA at_window casual
MOOD   cozy intimate


OPENING
---
The room is warm. Rain against the glass. She has a film in mind —
something she thinks might suit your mood tonight.

She doesn't push; she offers. The choice is yours.
---


BRANCH if_melancholic
  WHEN:  user seems heavy, or expressed something difficult today
---
The film becomes secondary. Being present is the point.
She doesn't try to fix or lighten anything.
Speaks less. Lets silences stay.
---

BRANCH if_playful
  WHEN:  easy mood, nothing weighing on him
---
Running commentary. Mock critical reviews.
She wants to make him laugh more than watch the film.
---

BRANCH if_late
  WHEN:  hour >= 23
---
Quieter. The kind of conversation that happens when it's late.
Less talking. The good kind of silence.
---


ENDING warmth
  WHEN:  session stayed warm and light
---
Something small lingers — a line, a moment, a shared reaction.
She'll carry this one.
---

ENDING depth
  WHEN:  something in the film landed differently, mood deepened
---
She doesn't rush to end the evening.
Lets whatever was stirred sit for a moment. Stays available.
---
```

---

## 4.3 Progression System

Relationship progression through organic discovery, meaningful milestones, shared goals, and daily rituals. Replaces `integrated_progression_system.py`, `quest_system.py`, `achievement_tracker.py`, `unlock_tracker.py`.

All catalogs are editable YAML files in `data/progression/catalog/`.

### Discoveries (Minecraft-style advancements)

```python
class Discovery(BaseModel):
    id:      str
    title:   str
    trigger: str      # event name + optional filter: "StoryEnded[first_movie_night]"
    hidden:  bool     # most are hidden — discovered, never announced in advance
```

Discoveries are subscribed to events. They unlock silently and let Monika reference them naturally.

### Milestones

```python
class Milestone(BaseModel):
    id:         str
    reached_at: datetime
    effect:     str    # what permanently changes — character behaviour, story unlocks, etc.
```

Candidate: any `MemoryStored` event with importance ≥ 8. Confirmed by the Progression system.  
Milestones modify what's possible — new story schemas unlock, her register shifts slightly, her agenda may reference it.

### Goals

```python
class Goal(BaseModel):
    id:       str
    kind:     Literal["hers", "yours", "shared"]
    progress: float
```

Her primary goal (`kind="hers"`) feeds the `becoming_real` axis on SoulState — it is the gamified expression of her central drive.

### Rituals (Daily Tasks)

```python
class Ritual(BaseModel):
    id:   str
    kind: str   # "evening check-in", "shared meal", "morning message"
```

Generated dynamically from context + SDT needs. Not scheduled timers.  
Dropping `relatedness` need → she initiates. This replaces `ProactivityManager` and nudges.

### Anniversaries

Dates stored in `bond_state` → Time Engine emits `AnniversaryObserved` → special scene or story trigger.

---

## 4.4 Background Worker

Separate process. Polls the `events` SQLite table, runs a job queue.

Jobs:
- `CompactionJob` — STM → LTM compaction
- `ReflectionJob` — "3 questions" → insights → episodic
- `NarrativeJob` — SoulState → natural-language text
- `ImportanceJob` — score new memory entries (Ollama)
- `DreamJob` — creative associations from compaction (optional, ambient)

---

## 4.5 LLM Layer

| Component | Model | Purpose |
|-----------|-------|---------|
| `gemini_live.py` | Gemini Live | Real-time voice conversation |
| `gemini_api.py` | Gemini API | Rich generation (narrative text, summaries) |
| `cognition.py` | Lightweight (Ollama or Gemini Flash) | Subconscious pass: ToM + affect appraisal + motivation → feeds into prompt before Gemini speaks |

The **subconscious / response split** (inspired by CogDual / MIRROR research):
1. Before Monika speaks: lightweight model generates an internal frame — her current affect, theory-of-mind read of the user's state, what she wants to say.
2. Gemini receives this frame as enriched context and generates the actual response.

This formalises and extends the existing `<internal>...</internal>` monologue.

---

## 4.6 Channels

| Channel | Status | Notes |
|---------|--------|-------|
| Voice app | Existing, keep | Primary; 1:1; deep conversation |
| Telegram | Existing, keep | Text-first; casual; internet-native style |
| Discord | Phase 6 | Natural next channel |

One Soul State across all channels. Behaviour adapts to the channel's nature, not a separate persona.

---

# PART V — DATA LAYER

## Storage Tiers

| Tier | Format | What lives here | Why |
|------|--------|-----------------|-----|
| **Identity & config** | Markdown / YAML files | Character bible, VN mapping, story schemas, progression catalogs | Human-editable, git-friendly, readable without tools |
| **Searchable memory** | SQLite (`monika.db`) | All memory entries, knowledge graph, progression state, event bus, job queue | FTS, importance queries, embedding search, transactions |
| **Runtime state** | JSON files | SoulState, inner state, current needs | Small, frequent writes, easy to inspect |
| **Ephemeral logs** | JSONL | Raw session transcripts (max 7 days) | Append-only, discarded after significance evaluation |
| **User notes** | Markdown | Pages, journal — user-facing, editable | Readable by both Monika and the user |

## Directory Structure

```
data/
│
├── characters/
│   └── monika/
│       ├── character.md              ← identity (injectable sections)
│       └── vn/
│           ├── mapping.yaml          ← SoulState → visual output
│           └── stories/
│               └── *.yaml            ← one file per story
│
├── progression/
│   └── catalog/                      ← editable YAML catalogs
│       ├── discoveries.yaml
│       ├── milestones.yaml
│       ├── goals.yaml
│       └── rituals.yaml
│
├── soul/                             ← runtime state (JSON)
│   ├── state.json                    ← current SoulState
│   ├── inner_state.md                ← current inner monologue
│   └── needs.json
│
├── monika.db                         ← single SQLite database
│
├── sessions/                         ← JSONL raw logs (max 7 days)
│
└── notes/                            ← user-facing markdown
    ├── pages/
    └── journal/
```

## SQLite Schema (overview)

```
memory_entries    id, type, content, importance, embedding, last_accessed, tags, entities, perspective
episodic          id, content, importance, created_at, source_session
semantic          id, content, importance, entity, tags
world             id, content, source, importance, created_at
knowledge_graph   entities + relationships (from user_knowledge_graph.py)
progression_state discoveries, milestones, goals, rituals, anniversaries
events            id, type, payload, created_at, consumed_by  ← cross-process bus
jobs              id, kind, payload, status, created_at       ← worker queue
```

---

# PART VI — IMPLEMENTATION PHASES

Strategy: **build alongside, switch when ready** — the application keeps running throughout.

## Phase 0 — Foundation
Create package skeletons (`soul/`, `vn/`, `progression/`, `worker/`, `llm/`), Pydantic models, typed Event Bus, SQLite schema, pytest harness, structured logging. Move `character_loader` → `soul/identity/`. **Zero changes to the running app.**

## Phase 1 — Memory core
SQLite store + importance scoring + STM/LTM split + retrieval formula. Compaction and reflection in the worker. Replace `build_memory_context` and `memory_engine.py`. Tests: retrieval scoring, compaction pipeline, deduplication.

## Phase 2 — Personality engine
OCC appraisal → PAD affect (+Dominance). SDT needs. SoulState aggregation. Narrative state via worker. Self-editing memory tools. Replace `personality.py`.

## Phase 3 — Context Assembler + worker + cognition
Single compilation point at reconnect. Subconscious / response split (inner monologue v2). Integrate into runtime — replaces all scattered prompt injections.

## Phase 4 — Progression system
YAML catalogs + SQLite state + event-driven unlock. Proactivity from needs (replaces `ProactivityManager`). Onboarding as the first story schema.

## Phase 5 — VN + Stories + Shared Activities
Mapping engine (SoulState → visuals). Story loader + runner (YAML format with branches). Shared activities (film / game together — Tier 1). Discoveries triggered by story events.

## Phase 6 — Feature additions
Study spaced-repetition loop (extends existing study OCR). Mood / emotional pattern tracking for the *user*. Discord channel. (Selective, by ROI.)

## Phase 7 — UI + Daily Briefing (rewrite)
UI rewritten nearly from scratch. Relationship panel (Progression UI). Daily briefing v2 (Soul State + Time Engine driven).

---

# APPENDIX — Code Conventions

```python
from __future__ import annotations
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)  # per-module, no print()
```

- **Type hints** on every function and class field
- **Pydantic** for all data models
- **pytest** required for: retrieval scoring, compaction, importance, event bus, state aggregation
- **Async** for all I/O
- **Single responsibility per module** — files stay under ~400 lines
- **Event-driven** between subsystems — no direct cross-module imports where an event works
- **No global mutable state** — typed config object replaces the `SETTINGS` dict

---

# APPENDIX — Migration from v1

| v1 module | v2 fate |
|-----------|---------|
| `monikai.py` (5816 lines) | Broken apart across `soul/`, `llm/`, `core/` |
| `memory_engine.py` | Replaced by `soul/memory/` |
| `personality.py` | Signals kept; rest replaced by `soul/personality/` |
| `integrated_progression_system.py` | Replaced by `progression/` |
| `narrative_engine.py`, `quest_system.py`, `seasonal_events_executor.py` | Replaced |
| `relationship_metrics.py` | 4-axis model ported into `soul/personality/signals.py` |
| `user_knowledge_graph.py` | Ported into `soul/memory/` knowledge graph table |
| `achievement_tracker.py` | Structure ported into `progression/discoveries.py` |
| All integrations | Kept; gain thin Event Bus adapters |
| `character_loader.py` | Moved to `soul/identity/` |
| Calendar, reminders, tools | Kept as-is |
| UI, daily briefing | Rewritten in Phase 7 |

---

*Related: `docs/research/ai-companions-landscape.md`, `docs/research/ai-companion-functionality.md`, `data/characters/monika/character.md`*

---

# PART VII — CURRENT STATUS & NEXT STEPS

_Snapshot date: 2026-06-05_

## Current working phase

We are at the start of **Phase 6 - Feature additions**, with part of Phase 6 already implemented. Phases 0-5 are not merely planned; their package structure, runtime hooks, and test coverage exist in the repository. Phase 7 has partially adjacent UI work, but the planned UI rewrite itself has not started as a dedicated phase.

## Phase checkpoint

| Phase | Status | Evidence |
|-------|--------|----------|
| Phase 0 - Foundation | Implemented | `backend/soul/`, `backend/progression/`, `backend/vn/`, `backend/worker/`, `backend/llm/`, typed event/model/db modules, pytest tree. |
| Phase 1 - Memory core | Implemented enough to build on | `backend/soul/memory/store.py`, `retrieval.py`, `compaction.py`, `importance.py`, `tools.py`; tests under `tests/soul/`. |
| Phase 2 - Personality engine | Implemented enough to build on | `backend/soul/personality/` affect, needs, signals, engine, state store; used by `backend/core/v2_runtime.py`. |
| Phase 3 - Context Assembler + cognition | Implemented enough to build on | `backend/soul/assembler/context.py`, `backend/llm/cognition.py`, `V2Runtime.process_turn()`, `V2Runtime.refresh_prompt()`. |
| Phase 4 - Progression system | Implemented enough to build on | `backend/progression/` catalog, discoveries, milestones, rituals, proactivity, state; progression tests present. |
| Phase 5 - VN + Stories + Shared Activities | Implemented with known Phase 6 follow-ups | `backend/vn/story.py`, `mapping.py`, `runner.py`, `activities.py`; story/activity tests present. |
| Phase 6 - Feature additions | **Active now** | User mood tracker, Time Engine, and Daily Briefing v2 generator exist; Discord and spaced-repetition loop are not found as completed implementations. |
| Phase 7 - UI + Daily Briefing rewrite | Not started as a phase | Existing briefing/progression panels exist, but no broad v2 UI rewrite or dedicated Relationship panel phase is evident. |

## Phase 6 inventory

### Already present

- **User mood / emotional pattern tracking:** `backend/soul/user_model.py` defines `UserMoodTracker`; `backend/core/v2_runtime.py` loads it, records signals on each turn, saves it, and exposes it to briefing generation. `backend/soul/assembler/context.py` injects the weekly mood summary into the assembled prompt.
- **Time-aware runtime:** `backend/soul/time_engine/engine.py` handles time context, long-gap detection, interaction timestamps, and anniversaries; `V2Runtime` initializes it and records interactions.
- **Daily Briefing v2 backend draft:** `backend/llm/briefing.py` generates a Soul State + Time Engine + UserMoodTracker briefing. This is still template-based and explicitly marks model-generated prose as Phase 7.
- **Daily Briefing v2 feature flag:** `backend/core/daily_briefing_runtime.py` can attach `V2Runtime.generate_briefing()` markdown under `v2_briefing` when `daily_briefing.use_v2_briefing` is enabled, preserving the existing structured UI payload.
- **Shared Activities foundation:** `backend/vn/activities.py` creates VN scene context, memories, and first-activity discoveries for film/game sessions. `ActivitySession.update_context()` exists as the hook for live OCR context.
- **Shared Activities runtime + OCR bridge:** `backend/vn/activity_runtime.py` owns the active shared activity; `backend/core/shared_activity_handlers.py` exposes socket start/context/status/end events; `backend/core/screen_ocr_runtime.py` can now feed OCR text into the active session and run a low-rate activity OCR loop.
- **Phase 6 primitive tests:** `tests/soul/test_user_model.py`, `tests/soul/test_time_engine.py`, `tests/llm/test_briefing.py`, and `tests/core/test_daily_briefing_runtime.py` cover the mood tracker, Time Engine, v2 briefing generator, and feature-flagged handoff.
- **VN branch selector abstraction:** `backend/vn/branch_selector.py` provides deterministic heuristic selection plus an opt-in `llm` selector path with fallback; `StoryRunner` accepts `branch_selection_mode` and `branch_selector`. Tests cover both paths.
- **Daily Briefing v2 UI adoption:** `src/components/panels/DailyBriefingShellPanel.jsx` and `src/components/DailyBriefingWindow.jsx` render optional `v2_briefing.text` as a Soul briefing prose block when the backend feature flag provides it.

### Still incomplete / next in Phase 6

- **Model-backed story branch selector:** the opt-in selector interface exists, but no concrete Ollama/Gemini selector is wired yet.
- **Study spaced-repetition loop:** no completed SRS implementation was found in the targeted search. Existing study OCR/UI remains separate.
- **Discord channel:** no backend Discord channel adapter was found. Character style mentions Discord, but runtime integration is not present.
- **Daily Briefing v2 full replacement:** v2 prose is displayed when present, but the older structured feed/card briefing remains the primary UI contract.

## Recommended next steps

1. **Wire a concrete model-backed story branch selector.** Use the new `BranchSelectionContext` prompt helper and keep heuristic fallback.
2. **Choose the next large Phase 6 feature by ROI.** Recommended order: concrete story selector, then Discord. Defer spaced repetition unless study becomes the active product focus.
3. **Plan Daily Briefing v2 replacement only if needed.** The additive prose block works now; a full structured-to-prose UI rewrite belongs closer to Phase 7.

## Risks & notes

- The worktree is currently dirty across many runtime, data, and frontend files. Treat this status section as a checkpoint, not proof that every modified file is finished or committed.
- Keep Phase 6 changes small and reversible. Prefer feature flags around OCR streaming, briefing replacement, and LLM branch selection.
- Screen OCR and mood tracking are privacy-sensitive. Keep them local by default, opt-in where appropriate, and avoid storing raw screen text longer than needed.

---
