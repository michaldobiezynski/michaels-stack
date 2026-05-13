---
name: detection-top2-disambiguation-gated-by-pattern
description: |
  Pattern for reassigning (not removing) ML-detection class labels when
  the overall output is diagnostically wrong. Use when: (1) your detector
  confidently emits a label whose class is locally plausible but globally
  implausible (e.g. a chess detector emitting 3 bishops and 0 rooks for
  one side), (2) you have access to the detector's top-2 class scores
  (not just argmax), (3) you want to flip class labels back to the
  "correct" alternative without retraining the model. The core trick is
  that the ratio threshold for alt-score can be safely relaxed (e.g.
  10% of top) when gated by a strong positional prior. On its own a 10%
  ratio would false-flip constantly; gated by "suspect pattern holds"
  it becomes a sniper rifle. Sibling to `detection-greedy-legality-
  repair-by-confidence-demotion` — that skill REMOVES pieces when rules
  violate, this one REASSIGNS them when patterns say the top-1 is wrong.
  Applies beyond chess: invoice parsing (total vs subtotal confusion
  when exactly one total is expected), document layout (heading vs
  paragraph confusion when exactly one title is expected), OCR
  (character confusion gated by dictionary words).
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Top-2 disambiguation gated by a global-pattern prior

## Problem

An ML detector (YOLO, CNN, OCR) emits an argmax class per detection.
On some input distributions the argmax is systematically wrong in a
specific way — e.g. rook → bishop in chess, total → subtotal in
invoices, 'l' → 'I' in OCR. The error can be highly confident
(70-80% score on the wrong class) with only a weak secondary signal
for the correct class (5-10%).

Two obvious fixes don't work:
- **Retraining** — correct long-term but off-scope for a post-
  processing change, and you're at the mercy of how much training
  data you can assemble for the failing subdomain.
- **Naive top-2 reassignment** — "if alt-class has score ≥ 50% of
  top, flip" would false-flip constantly on legitimate ambiguous
  detections, degrading overall accuracy.

The insight: **the ratio threshold is a function of your prior**.
When you have strong evidence that the top-1 label is collectively
wrong (a pattern-level prior), you can safely relax the alt-ratio
gate far below 50%. The pattern itself rules out the false-positive
case that a naive 50% rule was guarding against.

## Context / Trigger Conditions

- Detector outputs per-instance class labels with confidence; you
  can also access the top-N class scores (not just argmax).
- A specific class confusion is observed empirically on certain
  input distributions (theme, font, document type, etc.).
- Legality/plausibility checks on the aggregated output reliably
  detect the confusion pattern — e.g. "0 rooks + ≥ 3 bishops per
  side" for chess, "0 totals + ≥ 2 subtotals" for invoices, "this
  word doesn't parse as English" for OCR.
- You want a minimally-invasive fix that doesn't require retraining
  and doesn't affect cases where the pattern doesn't hold.
- Sibling symptom: your detector has an alt_confidence field (top-2
  score) and you're tempted to use it naively with a 50% threshold
  and finding it doesn't fire often enough to be useful.

## Solution

Four steps:

### 1. Carry top-2 through the detection struct

Your detector probably throws away everything except argmax. Change
that:

```rust
struct Detection {
    // ... existing fields ...
    class_id: usize,
    confidence: f32,
    alt_class_id: usize,     // second-best class
    alt_confidence: f32,     // second-best score
}
```

In the argmax loop, track the second-best alongside:

```rust
for c in 0..NUM_CLASSES {
    let score = scores[c];
    if score > max_score {
        second_score = max_score;
        alt_class_id = class_id;
        max_score = score;
        class_id = c;
    } else if score > second_score {
        second_score = score;
        alt_class_id = c;
    }
}
```

### 2. Write a plausibility check that detects the confusion pattern

Write a pure function on the aggregated output that detects your
specific pattern. For chess rook-as-bishop:

```rust
fn suspect_rook_bishop(detections: &[Detection], white: bool) -> bool {
    let (rook, bishop) = if white { ('R', 'B') } else { ('r', 'b') };
    let rooks = detections.iter().filter(|d| d.piece() == rook).count();
    let bishops = detections.iter().filter(|d| d.piece() == bishop).count();
    rooks == 0 && bishops >= 3
}
```

The threshold ("≥ 3") should be calibrated so the pattern has very
low prior probability on legitimate inputs. "3 bishops with 0 rooks"
essentially cannot arise in chess without promotion, so the pattern
is near-diagnostic.

### 3. Disambiguation pass with a relaxed ratio

Gated by the pattern, flip each affected detection when its alt
class matches the expected correct class AND the alt ratio clears
a low bar:

```rust
const ALT_MIN_RATIO: f32 = 0.10; // much lower than a naive threshold

if !suspect_pattern { return; }  // gate

for det in detections {
    if det.class_id != WRONG_CLASS { continue; }
    if det.alt_class_id != EXPECTED_CORRECT_CLASS { continue; }
    if det.alt_confidence < det.confidence * ALT_MIN_RATIO { continue; }

    // Flip.
    det.class_id = EXPECTED_CORRECT_CLASS;
    let old_conf = det.confidence;
    det.confidence = det.alt_confidence;
    det.alt_confidence = old_conf;
}
```

The key is the ratio: 0.10 would be reckless as a naive threshold
but is safe here because the pattern gate already ruled out the
false-positive regime. Calibrate with real data — see your
detector's alt_confidence distribution for the correct class when
the pattern holds.

### 4. Fallback when the top-2 trick can't reach the case

Real-world detectors sometimes produce near-zero alt scores even
when wrong (0.5%-1% of top). The top-2 trick can't flip those
cases safely no matter how low you set the ratio. You need a
complementary mechanism:

- **Template matching** on the failing cell crop against known
  class templates (works when you can enumerate sprite variants
  per theme).
- **Soft warning** surfaced to the user even without automatic
  flip — the plausibility check from step 2 becomes a
  `needs_user_confirmation` signal instead of a silent acceptance.
- **Rescue pass** at a lower detection threshold when the pattern
  suggests missing detections (not this skill's focus — see
  `detection-greedy-legality-repair-by-confidence-demotion` for
  related techniques).

## Verification

1. Inspect alt-score distribution on a failing dataset before
   coding. If alt-scores for the correct class are always
   < 1% of top, this skill doesn't apply — the top-2 trick is
   not viable and you need template matching or retraining.
2. Unit tests must cover:
   - **Flip happens**: pattern holds, alt matches, ratio ≥ threshold.
   - **No flip when pattern absent**: detection stays unchanged even
     with rook-as-alt if the side has 2 rooks detected.
   - **No flip when alt is wrong class**: alt is knight, not rook.
   - **No flip when alt confidence too low**: alt below ratio * conf.
   - **Independence across sides/groups**: flipping fires per-side
     (per-document, per-region, etc.) not globally.
3. End-to-end verification: run on the original failing inputs.
   Before: wrong label; after: correct label. No regressions on
   previously-correct inputs.

## Example

Real session incident on pawn-au-chocolat (chess detection from
Chess.com green-theme screenshots):

- YOLO detection: bishop on a1 (image coord) at conf 0.503.
- Runner-up class in YOLO output: white rook, alt_confidence 0.059.
- Ratio: 0.059 / 0.503 = 11.7%.
- Naive top-2 (≥ 50% threshold) would not flip — 11.7% is way below.
- But the side already has 0 rooks and 3 bishops detected
  (diagnostic "suspect rook-bishop" pattern).
- With the pattern gate, a 10% ratio threshold is safe. The
  detection flips to rook. End-to-end FEN now contains the correct
  rook on a1.

Code in `src-tauri/src/image_detection/piece_detector.rs`:
`disambiguate_rook_bishop`. Tests:
`disambiguate_flips_bishop_to_rook_when_suspect_and_alt_matches`
and siblings.

## Notes

- This pattern is COMPLEMENTARY to confidence-demotion-based legality
  repair. One removes pieces when rules violate; this one reassigns
  class labels when patterns say the top-1 is wrong. Use both.
- The suspect pattern must be STRONGLY diagnostic. "2 bishops + 0
  rooks" is too weak (legitimate mid-games do lose rooks). "3 bishops
  + 0 rooks" is strong (requires promotion, which is rare).
- The ratio threshold is tunable per detector. Start at 0.10;
  measure false-flip rate on a validation set; adjust.
- When the alt_confidence is essentially zero (< 1% of top) even on
  failing cases, this skill doesn't help — the model has no residual
  signal to reassign on. Template matching or retraining is the only
  path.
- Log every flip at INFO level so production bugs surface in the
  operator's logs. The log line should include the original class,
  the new class, and both scores.
- Apply the pattern gate to AGGREGATED state before the flip loop,
  not inside it. Doing it inside risks a flip mutating the pattern
  check for later flips in the same pass.

## References

- Sibling skill: `detection-greedy-legality-repair-by-confidence-demotion`
  — removes pieces when output is illegal. This skill reassigns when
  output is implausible.
- Sibling skill: `chess-board-a1-parity-cannot-disambiguate-orientation`
  — counterintuitive findings from the same chess-detection project.
- [YOLOv8 output format (per-class scores at index 4..4+NUM_CLASSES)](https://github.com/ultralytics/ultralytics)
- [Bakken & Baeck ChessVision](https://tech.bakkenbaeck.com/post/chessvision)
  — concept paper acknowledging confidence-aware post-processing.
