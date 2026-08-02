# Conversation Probe

`scripts/conversation_probe.py` is an automated dialogue-quality regression
harness. It does not create a second response path: a probe turn goes through
the real session, context compiler, lore activation, tool planner, text
author, validator, transcript, and speech configuration — the same code a
live user turn takes.

(The interactive "Conversation Lab" swipe/draft UI that used to sit in the
chat footer — sample several uncommitted replies, swipe between them, pick
one — was removed 2026-08-02 as unneeded product surface. It reused this same
probe infrastructure but is gone; this doc now covers only the regression
harness below.)

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
