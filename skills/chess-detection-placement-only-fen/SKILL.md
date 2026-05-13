---
name: chess-detection-placement-only-fen
description: |
  Fix for Stockfish "Loading..." hang forever after running chess-board image
  detection in pawn-au-chocolat. Use when: (1) the analysis panel shows
  `<Code>Loading...</Code>` indefinitely after clicking Analyse from a
  detected position, (2) no engine UCI output appears in dev logs despite
  detection succeeding, (3) the Rust `DetectionResult.fen` field is being
  passed straight to `defaultTree()` / engine commands. Root cause: Rust's
  `fen_generator::grid_to_fen` returns only the piece-placement portion of
  a FEN (8 ranks joined by `/`), not a full FEN - the missing turn/castling
  /en-passant/halfmove/fullmove fields cause shakmaty's `Fen::parse` to
  reject the string, the IPC promise rejects silently (no `.catch()` in
  EvalListener), and the UI hangs.
author: Claude Code
version: 1.0.0
date: 2026-04-21
---

# Placement-only FEN from chess image detection silently hangs engine analysis

## Problem

The chess-piece image-detection pipeline in pawn-au-chocolat exposes its
result through the Rust type `DetectionResult { fen: String, ... }`. The
field is named `fen` and typed as `String`, which strongly implies it holds
a full FEN like `rnbqkbnr/... w KQkq - 0 1`. It does not. The actual value
returned from `fen_generator::grid_to_fen` is only the piece-placement
portion - eight ranks joined by `/`, with nothing after.

Passing that partial string as if it were a full FEN to any code that
eventually reaches the Stockfish UCI command layer produces a silent UI
hang instead of a visible error, because two separate failure modes
compound:

1. **Rust-side rejection**: `chess.rs` parses the FEN via shakmaty's
   `Fen::parse`, which rejects a placement-only string. The IPC command
   `get_best_moves` returns `Err(...)`.
2. **Frontend swallows the error**: `EvalListener.tsx` calls
   `getBestMoves(...).then(...)` with no `.catch()`. The rejection becomes
   an unhandled promise rejection that never reaches the UI.
3. **UI stays at "Loading..." forever**: `BestMoves.tsx` renders
   `<Code>Loading...</Code>` whenever `enabled && !isGameOver && !error
   && !engineVariations`. Since `error` is never set (the catch is
   missing), the condition stays true indefinitely.

Even if the Rust side accepted the partial FEN and canonicalised it, there
is a second latent failure: `EvalListener` filters incoming
`BestMovesPayload` events by exact `payload.fen === searchingFen` match.
If the engine echoes a canonical full-form FEN and the frontend was
searching with the partial one, every payload is dropped.

## Context / Trigger Conditions

- Working in pawn-au-chocolat (Tauri 2 + React + Rust)
- User reports Stockfish "stuck at Loading..." after:
  - Clicking Analyse in the Live Analysis view (`/live`)
  - Any other flow that surfaces `DetectionResult.fen` and hands it to
    `defaultTree(fen)` without normalisation
- `npm run dev` logs show detection producing a FEN like
  `2r1k2r/1p3p1p/p3p1p1/2bpP1P1/5P2/P2RB3/1P3R1P/6K1` followed by no
  engine spawn output (no `[chess]` info lines from `chess.rs`)
- The UI renders `<Code fz="xs">Loading...</Code>` (BestMoves.tsx:~350)
  and never advances to engine variations

## Solution

Normalise the FEN at the detection-result boundary before it crosses into
tree / engine code. Append the default non-placement fields and
round-trip through chessops for canonical form.

**Fix location**: wherever `DetectionResult.fen` is consumed. In the Live
Analysis flow, that's the `runDetection` callback in
`src/components/liveAnalysis/LiveAnalysisView.tsx`:

```tsx
import { makeFen, parseFen } from "chessops/fen";

// inside runDetection(...)
if (res.status === "ok") {
  setResult(res.data);
  // detectScreenshotPosition returns only the piece-placement portion
  // of the FEN (grid_to_fen in fen_generator.rs). Append defaults for
  // the remaining fields so BoardSetupStep validation passes and
  // Stockfish receives a parseable `position fen ...` line.
  const placement = res.data.fen.trim();
  const full = `${placement} w - - 0 1`;
  const parsed = parseFen(full);
  setCurrentFen(parsed.isOk ? makeFen(parsed.value) : full);
}
```

Equivalent prior art exists at `src/components/tabs/ImportModal.tsx`
(around lines 236-247), where the import-from-image flow already handles
this correctly by appending `${sideToMove} - - 0 1` and passing through
`parseFen` / `makeFen`. Any new consumer of the detection result should
mirror that pattern.

### Secondary fix (recommended)

Add a `.catch()` to `EvalListener.tsx:~205` so future IPC rejections
surface as UI errors instead of hanging at "Loading...":

```tsx
getBestMoves(...)
  .then(...)
  .catch((e) => setError(e instanceof Error ? e.message : String(e)));
```

This is a latent bug affecting every engine flow, not just Live Analysis.

### Ideal fix (not done yet)

Change the Rust contract so `DetectionResult` either:

- Returns a full FEN (have `grid_to_fen` or a wrapper append
  `" w - - 0 1"` before returning), or
- Renames the field to `placement: String` so the type clearly signals
  the partial contract.

Either option eliminates the ambiguity at the type boundary and makes
the defect impossible to reintroduce. Until then, every frontend
consumer must remember to normalise.

## Verification

1. Trigger the detection flow (Live Analysis: pick window → crop →
   detect).
2. Click "Analyse" to create the analysis tab.
3. In `npm run dev` output, confirm Stockfish spawn logs appear: binary
   path, `uci` / `uciok` handshake, followed by `info depth ...` lines.
4. In the UI, confirm `BestMoves` leaves the "Loading..." placeholder
   within a couple of seconds and starts showing evaluations.
5. If "Loading..." persists, check the terminal for an IPC error mentioning
   FEN parse failure - that confirms the partial-FEN case is being hit
   and the normalisation is missing or bypassed.

## Example

Before fix:

```tsx
// LiveAnalysisView.tsx - BUG
if (res.status === "ok") {
  setResult(res.data);
  setCurrentFen(res.data.fen);  // placement-only, breaks engine
}
```

After fix:

```tsx
// LiveAnalysisView.tsx - FIXED
if (res.status === "ok") {
  setResult(res.data);
  const placement = res.data.fen.trim();
  const full = `${placement} w - - 0 1`;
  const parsed = parseFen(full);
  setCurrentFen(parsed.isOk ? makeFen(parsed.value) : full);
}
```

## Notes

- The `w - - 0 1` suffix is a safe default for an arbitrary detected
  position: white-to-move, no castling rights, no en-passant target,
  halfmove 0, fullmove 1. `BoardSetupStep` lets the user correct the
  side-to-move and castling rights before starting analysis, so
  defaulting is acceptable here.
- `parseFen` + `makeFen` round-trip is important: it canonicalises the
  string so frontend `searchingFen` and Rust-echoed `payload.fen` match
  byte-for-byte in `EvalListener`'s event filter.
- `defaultTree(fen)` in `src/utils/treeReducer.ts` does NOT normalise its
  argument - it stores whatever you pass. Don't rely on it as a safety
  net.
- The silent-failure pattern (unhandled IPC promise rejection + UI
  hang) is the tell. Any time Stockfish shows "Loading..." forever with
  no terminal output, check whether the FEN being searched is a valid
  full FEN.
- Related skill: `tauri-specta-diesel-patterns` covers the binding
  generation - if you change the Rust `DetectionResult` type, regenerate
  the TS bindings via the usual specta flow.

## References

- Upstream `fen_generator::grid_to_fen`:
  `src-tauri/src/image_detection/fen_generator.rs`
- Correct consumer pattern:
  `src/components/tabs/ImportModal.tsx` ~236-247
- Silent-catch location:
  `src/components/boards/EvalListener.tsx` ~205
- Symptom render:
  `src/components/panels/analysis/BestMoves.tsx` ~350
- chessops FEN docs: https://github.com/niklasf/chessops
