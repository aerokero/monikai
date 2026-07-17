# Conversation and memory quality

Status: active architecture  
Revised: 2026-07-17

## Principle

Memory is an available library, not ambient conversation context.

Monika should normally answer from the current Live conversation. Old facts,
summaries and transcripts are fetched only when she explicitly needs them
through `memory_search` or `recall_conversation`.

Absence of recalled memory is preferable to an unrelated memory.

## Runtime flow

### Ordinary turn

```text
user message -> current Live context -> response
```

No automatic FTS query runs on the user's raw message. No memory block, user
state, inner state or list of unfinished topics is injected.

### Past-reference turn

```text
explicit reference / missing known fact
    -> memory_search or recall_conversation tool
    -> result scoped to this response
```

The model supplies a concise search topic. The storage layer does not attempt
to understand Polish conversation or infer intent.

### Session close

The digest has a deliberately narrow output:

- a short conversation title;
- a 1-3 sentence factual recap for conversation history.

It does not create:

- an agenda or follow-up backlog;
- first-person synthetic episodes;
- a psychological user state;
- an inner state for Monika;
- a mood inferred from the transcript;
- durable memory entries.

Reminders and calendar events handle real future commitments. Conversation
history handles old discussions. Neither responsibility belongs to a generated
agenda.

## Proactivity

Provider-native proactive audio is disabled by default because it cannot be
deduplicated at application level. MonikAI's Telegram proactivity is based only
on a real time gap and strict rate limits. It receives no generated agenda or
synthetic psychological context.

## Conversational rules retained

- Zero questions is a valid response.
- A completed small topic may end naturally.
- Screen visibility does not imply causal relevance to the current topic.
- Exact-wording questions require source wording; a summary cannot be promoted
  to a quote.

These are behaviour contracts, not memory-selection heuristics.

## Existing data

Old `agenda_items`, episodic entries and generated soul files may remain in an
existing installation for auditability, but the active runtime does not read
or inject them. New databases no longer create an agenda table, and new
digests no longer produce those records.

Any destructive cleanup of existing user history must be a separate migration
with an export and review step.

## Regression guarantees

- An ordinary user message causes no memory search.
- Startup prompt contains no stored memory or generated state.
- Digest never writes memory entries.
- `significant=false` stores only skipped-session metadata.
- No active runtime component reads `agenda_items`.
- Native proactive audio stays opt-in.
