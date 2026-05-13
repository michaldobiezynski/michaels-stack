---
name: detection-sub-threshold-rescue-by-deficit
description: |
  Pattern for recovering missed detections when an ML-detection pipeline
  (YOLO, CNN, etc.) has a piece/component below the standard confidence
  threshold but a domain-rule check says "something should be here".
  Use when: (1) a chess-piece detector drops a rook at 0.17 confidence
  under a 0.25 threshold, leaving the side with 0 rooks plus 10 other
  pieces, (2) a document-parser drops an "amount total" row that the
  schema requires to exist, (3) any detection pipeline whose output is
  rule-constrained and where lowering the global threshold would
  introduce too many false positives. Complementary to
  detection-greedy-legality-repair-by-confidence-demotion (that skill
  REMOVES extras; this skill ADDS gaps). Core idea: run a structural
  deficit check on the standard-pass output; only when a deficit fires,
  re-run detection at a lowered threshold, then keep rescue candidates
  that (a) fill empty cells / regions, (b) classify as the specific
  missing type, (c) survive the existing quality filters.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Sub-threshold rescue pass gated by structural deficit

## Problem

ML detection pipelines drop true positives whose confidence sits just
under the accept threshold. Two failure modes on real chess screenshots:

- A white rook on `a1` scores 0.176 on Chess.com's green theme; the
  0.25 threshold rejects it and the user sees a rook-free back rank.
- Simultaneously, the 0.10-threshold output includes false positives
  (e.g. a phantom `P` on `f1` at 0.182) that a blanket threshold
  lowering would accept too.

The obvious fixes both fail:

- **Lower the global threshold**: catches the missing rook, but also
  reintroduces hallucinations. Net precision drops.
- **Scan empty cells by pixel variance**: tells you *something* is on a
  cell but not *what*. Without a piece-type classification you cannot
  fill the gap in the detected grid, only warn the user.
- **Train a better model**: out of scope for a post-processing commit
  and does not guarantee zero dropouts on new themes.

The effective fix is a structurally-gated rescue pass: only re-run at a
lowered threshold when domain rules say a specific piece type is
missing, and only keep rescue detections that match that type on empty
cells.

## Context / Trigger Conditions

This skill applies when ALL of the following hold:

1. Your detector exposes a `detect_*_with_threshold(image, model, conf)`
   surface (or equivalent) so callers can rerun inference at a custom
   threshold. If it does not, add that parameter before adopting this
   pattern.
2. Your domain has countable-type rules that can flag "X of type Y
   should exist on side Z but zero were detected". Chess:
   side-has-≥6-pieces-but-0-rooks. Documents: schema-says-every-invoice-
   has-a-total-row-but-none-found. Forms: expected-barcode-not-detected.
3. Your grid/cell structure lets you decide whether a rescue detection
   lands on an empty region. Chess: cell occupancy in the post-YOLO
   grid. Documents: bounding-box overlap with already-placed fields.
4. The "lowered threshold" value is materially below the standard
   threshold but not arbitrarily low (0.10 vs 0.25 on YOLOv5/v8 is the
   sweet spot in practice; below 0.05 noise dominates).

If you are fixing "too many" problems (extra kings, duplicate rows),
this is the wrong skill — use
`detection-greedy-legality-repair-by-confidence-demotion` instead.

## Solution

### 1. Expose a per-call threshold parameter on your detector

The standard entry point stays at the production threshold, but a
second entry point takes a custom threshold:

```rust
pub fn detect_pieces(image: &RgbImage, model: &Path) -> Result<Vec<Detection>> {
    detect_pieces_with_threshold(image, model, CONF_THRESHOLD)
}

pub fn detect_pieces_with_threshold(
    image: &RgbImage,
    model: &Path,
    conf: f32,
) -> Result<Vec<Detection>> {
    // Standard pipeline: resize → inference → NMS → colour correction
    // → occupancy pre-filter → disambiguation.
    // All of these apply at the threshold the caller chose.
}
```

Critically, all the downstream quality filters (NMS, colour
correction, occupancy pre-filter, etc.) run at the rescue threshold
too. That is how we avoid re-introducing false positives in the
rescue batch without adding a separate filter chain.

### 2. Structural-deficit detector on the standard-pass grid

Mirror the "is something missing?" question as pure grid logic. Return
structured entries (not strings) so the rescue pass can consume them:

```rust
pub struct MissingPieceType {
    pub is_white: bool,
    pub piece_char: char,  // 'R', 'r', etc.
}

pub fn missing_piece_types(grid: &[Vec<char>]) -> Vec<MissingPieceType> {
    let (w_rooks, b_rooks, _, _, w_total, b_total) =
        count_rook_bishop_tally(grid);
    let mut missing = Vec::new();
    if w_total >= 6 && w_rooks == 0 {
        missing.push(MissingPieceType { is_white: true, piece_char: 'R' });
    }
    if b_total >= 6 && b_rooks == 0 {
        missing.push(MissingPieceType { is_white: false, piece_char: 'r' });
    }
    missing
}
```

Keep the gate conservative. A 6-piece floor on chess avoids firing the
rescue on legitimate endgames (K+P+K with no rooks is legal and common).
The equivalent floor for document parsing is "≥ N non-empty regions" or
"pages where the header classifier already fired".

### 3. Filter the rescue batch by (cell-empty, type-matches)

After the lowered-threshold re-run, accept only candidates that satisfy
both gates:

```rust
pub fn filter_rescue_detections(
    rescue: Vec<Detection>,
    original_grid: &[Vec<char>],
    missing_types: &[MissingPieceType],
    board_width: f32,
    board_height: f32,
) -> Vec<Detection> {
    if missing_types.is_empty() {
        return Vec::new();
    }
    let cell_w = board_width / 8.0;
    let cell_h = board_height / 8.0;
    rescue.into_iter().filter(|det| {
        let col = (det.x / cell_w) as usize;
        let row = ((det.y + det.height / 2.0 - cell_h / 2.0) / cell_h) as usize;
        if row >= 8 || col >= 8 { return false; }
        if original_grid[row][col] != '.' { return false; }
        let Some(piece_char) = class_id_to_char(det.class_id) else { return false; };
        missing_types.iter().any(|m| m.piece_char == piece_char)
    }).collect()
}
```

Two invariants that are easy to get wrong:

- **Never overwrite an existing cell**: the `original_grid[row][col] != '.'`
  check. If you skip it, a low-confidence false positive on an occupied
  cell can flip a confident correct piece to a wrong one during merge.
- **Use the same cell-mapping geometry as the main grid mapper**: if the
  main mapper uses `(det.y + height/2 - cell_h/2) / cell_h` for the row,
  the rescue filter must too. Mismatched geometry silently misroutes
  rescues to the wrong cell.

### 4. Wire into the pipeline between standard detection and grid mapping

```rust
let mut detections = detect_pieces(&image, &model)?;
let (initial_grid, _) = map_to_grid_with_confidence(&detections, w, h);
let missing = missing_piece_types(&initial_grid);
if !missing.is_empty() {
    let rescue_raw = detect_pieces_with_threshold(&image, &model, RESCUE_CONF_THRESHOLD)?;
    let rescued = filter_rescue_detections(rescue_raw, &initial_grid, &missing, w, h);
    detections.extend(rescued);
}
let (grid, confs) = map_to_grid_with_confidence(&detections, w, h);
// Continue with orientation correction, legality repair, FEN.
```

Merging is a plain `Vec::extend` because the filter has already guaranteed
the rescue candidates land on cells the standard pass did not claim.

## Verification

1. **Unit tests without the ONNX model**: the deficit detector and rescue
   filter are pure grid logic. Write 4-7 tests exercising the truth table:
   - No missing types → empty rescue output.
   - Missing type + empty cell + matching class → kept.
   - Missing type + occupied cell → dropped.
   - Missing type + empty cell + wrong class → dropped.
   - Endgame with < 6 pieces → no missing types flagged.
   - Both sides deficit → both flagged.

2. **End-to-end regression on the failing screenshot**: an `#[ignore]`
   integration test that loads the real failing image, runs both passes,
   and hard-asserts the previously-dropped piece appears at the expected
   cell. Gate on the image+model file existing so CI without those
   artefacts silently skips.

3. **Diagnostic harness shows the rescue output**: if your project has a
   `diagnose_image`-style harness that dumps raw detections + grid,
   extend it to also dump the deficit check, rescue batch, filter
   survivors, and merged grid. This is how you manually verify new
   failure cases before coding a regression for them.

4. **Corpus regression must still pass**: if you have a grid-level
   test corpus (fixed `raw_grid` inputs, expected FEN outputs), the
   rescue wiring should not change those outputs because the corpus
   feeds synthetic grids that do not involve YOLO.

## Example

Chess.com green-theme screenshot with a white rook on `a1`:

```
Standard pass at conf>=0.25:
  24 detections, a1 = '.' (rook at 0.176 was dropped)
  grid row 1: ..B...K.

missing_piece_types(grid) = [MissingPieceType { is_white: true, piece_char: 'R' }]

Rescue pass at conf>=0.10:
  27 detections (3 new, including 'R' at a1 conf 0.176 and 'P' at f1 conf 0.182)

filter_rescue_detections keeps:
  1 detection: 'R' at a1 (matches missing type, a1 is empty)
  'P' at f1 dropped: type 'P' is not in missing types
  The other extra: already on an occupied cell

Merged grid row 1: R.B...K.  ✓
```

The key observation: a blanket threshold lowering to 0.10 would have
accepted the phantom pawn on `f1` too, silently corrupting the FEN.
Gating the rescue on `missing_piece_types` + filtering by matching
class keeps precision intact.

## Notes

- **Threshold value**: 0.10 is empirical for YOLOv5/v8 on chess piece
  detection. Tune by running the diagnostic harness over your failing
  cases and picking the lowest threshold at which the true positive
  appears without significant noise.
- **Cost**: the rescue pass duplicates inference cost. Gating on
  `!missing.is_empty()` keeps the cost paid only when the structural
  check says it is worth it. On clean images this should fire on a
  small minority of frames.
- **Per-side vs per-pass**: one lowered-threshold inference call covers
  every side and every class simultaneously. Filter per-side in the
  consumer, do not run the inference twice.
- **Do not chain rescues**: after one rescue pass, do not check
  deficits on the merged grid and re-rescue. Either the deficit is
  gone (success) or it persists (the model genuinely has nothing to
  offer even at 0.10 — the legality/confirmation layer downstream is
  the right next step).
- **Cross-reference**:
  - `detection-greedy-legality-repair-by-confidence-demotion` — the
    "too many" complement.
  - `detection-top2-disambiguation-gated-by-pattern` — the
    "wrong class" complement. Use together for full post-YOLO coverage.
  - `yolo-chess-colour-correction` — orthogonal fix for a common
    upstream failure mode on dark themes.
- **Generalisation**: the same pattern works for non-chess rule-
  constrained detection. Invoice parsing: if every invoice has a
  "total" row but none was detected, rescue for class `total` at
  lowered threshold over empty regions. Document layout: if every page
  has a title block but none fires, rescue for class `title`. Any
  schema where "type X appears at least once" is a hard rule and
  detection sometimes drops it.

## References

- In-repo implementation (pawn-au-chocolat):
  - `src-tauri/src/image_detection/legality.rs` — `MissingPieceType`,
    `missing_piece_types`.
  - `src-tauri/src/image_detection/piece_detector.rs` —
    `RESCUE_CONF_THRESHOLD`, `filter_rescue_detections`,
    `detect_pieces_with_threshold`.
  - `src-tauri/src/image_detection/mod.rs` — rescue wiring inside
    `detect_position_bytes`.
- Companion skills: `detection-greedy-legality-repair-by-confidence-demotion`,
  `detection-top2-disambiguation-gated-by-pattern`,
  `yolo-chess-colour-correction`.
