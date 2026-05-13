---
name: detection-canonical-position-recovery
description: |
  Pattern for ML-detection repair when score-based passes (top-2 disambiguation,
  sub-threshold rescue) cannot help. Use when: (1) you've layered the standard
  detection-repair stack (top-1 → top-2 disambig → sub-threshold rescue) and
  there's a residual class of failures where the misclassified item sits at a
  canonical type-X location but is labelled type-Y, (2) the rescue pass can't
  help because the cell is occupied (not empty) by a wrong-class detection,
  (3) the top-2 disambig can't help because the model's runner-up class isn't
  the correct one, (4) you have domain knowledge that says "type X is normally
  at canonical positions {P1, P2, ...}". Solution: a final-layer
  domain-grounded rewrite that flips wrong-class labels at canonical positions
  when the side is otherwise missing type X.
author: Claude Code
version: 1.0.0
date: 2026-04-26
---

# Canonical-position recovery as final-layer detection repair

## Problem

You have a layered ML-detection repair pipeline:

1. **Top-1**: take the model's argmax class.
2. **Top-2 disambiguation** (e.g. `detection-top2-disambiguation-gated-by-pattern`):
   when the side has a suspect deficit (0 rooks + ≥ 3 bishops, etc.) AND the
   model's runner-up class for the misclassified detection IS the correct one,
   flip the label.
3. **Sub-threshold rescue** (e.g. `detection-sub-threshold-rescue-by-deficit`):
   when the side is missing piece type X, re-run the detector at lower
   confidence and add type-X detections at empty cells.
4. **Legality repair** (e.g. `detection-greedy-legality-repair-by-confidence-demotion`):
   demote impossible classes.

A residual class of failures slips through all of these: the misclassified
piece sits at a canonical type-X starting square, but the detection there is
labelled type-Y (not type-X), and the model's runner-up at that detection is
neither type-X nor in fact anything informative. Top-2 doesn't fire, rescue
doesn't fire (the cell isn't empty), legality doesn't fire (Y is legal at
that square in some positions).

## Context / Trigger Conditions

- Layered detection-repair pipeline already in place (top-2 + rescue +
  legality) and a residual failure pattern persists despite tuning each.
- The misclassified item sits at a square that is canonically type-X (e.g.
  white knight on g1, white rook on a1, queen on d-file), and is labelled
  type-Y (often visually similar: knight↔bishop, rook↔queen, etc.).
- The model's runner-up class is not type-X (so score-based top-2 disambig
  cannot help).
- The cell is occupied, not empty (so rescue cannot help).
- Domain knowledge cleanly identifies "type-X is normally at positions {P1,
  P2, ...}", and pieces of other types being at those positions in real
  play is rare.

## Solution

Add a fifth layer to the repair stack: **canonical-position recovery**.

```rust
fn recover_X_on_canonical_squares(grid: &mut [Vec<char>]) {
    // Trigger: side is missing type X (≤ N count) AND has ≥ M total pieces
    //          (so we're not in a legitimate endgame deficit).
    // Action: walk the canonical squares for X. If the cell holds a
    //         visually-similar wrong type Y of the same colour, rewrite to X.
    let x_count = count_pieces_of_type(grid, X);
    let total = total_pieces(grid, side);
    if total >= MIN_TOTAL && x_count <= MAX_DEFICIT {
        for &(row, col) in CANONICAL_X_SQUARES {
            if grid[row][col] == Y_OF_SAME_SIDE {
                grid[row][col] = X_OF_SAME_SIDE;
            }
        }
    }
}
```

Run AFTER orientation correction (so canonical squares match the corrected
grid coordinates) and BEFORE legality repair (so the recovered labels can
participate in legality decisions).

### Why this beats blind heuristics

The trigger is *gated by deficit*, so it only fires when there's prior
evidence the model lost a type-X piece. The *canonical-square* constraint
is a second gate: in real play, pieces of type Y at type-X starting squares
are vanishingly rare (knights and bishops never end up at b1/g1 in
post-opening positions because pawns block those squares unless
b/g-pawn already moved). So the false-positive rate is small.

### Why not just retrain the detector

Retraining is slower (data + GPU + integration), and it doesn't help users
running the existing model. The recovery pass is one function, runs in
microseconds, and can be removed/tightened later if a retrain solves the
underlying issue.

## Verification

1. Run a fixture-level regression corpus before and after adding the layer.
2. Bucket the failures into gained / lost / unchanged.
3. Net gain should clearly exceed loss; unchanged failures should not include
   the targeted pattern.
4. Spot-check the gained cases: confirm the corrected piece really is the
   right type at the canonical square (not a true type-Y position you've
   wrongly rewritten).

## Example: chess knight recovery in pawn-au-chocolat

**Failure pattern**: white knight on g1 misclassified as white bishop on the
Lichess brown theme. 18 corpus fixtures affected.

**Why prior layers didn't help**:
- Top-2 disambig (`disambiguate_bishop_knight`) required the model's
  runner-up class for the bishop detection to be knight. It wasn't — the
  runner-up was usually queen or rook. So no flip.
- Sub-threshold rescue ran with knight in `missing_piece_types` but
  filtered out anything where the cell was already occupied. The g1 cell
  held a (wrong-class) bishop detection so no rescue.
- Bishops on g1/b1 are rare-but-legal so the legality pass left them.

**Solution** (`recover_knights_on_starting_squares` in `mod.rs`):

```rust
fn recover_knights_on_starting_squares(grid: &mut [Vec<char>]) {
    let w_knights = count(grid, 'N');
    let w_total = total(grid, /* white = */ true);
    if w_total >= 6 && w_knights <= 1 {
        for &col in &[1usize, 6] {            // b1, g1
            if grid[7][col] == 'B' {
                grid[7][col] = 'N';
            }
        }
    }
    let b_knights = count(grid, 'n');
    let b_total = total(grid, /* white = */ false);
    if b_total >= 6 && b_knights <= 1 {
        for &col in &[1usize, 6] {            // b8, g8
            if grid[0][col] == 'b' {
                grid[0][col] = 'n';
            }
        }
    }
}
```

**Result**: corpus pass rate 96.7% → 98.4% (+1.7pp), 18 gained, 0 lost.
Combined with prior fixes, dropped this failure pattern from 18 cells to 0.

## Notes

- This is layer #5 in the repair stack — order matters. Run after
  orientation correction (so canonical squares match grid coordinates) and
  after the rescue pass (so any rescued knights are already in the grid).
- The deficit gate (`knights ≤ 1 AND total ≥ 6`) is critical. Without it
  you would mis-flip legitimate bishops on b1/g1 in unusual endgames.
- For each piece type, the canonical squares are different. White rook:
  a1/h1. Black queen: d8. Etc. Define one recovery function per type
  rather than a generic abstraction — they don't share enough structure.
- Bishops genuinely on knight starting squares in a real game are
  vanishingly rare in modern chess because the pawn structure blocks
  the square. If your domain has different priors (e.g. fairy chess
  variants), tighten the trigger.

## Related skills

- `detection-top2-disambiguation-gated-by-pattern`: prior layer (when
  runner-up class is correct).
- `detection-sub-threshold-rescue-by-deficit`: prior layer (when cell is
  empty).
- `detection-greedy-legality-repair-by-confidence-demotion`: prior layer
  (when result violates rules).
- `heuristic-override-confidence-margin`: orthogonal — about not
  overriding the classifier with bare-majority secondary signals.
