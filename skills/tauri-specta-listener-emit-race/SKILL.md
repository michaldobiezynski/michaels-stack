---
name: tauri-specta-listener-emit-race
description: |
  Diagnose Tauri frontends that sit on a loading/placeholder state when a
  Rust command immediately starts emitting typed events. Use when: (1) a
  `#[tauri::command]` kicks off work that emits `BestMovesPayload`,
  `Progress`, or similar events, (2) the frontend calls the command AND
  `events.foo.listen(...)` in the same render tick but in separate `useEffect`
  blocks, (3) the UI stays on its initial "..." placeholder even though the
  Rust side is running fine. Classic symptom: engine/worker is clearly doing
  work (CPU active, logs flowing in terminal) but the React view never
  updates. Fix: `await` the `listen()` Promise BEFORE invoking the command
  that triggers the emission.
author: Claude Code
version: 1.0.0
date: 2026-04-22
---

# Tauri-specta: Listener Must Be Attached Before the Emitter Runs

## Problem
A Tauri command starts long-running work that emits typed events via
`tauri-specta`. The frontend wires both the listener and the command in
separate `useEffect` hooks. The UI never updates. No error, no console
warning; the Rust side emits happily, the TS side just never receives.

## Trigger Conditions (all must hold)
- App uses `tauri-specta` to emit typed events from a `#[tauri::command]`
  (e.g. `BestMovesPayload.emit(&app)` inside `get_best_moves`).
- Frontend has **separate** `useEffect`s: one calls
  `events.foo.listen(cb)`, the other calls `commands.doWork(...)`.
- Both effects have overlapping dependency lists, so they run in the
  same tick.
- The command does not return the result synchronously - it only emits
  events while running.
- The UI stays in its "waiting for first event" state indefinitely.

## Root Cause
`events.foo.listen(cb)` returns `Promise<UnlistenFn>`. The actual IPC
registration on the Rust side completes when the Promise resolves, not
when you call `listen(cb)`. If you invoke a command that starts emitting
before that Promise resolves, every event fired during the gap is dropped
silently - **Tauri events are not buffered**. The sync order of the two
`useEffect`s is irrelevant; what matters is that both are async and race.

Reader loops inside the Rust command typically emit the first `info`
line within a few ms of `go`, so the window is tiny but real, and on a
fast machine it reproduces often enough to look like a permanent hang.

## Fix
Collapse the listener and the command call into **one** async block. Await
the listen Promise first, only then invoke the command.

```tsx
useEffect(() => {
  if (!ready) return;
  let cancelled = false;
  let unlisten: UnlistenFn | null = null;

  (async () => {
    unlisten = await events.bestMovesPayload.listen(({ payload }) => {
      // filter + setState
    });
    if (cancelled) {
      unlisten?.();
      return;
    }
    const r = await commands.getBestMoves(/* ... */);
    if (cancelled) return;
    if (r.status === "error") setError(r.error);
  })();

  return () => {
    cancelled = true;
    unlisten?.();
    commands.stopEngine(/* ... */).catch(() => {});
  };
}, [ready, /* ... */]);
```

Import the type: `import type { UnlistenFn } from "@tauri-apps/api/event";`

## Verification
Drop a `console.debug` in the listener callback logging every received
payload, plus one right after the `listen` await and one right after the
command resolves. With the bug present you see the "listener attached"
line but no payloads. With the fix you see payloads arriving within
the first few hundred ms of "listener attached".

## Notes
- Don't paper over it by sleeping before the command call - the race
  window is variable and `sleep(N)` is always either wasteful or wrong.
- Rust-side mitigations (replaying the last state to new subscribers,
  buffering the first few events) are possible but add complexity; the
  frontend ordering fix is the right one.
- The same pattern catches any Rust-emitting command: `analyze_game`,
  progress reporters, download pipelines, engine evaluators.
- If you still need the two effects separated for clarity, attach the
  listener in a **parent** effect that renders `null` until
  `listenerReady` state flips, then the child effect can safely kick
  off the command.
- This race is independent of React StrictMode double-mount behaviour;
  removing StrictMode does not fix it.

## References
- Tauri v2 event API: https://v2.tauri.app/reference/javascript/api/namespaceevent/
- tauri-specta events: https://github.com/oscartbeaumont/tauri-specta
