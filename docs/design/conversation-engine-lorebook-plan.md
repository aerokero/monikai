# MonikAI Conversation Engine and Lorebook Plan

**Status:** accepted architecture, implementation in progress  
**Created:** 2026-07-30  
**Scope:** language, reasoning, lore, memory boundaries, and voice delivery

## Implementation progress

- **Phase 1 foundation:** implemented. SQLite persistence, typed models,
  namespaced entries, World Stack, exact-key/constant/pin activation, sticky
  turns, budgets, trust boundary, context rendering, and diagnostics are
  covered by tests.
- **Phase 2 context slice:** implemented. The active response author now
  receives the full character package, only the current conversation thread,
  World Snapshot, and activated lore through one immutable per-turn compiled
  context. Retries reuse that context.
- **Phase 2 author quality slice:** implemented. The response author uses a
  provider-neutral text-model boundary, explicit conversational rules, and a
  deterministic semantic validator. A failed candidate receives at most one
  bounded correction pass; failure or timeout preserves the original answer.
- **Phase 2 speech-only slice:** implemented for ordinary conversation.
  Authored display text is passed unchanged to a dedicated Gemini TTS model,
  which returns raw PCM and never receives dialogue history or permission to
  author another response. TTS failure preserves the visible authored text.
  Gemini Live is suppressed after voice ASR finality.
- **Compatibility boundary:** operational, tool, attachment, and visual turns
  still use the legacy Live capability loop until tool execution is moved
  behind the text-first engine. `speech.delivery_mode=live_renderer` provides
  an explicit rollback; it is not the default.
- **Tool migration slice:** implemented for the first read-only set: local
  time/date, current weather, and reminder listing. Runtime results are escaped
  as trusted per-turn evidence, then the text model authors the only user-facing
  answer. Existing permission flags remain authoritative; a tool requiring
  confirmation stays in the compatibility loop.
- **Native tool-planning slice:** implemented for the reminder domain. The
  provider returns structured function calls for read, create, and cancel;
  execution remains application-owned. A shared executor is used by both the
  text-first engine and legacy Live compatibility path. Mutating calls require
  deterministic evidence of explicit, non-negated user intent and preserve the
  existing confirmation channel. Denial is returned to the text author and the
  operation is not executed.
- **Calendar and notes migration:** implemented. Calendar list/create/update/
  delete and notes read/append/replace now use provider-native planning and the
  shared executor in both text-first and compatibility paths. Calendar and
  notes mutations require explicit non-negated intent; append and whole-file
  replacement are separate capabilities with separate permissions.
- **Explicit memory/recall migration:** implemented for durable-memory search,
  past-conversation recall, explicit memory writes, and sandboxed page reads.
  Ordinary facts do not invoke the memory planner. A write requires an explicit,
  non-negated "remember this" request, executes once, and returns its status to
  the response author. Markdown reads are restricted to `memory/pages`; absolute
  or relative traversal outside that root is rejected.
- **Memory-page write hardening:** implemented. `MemoryEngine` now resolves
  every get/create/append target under `memory/pages`, while retaining absolute
  paths that are genuinely inside that root for internal journal callers.
  New-page titles/tags are normalized before frontmatter generation. Explicit
  create and append requests use native planning, permission checks, and the
  shared executor; append never replaces existing page content.
- **Spotify read migration:** implemented for connection status, currently
  playing, playlists, and recently played tracks. Casual Spotify mentions do
  not invoke the planner. Results pass through the shared executor and return
  to the text author as evidence. OAuth URL generation remains in the explicit
  compatibility/UI flow so a long authorization URL is not spoken by TTS.

## 1. Goal

Monika's final response is authored by an intelligent text model with a stable
character package and explicit conversational context. Audio is transport:
speech-to-text before reasoning and text-to-speech after reasoning. No audio
model may reinterpret or rewrite an already authored response.

The other central source of context is a first-class lorebook system. It stores
knowledge about Monika's real world, supports imported fictional worlds, and
allows an explicit scenario to mix those worlds without silently contaminating
their canon.

## 2. Architectural principles

1. **One owner of the response.** `ConversationEngine` is the only component
   that authors Monika's final text.
2. **Audio does not reason.** STT produces a final transcript with turn
   metadata; streaming TTS receives final text plus delivery guidance.
3. **Identity is not memory.** Monika's character package remains curated,
   versioned data.
4. **Lore is not personal memory.** Facts about a world and its entities live
   in lorebooks; facts about the user and relationship remain in memory.
5. **Current state is not lore.** Time, weather, screen, music, and device
   state remain in `WorldSnapshot`.
6. **Worlds are namespaced.** Contradictory facts may coexist in separate
   worlds. The active `WorldStack` decides which canon applies.
7. **Retrieval is selective and inspectable.** Lore entries are activated by
   pins, constants, entity/key matches, semantic relevance, relations, and a
   token budget. Every activation records its reason.
8. **Imported lore is data by default.** Only trusted lorebooks may contribute
   behavioral instructions.
9. **Learning happens after the response.** Memory and lore extraction are
   asynchronous and cannot replace or distort the conversational reply.
10. **Quality is evaluated on conversations.** Wiring tests are necessary but
    multi-turn Polish dialogue scenarios are the release gate.

## 3. Knowledge boundaries

| Layer | Responsibility | Example |
|---|---|---|
| Character package | Monika's identity, temperament, voice, opinions | Monika values honesty over comfort |
| User memory | Stable facts and preferences about the user | Bartek sometimes drinks coffee at work |
| Episodic memory | Meaningful shared events | They watched *Blade Runner 2049* together |
| Lorebook | Entities, rules, history, and canon of a world | Arasaka controls Mikoshi |
| World Snapshot | Ephemeral here-and-now state | It is Thursday morning and raining |
| Conversation history | What was said in the active thread | The last turns of the current discussion |

The existing `MemoryEntry(type="world")` is legacy compatibility, not the
target lore representation. It has no world namespace, activation rules,
provenance, canon status, or conflict semantics.

## 4. Target runtime

```text
audio
  -> STT
  -> TurnManager(final transcript, confidence, turn_id)
  -> ContextCompiler
       -> character package
       -> current conversation
       -> user and relationship memory
       -> WorldStack
       -> activated lore entries
       -> WorldSnapshot
  -> ConversationEngine / intelligent text model
  -> response validator
  -> final text
  -> streaming TTS

after the response:
  -> memory extractor
  -> lore fact extractor
  -> accepted facts or review candidates
```

The turn pipeline is idempotent: one final user `turn_id` may produce exactly
one accepted assistant response.

## 5. World Stack

Every conversation has an explicit stack of active worlds:

```text
base reality
  + selected imported lorebooks
  + optional scenario overlay
```

Supported reality modes:

- `grounded`: fictional lore is discussed as fiction;
- `crossover`: selected fictional lore is present in Monika's reality;
- `roleplay`: active lore is the current reality of the scene;
- `ambiguous`: deliberate, user-selected uncertainty between frames.

`grounded` is always the default. A mode change must be explicit or be part of
an explicitly started scenario.

Conflict precedence inside a conversation:

```text
scenario overlay
> user-pinned correction
> active lorebook canon
> facts learned by Monika
> unsupported model knowledge
```

This precedence never deletes contradictory facts from other world namespaces.

## 6. Lorebook model

A lorebook defines:

- stable ID, name, description, and kind;
- trust and editability;
- default reality mode;
- default context budget;
- enabled state and priority;
- import/provenance metadata.

A lore entry defines:

- an ID unique inside its lorebook;
- title and standalone content;
- entry type: knowledge, scene, dialogue example, or behavior instruction;
- primary and optional secondary activation keys;
- entity names and relations;
- match mode, priority, sticky duration, and constant/pinned state;
- canon status, confidence, source, and timestamps.

Initial persistence uses SQLite for transactional CRUD, FTS, activation state,
and diagnostics. YAML/JSON/Markdown are import and export formats rather than
parallel runtime stores.

## 7. Lore activation

The Context Compiler selects lore in this order:

1. entries pinned by the active scenario or user;
2. constant entries from active lorebooks;
3. primary/secondary key and entity matches in recent turns;
4. semantic retrieval;
5. one-hop relation expansion;
6. sticky entries retained for a configured number of turns.

Candidates are sorted by explicit priority and relevance, then packed into a
per-conversation token budget. The activation trace records the entry, world,
reason, score, turn, and final inclusion decision.

Behavior instructions are excluded unless their lorebook is trusted.

## 8. Learning world knowledge

After a completed turn, an extractor routes candidate information:

```text
about the user                 -> user memory
about a shared event           -> episodic memory
about current transient state  -> no durable write / WorldSnapshot
about a world entity or rule   -> lore candidate
```

A lore candidate contains source session and turn IDs, confidence, target
lorebook, proposed operation (`create`, `extend`, `correct`, `conflict`), and
review state.

Only high-confidence, low-risk additions may be accepted automatically.
Corrections, conflicts, imported-canon changes, and behavior instructions
require review. The UI must expose what Monika learned and why.

## 9. Character package

The response author receives the same complete package on which quality is
evaluated:

- compact identity core;
- concrete opinions and preferences;
- Polish pragmatic conversation rules;
- positive, multi-turn example dialogues;
- relationship context;
- current scenario;
- a near-history character note when needed.

Required example classes include: answers without a question, a user saying
"I don't know", damaged ASR, ordinary small talk without psychology, calm
disagreement, topic closure, and returning to an unfinished thread.

## 10. Evaluation

`conversation_probe` becomes a multi-turn quality harness. Each trace records:

- input revisions and final ASR;
- `turn_id` and confidence;
- compiled context and activated lore;
- authored response and validation result;
- TTS input;
- memory/lore extraction candidates;
- latency per stage.

Release metrics include unsupported psychological inference, repeated thesis,
question pressure, false memory claims, context contamination between worlds,
character consistency, Polish naturalness, and exactly-once turn handling.

## 11. Delivery phases

### Phase 1 — Lorebook foundation

- SQLite schema and typed models;
- lorebook/entry CRUD;
- conversation World Stack;
- key, constant, pin, priority, budget, and sticky activation;
- trust boundary for behavior instructions;
- activation diagnostics and tests.

### Phase 2 — Text-first Conversation Engine

- `TurnManager`, `ContextCompiler`, and provider-neutral model adapter;
- one author for final text;
- full character package available to the author;
- semantic response validator;
- dedicated speech-only provider for ordinary conversational turns;
- conservative routing of tool and multimodal turns to the compatibility loop.
- read-only `author → tool evidence → author` loop for time, weather, and
  reminder listing.
- provider-native planning and shared execution for reminder creation and
  cancellation, with exactly-once and confirmation tests.
- calendar and notes domains behind the same planner, permission boundary, and
  shared executor.
- explicit memory search/recall/write and sandboxed memory-page reads behind
  the shared executor.
- sandboxed memory-page create/append with compatibility-safe internal paths.
- read-only Spotify context behind the text-first planner and shared executor.
- smart-home discovery and confirmation-gated light control behind the same
  validated planner and multi-platform executor.

### Phase 3 — Full lore retrieval and import

- semantic retrieval and relation expansion;
- SillyTavern World Info import;
- generic YAML/JSON/Markdown import/export;
- world/scenario selection and activation inspection.

### Phase 4 — Lore learning

- asynchronous fact routing;
- lore candidates, review, correction, and versioning;
- editable UI for learned world knowledge.

### Phase 5 — Audio separation

- dedicated STT with finality/confidence metadata;
- dedicated TTS with immutable transcript (**non-streaming slice implemented**);
- Gemini Live removed from ordinary conversational response authorship
  (**implemented**);
- operational/tool turns migrated away from Live response authorship;
- remaining mutating and confirmation-gated tool domains migrated behind the
  shared executor;
- dedicated STT replaces Live ASR;
- streaming TTS with pace, emotion, and pause guidance;
- interruption and barge-in preserved at `TurnManager` level.

### Phase 6 — Preference-driven polish

- regenerate/swipe and selected-response tracking;
- blind model A/B evaluation on the dialogue suite;
- iterative character examples based on actual owner preferences.

## 12. First implementation slice

The delivered slices now cover the Phase 1 lore foundation, immutable
per-turn context compilation, provider-neutral text authorship, response
validation, and direct speech-only delivery for ordinary conversation.
