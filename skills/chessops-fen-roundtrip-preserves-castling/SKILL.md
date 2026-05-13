---
name: chessops-fen-roundtrip-preserves-castling
description: |
  chessops `parseFen(...).unwrap()` → `makeFen(setup)` preserves the
  castling and en-passant fields VERBATIM from the input FEN - it does
  not "canonicalise" them. Use when: (1) vitest assertions comparing a
  chessops-produced FEN string to a hand-written expected constant fail
  with the only difference being `KQkq` vs `-` or an extra en-passant
  square, (2) your test sees "expected 'rnbqkbnr/pppppppp/8/8/4P3/8/
  PPPP1PPP/RNBQKBNR b KQkq - 0 1' to be 'rnbqkbnr/pppppppp/8/8/4P3/8/
  PPPP1PPP/RNBQKBNR b - - 0 1'", (3) you're writing test fixtures for
  code that starts from a detected / imported / reconstructed FEN
  (typical input has castling `-` because the source can't infer
  history), (4) you're surprised the start position no longer has KQkq
  after round-tripping. Fix: match the test fixture to the INPUT FEN
  (the source feeding chessops), not the canonical standard position.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# chessops FEN round-trip preserves castling and en-passant verbatim

## Problem

Test expectations for chessops-produced FENs fail because the test
author assumed `parseFen` + `makeFen` would normalise the castling or
en-passant field to a canonical form (e.g. "a real board with kings
and rooks on their original squares should have castling = KQkq"). It
doesn't. chessops preserves those fields from the input FEN, so
whatever you fed in is what you get back.

## Context / Trigger Conditions

- Assertion fails with the only diff being `KQkq` vs `-`, or an extra
  `e3` / `d6` en-passant square.
- The tested code path runs FENs through a pipeline like:
  ```ts
  const parsed = parseFen(input);
  const setup = parsed.unwrap();
  // ...Chess.fromSetup(setup), pos.play(move), ...
  const out = makeFen(pos.toSetup());
  ```
- The INPUT FEN comes from a source that can't know castling history:
  screenshot detection, OCR, manual FEN editor, crop import, etc., so
  it uses castling `-`.
- You hand-wrote your expected FEN based on "what the start position
  should be" (KQkq from the canonical standard string) rather than
  running the test input through chessops once and capturing its
  output.

## Root cause

chessops implements strict FEN round-tripping for these fields:
`castling` and `epSquare` on `Setup` are parsed from the input and
emitted back unchanged (aside from the en-passant "only when capturable"
optimisation in some variants). There is no "infer castling rights
from king/rook positions" step. A position with the king on e1 and
rooks on a1/h1 but castling = `-` is a legal chessops state meaning
"these pieces haven't moved away but castling has been lost anyway";
it's distinct from KQkq.

This differs from some Python / Stockfish helpers that auto-derive
castling rights from piece placement.

## Solution

Two reliable options:

1. **Match fixtures to the actual input.** If the code under test
   starts from a `-` castling FEN (detection pipeline, import flow),
   write your expected constants with `-` castling too:
   ```ts
   // detection pipeline produces castling = "-", so everything
   // downstream preserves it
   const START_FEN =
     "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1";
   const AFTER_E4_FEN =
     "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b - - 0 1";
   ```

2. **Derive fixtures by running chessops once.** Capture what chessops
   actually emits and use that literal as the expected constant. A
   throwaway script or a console.log in a failing test is enough.

## Verification

After aligning the castling/en-passant fields, the assertion's only
remaining diff (if any) is piece placement or turn, which are the
fields you actually meant to test. If the test had been looking at
those and missing them before because the trailing fields shouted
first, the real regression now surfaces.

## Example

Real session incident. The test for a manual-move history mini-board
compared `compactFen` (produced by chessops) against a hand-written
expected:

```ts
// Hand-written expected - WRONG for this pipeline:
const AFTER_E4_FEN =
  "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1";

// Actual chessops output (detection pipeline seeds castling="-"):
//   "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b - - 0 1"
```

The test file for the pure reducer (which seeded its inputs with KQkq
directly) passed because KQkq went in and KQkq came out. The
integration test that went through the detection pipeline failed with
`-` because that's what detection emits. Fix was a one-line constant
update per file — after that, the real logic under test was the only
thing being checked.

## Notes

- Pure reducer tests that seed their own START_FEN can use KQkq safely
  (it round-trips); integration tests whose input is produced by
  another part of the system must use whatever that part emits.
- Same logic applies to `epSquare`: if the input has `e3`, output
  keeps `e3` even when no capture is possible; if input has `-`,
  output stays `-` even after a double pawn push in "strict" variants.
- Half-move / full-move counters are also preserved and incremented
  by `pos.play`, so `"... 0 1"` → `"... 0 2"` after a black move, etc.
- If you WANT canonical castling derivation, do it yourself with
  `getCastlingSquare` or by constructing a new `Setup` — chessops
  doesn't do it implicitly.

## References

- [chessops on npm](https://www.npmjs.com/package/chessops)
- [FEN - Wikipedia (castling and en-passant fields)](https://en.wikipedia.org/wiki/Forsyth%E2%80%93Edwards_Notation)
