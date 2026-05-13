---
name: tauri-cross-ipc-session-id-rotation-leaks-process-pool
description: |
  Diagnose severe memory leaks (GB to 100+ GB) in Tauri / Electron / Pyodide /
  any IPC-bridged app where the JS side regenerates a session / correlation ID
  per detected event (per captured frame, per detected position change, per
  inbound message), uses that ID as part of the key on backend commands, and
  the backend keeps a long-lived map of expensive resources (spawned
  Stockfish / Python worker / ONNX session / GPU context / persistent DB
  connection) keyed by (sessionId, resourcePath). The frontend cleanup
  calls a "stop" command that halts the work but does NOT remove the entry
  from the backend map. The backend's "new session" path unconditionally
  spawns a fresh resource when it sees an unknown key. Net effect: every
  event leaks one fully-allocated resource.

  Use when: (1) a Tauri or Electron app's memory climbs gradually over
  hours of normal use until it crashes or pages heavily, (2) the climb
  correlates with a live capture, auto-refresh, polling, or streaming
  feature firing detection / analysis events at a regular cadence,
  (3) Activity Monitor shows many child processes (Stockfish, Python,
  etc.) growing over time, (4) the backend has both a "stop" and a
  "kill" command on the same resource (the asymmetry is the smell),
  (5) the frontend useEffect / watcher cleanup calls the "stop"
  variant, (6) the leak is invisible if you only audit one side:
  backend sees its map growing but cannot know JS is rotating keys;
  JS sees its session ID rotating but cannot know the backend is
  holding the old key.

  Specifically catches "memory climbed to 100 GB during live capture"
  in Tauri chess / screen-share / OCR / live transcription apps.
  Diagnosis requires following the data flow across the IPC boundary
  in BOTH directions; single-side audits will miss it.
author: Claude Code
version: 1.0.0
date: 2026-05-11
---

# Cross-IPC session-id rotation leaks a backend process pool

## Problem

A live / auto-refresh / polling feature in a Tauri (or Electron, or any
IPC-bridged) app leaks one fully-allocated backend resource per detected
event. The resource is typically expensive: a spawned child process
holding a multi-hundred-MB Hash table (Stockfish, Leela, Stockfish-derived
engines), a loaded ONNX / TFLite / Core ML model, a GPU context, a
persistent DB pool, or a long-lived HTTP client. Memory climbs gradually
while the feature is active and never drops back to baseline until app
restart. Over hours of use it can reach tens to hundreds of GB.

Neither side's code is wrong in isolation. Each side's unit tests pass.
The bug lives in the composition across the IPC boundary.

## Context / trigger conditions

Three ingredients must coexist:

1. **Frontend rotates a session / correlation ID per detected event.**
   Look for `setSessionId(genID())`, `setTabId(uuid())`, or any
   `useState`/atom that gets a fresh random ID inside a detection
   callback that fires on a timer, a websocket message, or a capture
   tick.

2. **That ID is part of the key on backend commands** that mutate or
   read a long-lived resource pool. The pool is typically
   `DashMap<(SessionId, ResourcePath), Arc<Mutex<Resource>>>` or
   equivalent. Example signature:
   ```rust
   #[tauri::command]
   async fn get_best_moves(
       tab: String,    // <-- the rotated session id lands here
       engine: String,
       state: tauri::State<'_, AppState>,
   ) -> Result<…> {
       let key = (tab, engine);
       if state.engine_processes.contains_key(&key) {
           // reuse path
       } else {
           // spawn-fresh path — always allocates a new resource
       }
   }
   ```

3. **Cleanup calls "stop" rather than "kill".** The backend has two
   commands on the same resource: one that signals it to halt current
   work (UCI `stop`, `SIGINT`, `cancel()`) and another that frees it
   (process kill + `map.remove(&key)`). The frontend's `useEffect`
   cleanup chooses "stop", because "stop" reads as gentler / more
   recoverable. The map entry stays, the resource keeps its full
   memory allocation, the new session ID has no way to find or reuse
   the old resource.

If all three hold, every detected event during the feature's lifetime
leaks one resource. The leak rate equals the detection event rate.

## Why it hides from single-side audits

- **Backend audit alone**: the resource map grows, but every entry
  has a coherent `(sessionId, resourcePath)` key. Nothing looks wrong;
  there's no obvious "old entry, never reused" because the backend
  has no concept of "old session ID". From the backend's view, every
  request is a new session that hasn't been cleaned up *yet*.

- **Frontend audit alone**: session IDs rotate correctly, listeners
  are added and removed, cleanup functions fire on every useEffect
  re-run. The `stop` command is called. The frontend has no view
  into the backend's map.

- **Both sides' unit tests pass**: `kill_command` correctly frees
  resources when called; `stop_command` correctly halts work without
  freeing; the frontend's cleanup fires deterministically. The bug
  is the *choice of which command to call on rotation*, which is
  emergent from the composition.

The diagnostic technique is to follow ONE event from the frontend
callback all the way through to the resource allocation site in the
backend, and then ask: "What is the cleanup path for the OLD session's
resource?" If the answer is "there isn't one; we just don't reference
it any more from JS", you've found the leak.

## Solution

Three fixes, ordered by leverage:

### Fix 1 (best): stop rotating the session ID per event

Keep one session ID for the entire feature activation. When the
detected event changes the inputs (FEN, frame, query), pass the
new inputs to the SAME session via the backend's existing "options
change" path. Most backend pools already have one (Stockfish:
`setoption` + `position`; ONNX: just call inference again; DB:
new prepared statement on the existing connection). This is the
right fix in 90% of cases.

```typescript
// Before (leaking)
useEffect(() => {
  // detected position change
  setSessionId(genID());  // <-- rotates per event
  void commands.getBestMoves(engineName, enginePath, sessionId, …);
}, [detectedFen]);

// After (fixed)
const sessionIdRef = useRef(genID());  // one ID for the feature lifetime
useEffect(() => {
  void commands.getBestMoves(engineName, enginePath, sessionIdRef.current, {
    fen: detectedFen, …  // backend's reuse path handles the position change
  });
}, [detectedFen]);
```

### Fix 2 (if rotation is unavoidable): call `kill` on the old session

If you genuinely need a fresh resource per event (e.g., each event
spawns a worker that runs to completion and dies), switch the
cleanup to the `kill` command that removes from the map:

```typescript
return () => {
  // Was: commands.stopEngine(engineKey, oldSessionId);
  void commands.killEngines(oldSessionId);  // <-- the variant that removes from the map
};
```

This works, but every event still pays the cost of cold-spawning
the resource. Worth it only if the resource is genuinely event-scoped.

### Fix 3 (API-level): make `stop` also remove from the map

If your team semantics are "stop means done", change the backend
`stop` command to also call `map.remove(&key)`. This is a breaking
API change for any caller that relied on `stop` keeping the resource
alive for resumption (e.g., a "pause / resume analysis" feature),
so audit callers first. Not recommended unless you control all
callers.

## Verification

After applying the fix, verify with three checks (in increasing
order of effort):

1. **Spawn-site logging**: add `info!("[backend] spawning new resource for {:?}", key)`
   in the backend's "fresh allocation" branch. Run the feature for
   five minutes at the normal cadence. Count the spawn lines. Should
   be O(1) for fix #1, O(events) for the original bug.

2. **Map-size periodic dump**: log `state.engine_processes.len()`
   from a tokio task every 30 seconds while the feature runs. Should
   stay constant (close to the number of distinct
   `(session, resource)` pairs the user actually intends to have).

3. **OS process count**: on macOS, `ps -ax | grep stockfish | wc -l`
   in a loop. Should not grow over time. On Linux, same with
   `pgrep` or `/proc`.

If all three are flat-lined under sustained feature use, the leak
is closed.

## Worked example: pawn-au-chocolat, 2026-05

The Live miniboard auto-refresh loop in pawn-au-chocolat ran
detection every 4 seconds. On every detected board change:

1. `silentRetake` (LiveAnalysisView.tsx ~ line 691) called
   `setCompactTabId(genID())` — fresh session ID per detected
   position.
2. The engine effect (LiveAnalysisView.tsx ~ line 374) depended
   on `compactTabId`. Its cleanup fired on every rotation:
   `commands.stopEngine(engineKey, oldSessionId)`. This sent
   UCI `stop` to Stockfish; the DashMap entry stayed; the process
   stayed alive and idle, still holding its Hash table.
3. The new effect immediately called
   `commands.getBestMoves(engineName, engineKey, newSessionId, …)`.
   In `chess.rs:547`, `state.engine_processes.contains_key(&key)`
   returned false for the new sessionId, so the code fell through
   to `EngineProcess::new(path)` at line 579, spawning a brand new
   Stockfish with its full Hash allocation.

Net effect: every detected board change left one fully-allocated
Stockfish behind. At one board change per 30s over three hours of
broadcast-following, that is 360 leaked Stockfishes. At a 256 MB
Hash each, ~92 GB. The user reported peaks above 100 GB; one
configuration tweak (Hash = 512 MB, or shorter cadence) accounts
for the rest.

Fix #1 applied: keep `compactTabId` stable for the entire miniboard
activation. The backend's `set_options` reuse path
(`chess.rs:547-577`) already handles position changes cleanly on
the existing engine. One Stockfish, one Hash, regardless of how
many positions get streamed through it.

## Notes

- **"Stop" vs "kill" is the load-bearing semantic.** In every IPC
  API I have audited, "stop" means "halt the current work, keep
  the resource alive for resumption" and "kill" means "release the
  resource". Confusing them is the most common form of this bug.
  When designing an IPC API around an expensive resource pool,
  pick one verb and stick to it; if you must offer both, name them
  unambiguously (e.g., `pause` and `release` rather than `stop` and
  `kill`).

- **The asymmetry is a smell.** When you see a backend pair like
  `stop_engine` + `kill_engine`, audit every frontend cleanup that
  calls either. The wrong one is almost always being called
  somewhere.

- **Atom families compound this on the JS side.** Jotai's
  `atomFamily`, Recoil's family atoms, and similar APIs cache one
  atom per key. If the JS key rotates per event, the atomFamily
  retains every old atom too. JS-side leak is usually MB-scale
  (not GB), but it can be enough to be confusing if you measure
  total app RSS rather than child-process RSS.

- **The bug pattern is framework-agnostic.** It applies anywhere
  you have:
  - A frontend → backend IPC (Tauri, Electron, Pyodide, gRPC web,
    Wails, …)
  - A backend pool of expensive resources keyed by something the
    frontend controls
  - A frontend watcher / effect that rotates that key
  - A backend command that halts work without freeing

  I have seen the same shape in a Python + Electron transcription
  app (worker subprocesses), a Tauri + Rust OCR app (ONNX sessions),
  and a Go + Wails screen-share app (capture handles). It is not
  Tauri-specific.

- **Diagnosis order**: when memory leaks during a live capture /
  auto-refresh feature, the first hypothesis people reach for is
  "the screen-capture buffers are leaking" (because the buffers
  are visible and large). The right first hypothesis is "what
  expensive resource gets allocated per detected event?". Capture
  buffers in well-behaved frameworks are typically per-call locals
  that drop at function return; their churn does not retain.

- **Don't fix this with a `lru` cache.** Tempting: "evict old map
  entries with LRU". But the resource needs explicit shutdown
  (UCI `quit`, model dispose, connection close), not GC. LRU
  papers over the symptom by capping the leak rate, but every
  evicted entry is still a leaked OS resource.

## Related

- `tauri-v2-plugin-pitfalls` — different bug class (HTTP/FS silent
  failures), same general theme of "trust the API boundary at your
  peril".
- `zustand-react-state-race` — also a cross-state-system bug where
  each piece looks fine alone.
- `tauri-specta-listener-emit-race` — Tauri event lifecycle on the
  JS side; often the next thing to audit if you fix the resource
  leak and still see UI freezes.

## References

- Diagnosed in: pawn-au-chocolat (Tauri 2 chess analysis app),
  live miniboard auto-refresh path, 2026-05-11.
- The pattern is a cross-cutting concern in IPC architectures, not
  framework-specific. No single canonical reference; surfaces in
  retrospectives on every framework's GitHub issues over time.
