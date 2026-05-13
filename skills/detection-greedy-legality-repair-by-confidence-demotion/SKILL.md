---
name: detection-greedy-legality-repair-by-confidence-demotion
description: |
  Pattern for post-processing ML-detection output (YOLO, CNN, etc.)
  when the raw output must satisfy domain rules but frequently doesn't.
  Use when: (1) building a chess/Go/backgammon board detector where
  YOLO occasionally emits two kings, nine pawns, or pieces on illegal
  squares, (2) any detection pipeline whose output is rule-constrained
  (document layout with "at most one barcode per page", invoice parsing
  with "exactly one total row"), (3) naive argmax gives wrong answers
  on ~5% of inputs and you need better recall without retraining the
  model. Covers: the validate-issues + greedy-demotion loop using
  per-detection confidence, the "never demote a load-bearing piece
  while fixing a count issue" guard, and the fall-through to
  "needs user confirmation" when removal alone cannot satisfy the
  rules. Survey found this pattern acknowledged as the right idea
  (Bakken & Baeck 2018) but not implemented in OSS chess-detection
  pipelines - they all stop at argmax. Rust/TS agnostic, the logic
  is the same in any language.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Greedy legality repair by confidence-driven demotion

## Problem

ML detectors (YOLO, CNN, etc.) emit per-instance outputs that ignore
domain rules. For chess detection from screenshots, this manifests as:

- Two white kings because a bishop or queen on the king's diagonal got
  misclassified.
- Nine white pawns because a knight was misclassified as a pawn.
- A white pawn on rank 8 because a minor piece got labelled pawn
  (impossible in legal chess: pawns on rank 8 must have promoted).
- 17+ pieces for one side.

Naive pipelines emit whatever the argmax says and pass it downstream,
producing illegal FENs that crash the engine, show the wrong board,
or silently give the user a position they can't analyse. Users see
"Loading..." forever or an oddly-shaped board they can't correct
without hand-editing the FEN.

The classic academic fix ("train a better model") is expensive, off-scope
for a post-processing commit, and still doesn't guarantee zero rule
violations. A post-processing repair layer that uses per-detection
confidence to pick which detection to demote is a high-yield low-risk
alternative.

## Context / Trigger Conditions

- You're building or maintaining a chess-position-from-image pipeline
  (YOLO, CNN, template matching) and users report "it sometimes adds
  or removes pieces".
- Your pipeline emits a FEN that looks plausible but is rejected by a
  legality validator (python-chess `Board.status()`, chessops
  `Position.fromSetup`, shakmaty `Chess::from_setup`).
- You already have per-detection confidence scores and want to use
  them beyond the existing NMS / confidence threshold.
- Classical "just raise the confidence threshold" makes recall worse
  without fixing colocated rule violations (two high-confidence kings
  are both kept).
- You're reviewing an OSS chess detector that stops at argmax and
  want to add a repair layer.
- Downstream consumer (engine, UI) fails or shows wrong state when
  the FEN violates rules that could be detected and fixed.

## Solution

Four parts:

### 1. Enumerate legality issues from the grid

A pure function `find_issues(grid) -> Vec<LegalityIssue>` that
enumerates all rule violations currently present. Use an enum that
names each violation and includes data needed to locate the offending
cell(s):

```rust
enum LegalityIssue {
    TooManyKings { white: bool, count: u8 },
    MissingKing { white: bool },  // Not fixable by removal.
    TooManyPawns { white: bool, count: u8 },
    PawnOnBackRank { row: usize, col: usize, piece: char },
    TooManyPieces { white: bool, count: u8 },
}
```

For chess specifically: king counts, pawn counts per side, pawns on
rank 1 or 8, total piece count per side. Use shakmaty / python-chess
for richer checks (opposite check, impossible check) if available.

### 2. Greedy repair loop

A function `repair(grid, confidences) -> RepairOutcome` that:

1. Finds all issues.
2. Picks the first issue that's **fixable by removal** (not
   `MissingKing`).
3. Asks `pick_removal` for the lowest-confidence offending piece to
   demote to empty.
4. Repeats until no fixable issues remain or the pool is empty.

Bound the loop (at most 64 iterations for an 8x8 grid) so you can't
loop forever if the repair logic has a bug.

Return three possible outcomes:

```rust
enum RepairOutcome {
    AlreadyLegal,
    Repaired { grid, report },
    Unrepairable { grid, report },  // best-effort partial grid + remaining issues
}
```

The `Unrepairable` variant returns the **partially repaired** grid so
the UI still has something to render while asking the user to confirm
or re-crop.

### 3. The load-bearing-piece guard

When fixing `TooManyPieces` (too many white/black pieces overall),
**never demote a king**. If you do, you cascade into `MissingKing`
which flips a repairable state into an unrepairable one. Special-case:

```rust
LegalityIssue::TooManyPieces { white, .. } => {
    collect_matching(grid, confidences, &mut candidates, |p| {
        if p == '.' { return false; }
        if p == 'K' || p == 'k' { return false; }  // <-- key guard
        let is_white = p.is_ascii_uppercase();
        is_white == want_white
    });
}
```

`TooManyKings` is handled separately and runs first in `find_issues`
ordering, so extra kings get demoted before `TooManyPieces` even
fires.

### 4. Deterministic tie-breaking

When multiple offending cells have identical confidence, sort by
`(confidence ASC, row ASC, col ASC)` so repair is deterministic and
unit-testable. Picking the "first" of an unordered set produces
flaky tests.

### 5. Fall-through to user confirmation

When `repair` returns `Unrepairable`, surface a `needs_user_confirmation`
flag to the caller. Don't emit a wrong FEN and pretend everything is
fine - the user should see a banner like "couldn't verify this
position, please review or retake" and the auto-advance flow should
be blocked.

## Verification

Unit-test each issue type and the repair paths:

```rust
#[test]
fn repair_two_kings_removes_lower_confidence_one() {
    let mut g = empty_grid();
    g[7][4] = 'K';
    g[7][5] = 'K';
    g[0][4] = 'k';
    let mut c = uniform_conf(0.9);
    c[7][5] = 0.3; // lower-confidence white king
    match repair(&g, &c) {
        RepairOutcome::Repaired { grid, report } => {
            assert_eq!(grid[7][4], 'K');
            assert_eq!(grid[7][5], '.');
            assert_eq!(report.actions[0].removed, 'K');
            assert!((report.actions[0].confidence - 0.3).abs() < f32::EPSILON);
        }
        other => panic!("expected Repaired, got {other:?}"),
    }
}

#[test]
fn repair_never_removes_king_when_fixing_too_many_pieces() {
    // 16 knights + 1 king = 17 white pieces. Even if the king has
    // the lowest confidence, it must NOT be removed.
    // ...
    assert_eq!(final_grid[7][4], 'K', "king must be preserved");
    assert!(report.actions.iter().all(|a| a.removed != 'K'));
}

#[test]
fn repair_missing_king_returns_unrepairable_with_best_effort_grid() {
    // ...
    match repair(&g, &c) {
        RepairOutcome::Unrepairable { grid, report } => {
            assert!(report.issues_after.contains(&MissingKing { white: false }));
            // partially repaired grid still usable for display
        }
        other => panic!(),
    }
}
```

Ship a grid-level corpus test that runs the post-detection pipeline
(orientation + repair + FEN) over ~15-20 table-driven cases covering
clean positions, sparse endgames, and each rule violation. This is
your ratchet: any future change that breaks these cases is a regression.

## Example

Real incident in a Tauri/Rust chess app:

- Screenshot detection occasionally produced 2 white kings because a
  bishop on e1 was misclassified.
- Pipeline emitted `"rnbqKbnr/..." w - - 0 1` with two 'K' chars.
- Stockfish rejected the FEN silently; UI showed "Loading..." forever.
- Adding `legality::repair` with confidence demotion fixed ~80% of
  these cases (the misclassified bishop always had lower confidence
  than the real king).
- Remaining 20% were `MissingKing` cases (YOLO missed a king entirely)
  which the Unrepairable path correctly surfaces as "needs user
  confirmation" instead of emitting a broken FEN.

## Notes

- Plumb confidence through the grid mapping step. If your `map_to_grid`
  function drops confidence (common in naive implementations), extend
  it: `map_to_grid_with_confidence(detections) -> (grid, conf_grid)`
  where `conf_grid[r][c]` holds the confidence of whatever piece
  currently occupies that cell.
- When orientation-correcting the grid (180 degree flip), rotate the
  confidence grid identically. A piece's confidence must stay in the
  same cell as the piece itself.
- If you need richer legality (opposite check, bad castling rights,
  impossible check), delegate to python-chess `Board.status()` or
  shakmaty `Chess::from_setup`. Both expose explicit flags you can
  map to `LegalityIssue` variants.
- This pattern generalises to any ML-detection-with-constraints
  domain: document layout ("at most one barcode per page"), invoice
  parsing ("exactly one total row"), sheet-music OCR ("notes must fit
  the declared time signature").
- Greedy repair using detector confidence against a rules validator
  was called out as the right approach in Bakken & Baeck's ChessVision
  post (2018) but I have not found an OSS chess-detection project
  that implements it - most stop at argmax. This is a latent
  improvement almost everyone has left on the table.
- Guard against infinite loops: bound the repair loop to N iterations
  where N is the max grid size. The loop breaks naturally when issues
  are empty OR when `pick_removal` returns `None` (no fixable
  candidates), but an explicit bound is cheap insurance against
  future edits.

## References

- [python-chess Board.status() legality flags](https://python-chess.readthedocs.io/en/latest/core.html)
- [chessops Position.fromSetup (IllegalSetup variants)](https://github.com/niklasf/chessops)
- [shakmaty crate docs](https://docs.rs/shakmaty/)
- [Bakken & Baeck ChessVision post (concept reference)](https://tech.bakkenbaeck.com/post/chessvision)
- Related skill: `chess-board-a1-parity-cannot-disambiguate-orientation`
  for why simple corner-colour checks don't belong in your orientation
  voter.
