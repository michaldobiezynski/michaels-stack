---
name: lichess-puzzle-format
description: |
  Lichess-compatible chess puzzle format and analysis-to-puzzle indexing.
  Use when: (1) creating puzzles from engine analysis of chess games,
  (2) converting game analysis into playable puzzle positions,
  (3) debugging puzzles that show wrong positions or moves.
  Covers the exact FEN/move mapping between analyzeGame output and
  puzzle construction in pawn-au-chocolat.
author: Claude Code
version: 1.0.0
date: 2026-04-01
---

# Lichess-Compatible Chess Puzzle Format

## Problem
When extracting puzzles from engine-analysed chess games, the mapping between
analysis array indices, game move indices, and puzzle positions is non-obvious.
Getting it wrong produces puzzles where the first move is the blunder (wrong)
instead of the opponent's setup move, or the FEN shows the wrong position.

## Context / Trigger Conditions
- Building puzzle extraction from `analyzeGame()` results in pawn-au-chocolat
- Analysis array has one entry per ply (half-move), with `analysis[0]` being
  the evaluation of the starting position
- `gameMoves[]` is 0-indexed UCI moves (one per ply)
- Puzzles must be in Lichess-compatible format for the puzzle solving UI

## Solution

### Analysis Array Mapping
- `analysis[0]` = engine eval of starting position (before any moves)
- `analysis[i]` = engine eval after `gameMoves[i-1]` was played
- `analysis.length = gameMoves.length + 1` (includes start position)

### Colour Determination
```typescript
const colour = i % 2 === 1 ? "white" : "black";
// i=1 (after White's 1st move): colour = "white" (evaluating White's move)
// i=2 (after Black's 1st move): colour = "black" (evaluating Black's move)
```

### Puzzle Construction (Lichess Format)
When a blunder is detected at analysis index `i`:

```typescript
// CORRECT: Lichess format
const setupMoveIndex = i - 2;
const setupMove = gameMoves[setupMoveIndex];   // Opponent's move (auto-played)
const puzzleFen = positions[setupMoveIndex];   // Position BEFORE opponent's move
const correctMoves = analysis[i - 1].best[0].uciMoves; // Best response
const puzzleMoves = [setupMove, ...correctMoves];

// WRONG: Common mistake
const puzzleFen = fens[i - 1];     // One move too late
const solutionMoves = [gameMoves[i], ...bestMoves]; // gameMoves[i] is the BLUNDER!
```

### The Format Explained
1. **FEN** = position where the opponent is about to move (2 plies before the blunder)
2. **moves[0]** = opponent's last move before the puzzle position (auto-played by UI)
3. **moves[1+]** = the correct response the user must find (from engine's best line)
4. Requires `i >= 2` (cannot create puzzles from the first move)

## Verification
- The puzzle FEN should show the position BEFORE the opponent's setup move
- After auto-playing moves[0], it should be the blundering player's turn
- moves[1] should be the engine's recommended move, NOT the blunder

## Example
Game: 1.e4 e5 2.Nf3 Nc6 3.Bb5?? (blunder by White at ply 4)

```
gameMoves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
analysis[5] detects the blunder (i=5, colour="white")

setupMoveIndex = 5 - 2 = 3
setupMove = gameMoves[3] = "b8c6"  (Black's move, auto-played)
puzzleFen = positions[3]           (position before Nc6)
correctMoves = analysis[4].best    (engine's best from position after Nc6)
puzzleMoves = ["b8c6", "d2d4", ...] (setup + correct response)
```

## Notes
- The `positions[]` and `fens[]` arrays use index 0 for the starting position,
  so `positions[k]` = position after k moves
- CP loss is calculated as `getCPLoss(analysis[i-1].score, analysis[i].score, colour)`
- The perspective filter uses `colour` to determine whose move is being evaluated
- `prevAnalysis.best[0].uciMoves` gives the engine's best continuation (the correct answer)
- Always guard with `if (setupMoveIndex < 0) continue` to skip early-game positions
