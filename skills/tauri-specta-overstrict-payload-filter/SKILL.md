---
name: tauri-specta-overstrict-payload-filter
description: |
  Diagnose Tauri frontends where the listener is attached in time, the Rust
  side is clearly emitting events, but the UI still sits on a loading/
  placeholder state forever. Use when: (1) `events.foo.listen(...)` resolves
  BEFORE the emitting command runs (no listener-emit race), (2) Rust-side
  logs show `.emit(&app)` firing repeatedly, (3) the listener callback has a
  multi-field equality predicate like
  `payload.engine === expected && payload.fen === expected && payload.tab === expected`,
  and (4) nothing ever reaches `setState`. Classic symptom: identical-looking
  symptom to the listener-emit race skill, but the listener IS attached and
  the emitter IS running; every payload is being filtered out by an
  over-strict predicate. Fix: filter on ONE field that is guaranteed unique
  per session (e.g. a `genID()` tab id), not a chain of equality checks on
  fields that may be round-tripped through type parsers.
author: Claude Code
version: 1.0.0
date: 2026-04-22
---

# Tauri-specta: Over-Strict Payload Filter Silent-Drop

## Problem
A `tauri-specta` typed-event listener is attached correctly (no race against
the emitter), the Rust side is definitely emitting, and yet the UI never
updates. No errors, no warnings, no console output. The callback runs — you
can confirm with a `console.debug` at the top of the listener — but its
state-setting branch is never taken.

## Trigger Conditions (all must hold)
- Listener-before-emit ordering is already correct (see sibling skill
  `tauri-specta-listener-emit-race`). The listener callback DOES fire.
- The callback gates its `setState` behind a multi-field equality check,
  typically some combination of:
  - `payload.engine === expectedEngine`
  - `payload.fen === expectedFen`
  - `payload.tab === expectedTab`
  - `payload.moves.length === 0`
- One or more of those fields is a string that the Rust side parsed,
  possibly normalised, and then emitted back. Common offenders:
  - FEN strings round-tripped through `shakmaty::Fen::parse().to_string()`
  - Paths normalised by `PathBuf` (trailing slash, case on macOS)
  - Chess move strings, SAN/UCI conversions
  - Any `serde`-(de)serialised string that trims or normalises whitespace
- A `console.debug` inside the callback logs payloads arriving, but no
  state update happens.

## Root Cause
String equality between what JS sent and what Rust emits is fragile. If any
Rust-side code path touches the string — even once — with something like
`let fen: Fen = options.fen.parse()?; /* then later */ self.options.fen =
fen.to_string()` — the round-trip reformats the string. Maybe castling
rights become `KQ` instead of `kqKQ`, maybe a default en-passant `-` gets
added, maybe trailing whitespace is stripped. The new string will NOT
`===` the one JS still holds. Every payload then silently fails the
predicate.

Tauri events are one-shot broadcasts; dropped payloads aren't queued or
retried. The predicate is in user code, so nothing warns you it's always
false.

## Fix
Pick ONE discriminator that is guaranteed unique per emit session, and
filter on that alone. The cleanest option: generate a fresh id on the
frontend before you invoke the command (e.g. `nanoid` or a local
`genID()`), pass it as the command's `tab`/`id` param, and match only
that id in the listener.

```tsx
const sessionId = genID();
setActiveSessionId(sessionId);

useEffect(() => {
  if (!sessionId) return;
  let unlisten: UnlistenFn | null = null;
  let cancelled = false;
  (async () => {
    unlisten = await events.bestMovesPayload.listen(({ payload }) => {
      // One filter: the session id we minted.
      if (payload.tab !== sessionId) return;
      setBestLines(payload.bestLines);
    });
    if (cancelled) { unlisten?.(); return; }
    await commands.getBestMoves(engineName, enginePath, sessionId, /* ... */);
  })();
  return () => { cancelled = true; unlisten?.(); };
}, [sessionId, /* ... */]);
```

Do not check the engine name, the FEN, or any other round-trippable string.
They are not load-bearing for correctness — the session id already proves
"this payload is for this session". And they're each a silent-drop trap
waiting to happen.

## Verification
Add `console.debug` inside the listener at the top (before the filter) AND
in the accepted branch. With the bug present: you see "payload arrived"
logs but no "payload accepted" logs. With the fix: both logs fire for every
payload that matches the session id.

If you need to keep belt-and-braces filtering for defence-in-depth (e.g.
the same listener survives across multiple sessions), log the REJECTED
payloads at `console.debug` level with the exact fields and what was
expected. Invisible drops are the problem; visible drops are fine.

## Example (real-world)
Pawn au Chocolat's live-analysis compact mode filtered on four fields:
`engine name`, `tab id`, `fen string`, `moves.length`. The FEN round-trip
via `shakmaty`'s parser subtly reformatted the string, so the `===` check
failed on every payload. UI sat on "Analysing... 0s" forever. Collapsing
to `payload.tab === compactTabId` (with `compactTabId = genID()`
regenerated per detection) fixed it.

## Notes
- This skill pairs with `tauri-specta-listener-emit-race`. Same symptom
  (stuck placeholder), different cause. Check race first: if `listen()` is
  awaited AFTER the command, fix that. Only then look at the filter.
- A useful triage question: is the listener callback ever firing at all?
  Put a `console.debug("payload", payload)` at the very top. If yes, the
  filter is the issue. If no, it's the race (or the emitter never runs).
- Tauri v2 event names are strings on the wire; the typed `events.foo`
  helpers are just sugar. The payload body goes through `serde_json`
  serialisation/deserialisation, so any `#[serde]` transforms run both
  ways.
- Don't over-correct by removing ALL filtering. If the component may
  receive payloads from other sessions (e.g. a stale tab still listening),
  the session id filter is still load-bearing — just don't chain equality
  checks on other string fields.

## References
- Tauri v2 event API: https://v2.tauri.app/reference/javascript/api/namespaceevent/
- tauri-specta events: https://github.com/oscartbeaumont/tauri-specta
- Related skill: `tauri-specta-listener-emit-race` (listener attached too
  late; same symptom, different cause)
