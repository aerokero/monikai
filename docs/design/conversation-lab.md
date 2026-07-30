# Conversation Lab

Conversation Lab extends `scripts/conversation_probe.py` instead of creating a
second response path. A probe turn goes through the real session, context
compiler, lore activation, tool planner, text author, validator, transcript,
and speech configuration.

## Scenario v2

Version 2 remains compatible with the original `turns[].expect` format and adds:

- `defaults.expect` shared by every turn;
- `conversation_expect` for multi-turn behavior;
- per-turn question, sentence, length, memory, inference, repetition, and lore
  isolation checks.

The initial golden regression is:

`scripts/scenarios/coffee_focus_regression.json`

It guards against turning ordinary coffee and concentration remarks into
personality diagnoses, durable memory claims, or a chain of repeated questions.

## Running

With the app and its backend already running:

```powershell
python scripts/conversation_probe.py `
  --scenario scripts/scenarios/coffee_focus_regression.json `
  --report tmp/coffee_focus.md `
  --jsonl tmp/coffee_focus.jsonl
```

Compare a later run with a saved trace:

```powershell
python scripts/conversation_probe.py `
  --scenario scripts/scenarios/coffee_focus_regression.json `
  --baseline tmp/coffee_focus-baseline.jsonl `
  --report tmp/coffee_focus-current.md `
  --jsonl tmp/coffee_focus-current.jsonl
```

## Artifacts

The Markdown report is intended for quick human review. JSONL is the stable
machine-readable record:

- one versioned run record with scenario fingerprint;
- one record per turn with expectations, redacted runtime trace, model/context
  diagnostics, checks, and round-trip latency;
- one conversation-level summary record.

Keys that may contain credentials are redacted. Prompt content is represented
by SHA-256 fingerprints and character counts in the Thinker trace; activated
lore is recorded by namespaced UID, reason, and score.

## Release policy

Deterministic failures are release regressions. A future blind model judge may
add Polish naturalness and character scores, but it must not override concrete
failures such as false memory claims, world leakage, or question pressure.

## Interactive swipe mode

The sparkle button in the chat footer enables Conversation Lab for typed,
tool-free turns. In this mode:

1. the user turn is recorded once;
2. the text author compiles one immutable context and samples up to three
   response drafts from it;
3. drafts stay outside the transcript, speech renderer, memory and lore
   learning;
4. the user swipes between variants and explicitly selects one;
5. only the selected variant is delivered, spoken and made eligible for lore
   learning.

Pending response sets are kept in memory for at most 15 minutes and are bound
to the originating Socket.IO client. A repeated or cross-client selection
cannot commit a second answer.

The UI now reports context compilation, model generation and completed
candidate counts. It stops waiting after 35 seconds and reports backend
disconnects instead of leaving a permanent spinner.

## Safety and observability

- A configured context compiler is fail-closed: no context means no authored
  reply.
- Validation runs for every parsed response. A failed, timed-out or still
  unsafe revision is not delivered.
- Traces record context status/error, primary/retry/fallback attempts, model
  names, latency, candidate validation and per-candidate timing.
- Ambient world data is topic-filtered. Weather, Spotify, time, camera and gap
  information cannot become an unrelated conversation topic merely because it
  exists in the snapshot.
- The canonical database is `data/monika.db`. Startup migrates rows once from
  the historical split path `backend/data/monika.db`.
- Gemini 3 uses `thinking_level=medium`; revision passes use `low` to stay
  within their shorter latency budget.

The 2026-07-30 live coffee/focus run passed all language, context and
validation checks. Its remaining release failures were model-availability
alarms: `gemini-3.5-flash` returned 503 and the configured Pro fallback had no
free-tier quota, so the validated emergency author was
`gemini-3.5-flash-lite`.
