---
name: heuristic-override-confidence-margin
description: |
  Pattern for post-classification heuristic correction layers that override a
  primary classifier (YOLO, CNN, OCR, embedding model, etc.). Use when:
  (1) a rule-based or pixel-level heuristic flips ML labels and you observe
  it OVER-correcting on a subset of inputs, (2) a "post-processing pass"
  improves recall on some classes but silently degrades others, (3) you have
  a verifiable corpus showing the heuristic's flip rate exceeds its accuracy
  on borderline cases, (4) the heuristic and the classifier give a near-tie
  signal but the heuristic always wins, (5) a symmetric flip-margin is
  blocking recovery of a known classifier bias in one specific direction
  while you don't want to weaken the other direction. Solution: require a
  CONFIDENCE MARGIN before the heuristic overrides the classifier, and
  consider splitting the margin into ASYMMETRIC per-direction thresholds
  when one direction has a named systemic classifier-bias to recover from.
  Includes diagnostic technique: side-by-side bin-count comparison between
  same-position fixtures rendered on different themes pinpoints whether
  the heuristic itself is off, the threshold is too tight, or the
  classifier is biased.
author: Claude Code
version: 1.1.0
date: 2026-05-11
---

# Heuristic-overrides-classifier confidence margin

## Problem

A post-processing layer applies a rule-based or pixel-level heuristic on top
of a primary classifier (ML model) to correct its mistakes. The heuristic
checks for an alternative signal (e.g. mean pixel brightness for piece colour
correction, dictionary lookup for OCR, lexical pattern for entity type) and
flips the classifier's label whenever the heuristic's signal disagrees.

The naive override rule looks like:

```rust
if heuristic_signal != classifier_label {
    label = heuristic_signal;  // bare-majority flip
}
```

This works well when the heuristic is *strongly* discriminating, but fails on
borderline cases where the heuristic's signal is noisy. The heuristic flips
labels on cases where its evidence is barely on one side of the decision
boundary -- and on those cases, the classifier was actually right. You see:

- New regressions appear that didn't exist before the heuristic was added.
- Aggregate accuracy stalls or drops despite "improving" on the targeted
  failure mode.
- A debugging corpus shows clusters of newly-broken cases all sharing the
  pattern that the heuristic *barely* preferred the wrong label.

## Context / Trigger Conditions

- ML pipeline emits class labels and a downstream heuristic re-checks them.
- A regression corpus or unit-test suite shows the heuristic helps on some
  inputs but breaks others.
- The breakage cases share a pattern: the heuristic's signal is close to the
  classifier's, just barely on the other side.
- Common domains: piece colour in chess board detection, character labels in
  OCR (lookup-based correction), spam vs. ham (rule-based override of model),
  entity type in NER (gazetteer override of model).

## Solution

Require a **confidence margin** before the heuristic flips the classifier's
label. The heuristic must beat the primary by more than the margin, otherwise
defer to the primary.

```rust
const FLIP_MARGIN: f32 = 0.10;  // tune empirically

let heuristic_signal_strength = ...;  // e.g. ratio of bright vs dark pixels
let primary_label = classifier_label;

let pixel_strongly_says_white = bright_ratio > min_evidence
    && bright_ratio - dark_ratio > FLIP_MARGIN;
let pixel_strongly_says_black = dark_ratio > min_evidence
    && dark_ratio - bright_ratio > FLIP_MARGIN;

let heuristic_says = if pixel_strongly_says_white {
    Some(WHITE)
} else if pixel_strongly_says_black {
    Some(BLACK)
} else {
    None  // ambiguous - defer to classifier
};

if let Some(h) = heuristic_says {
    if h != primary_label {
        label = h;  // confident flip
    }
}
```

Two thresholds matter:

1. `min_evidence` — the heuristic's evidence must clear a floor. Rejects
   near-empty samples / outlier noise.
2. `FLIP_MARGIN` — the heuristic must beat the alternative by this much.
   Rejects bare-majority cases where the heuristic is unreliable.

### Picking the margin

- Start at the smallest margin that prevents your known regressions.
- Run the regression corpus at multiple margins (0.05, 0.10, 0.15, 0.20) and
  plot net delta vs. margin.
- The right margin is the one with the best NET (gained – lost) score, not
  the one with most gains or fewest losses.
- For each unit of margin you trade specificity (heuristic stops correcting
  more cases) for precision (heuristic stops mis-flipping cases).

### Asymmetric margins when one direction is the riskier flip

A single symmetric margin assumes BOTH override directions have the same
false-positive risk. In practice they usually do not. Common patterns where
one direction is riskier than the other:

- **Sprite-design asymmetry.** In chess piece detection, white pieces have
  thick dark outlines around bright bodies; black pieces are bright-poor
  throughout. The bins-path can read a white piece as "more dark than bright"
  if the sample catches enough outline, but the reverse failure (reading a
  black piece as "more bright than dark") is much rarer — black bodies have
  no bright fill to mislabel. The white→black flip direction needs the
  STRICT margin; the black→white flip direction can be LOOSER.

- **Classifier bias.** If YOLO (or any classifier) has a known systemic
  over-prediction in one class — e.g. "labels white bishops on chromatic
  dark squares as black" — the heuristic's RECOVERY direction (flip-to-
  white) needs the looser margin to catch the marginal recoverable cases.
  The opposite direction stays strict to avoid amplifying the classifier's
  good calls.

- **Domain prior.** A spam-classifier with a heuristic flip from spam→ham
  on whitelist matches can afford a loose flip-to-ham margin (false ham is
  user-noticed; false spam silently drops mail).

Split the margin into two constants and pick each empirically:

```rust
const FLIP_MARGIN_TO_X: f32 = 0.10;  // strict — only flip X if dominant
const FLIP_MARGIN_TO_Y: f32 = 0.05;  // loose — recover marginal Y cases

let strongly_x = x_evidence > min_evidence
    && x_evidence - y_evidence > FLIP_MARGIN_TO_X;
let strongly_y = y_evidence > min_evidence
    && y_evidence - x_evidence > FLIP_MARGIN_TO_Y;
```

The asymmetry is justified when you can name a specific failure-mode the
classifier is biased toward — i.e. when you can point at the corpus and say
"these fail because the classifier was wrong AND the symmetric threshold
blocked recovery." Without that named bias, stay symmetric.

### Diagnostic: side-by-side fixtures of the SAME position on different themes

When two fixtures render the same chess position on different themes and
ONE passes / ONE fails, the side-by-side bin counts are the highest-signal
diagnostic in the system. Log the heuristic's intermediate values for both
fixtures and compare. Three outcomes:

1. **Heuristic gives identical-ish counts on both.** The failing fixture is
   different upstream — the classifier itself is wrong on that theme.
   (Most common cause: YOLO trained more heavily on one theme palette.)
   The heuristic's *threshold* is the question to tune.

2. **Heuristic gives wildly different counts.** The heuristic itself is
   theme-sensitive. Look at the sample-region selection logic, the bin
   thresholds, the chromaticity gate, etc. The heuristic needs structural
   improvement, not just threshold tuning.

3. **Counts are similar AND classifier agrees on both.** The fixture isn't
   actually parallel — different upstream cropping, different orientation,
   etc. Fix the test scaffolding before drawing conclusions.

The case where BOTH fixtures have evidence below the heuristic's threshold,
and one passes only because the classifier was right by luck, is the
telltale signal that the symmetric threshold is wrong and an asymmetric
threshold is correct. The classifier was the entire reason the passing
fixture passed; without the heuristic doing anything, both should pass or
both should fail.

## Verification

1. Run the regression corpus at the new margin and compare per-fixture
   pass/fail diff against the baseline.
2. Confirm net is positive (gains > losses).
3. Spot-check the LOST cases — for each, ask whether the regression is
   acceptable in isolation (often it is: a marginal case where the heuristic
   was barely-right is replaced by a marginal case where the classifier is
   barely-right).
4. Ratchet your test corpus / manifest to lock in the gains as new
   regression-guards.

## Example: Chess piece colour correction (symmetric margin, 2026-04)

In pawn-au-chocolat (`src-tauri/src/image_detection/piece_detector.rs`),
YOLO classifies chess pieces as 12 classes (6 piece types × 2 colours). A
post-processing pass `correct_detection_colours` samples pixels in each
detection's bounding box, counts bright (>180) and dark (<70) pixels, and
flips the colour bit if dark wins or bright wins.

The naive bare-majority flip mis-classified white queens as black queens on
8 corpus fixtures: the queen sprite has dense black filigree at its crown,
which dominates the centre sample. The bright body fill (white) and dark
filigree counts came out near-equal — bright at 24%, dark at 27% — and the
3pp dark majority flipped the YOLO-correct white-queen call.

Adding `FLIP_MARGIN = 0.10` (10 percentage points) preserved the YOLO call
on these borderline cases while still allowing strong-signal flips (where
e.g. dark > bright by 30+ pp on a clearly black piece). Result: corpus pass
rate 56/70 (80%) → 62/70 (88.6%), +6 fixtures net.

The two attempted alternatives both regressed massively:

- **Full-bbox chromaticity sampling**: filter background pixels by
  chromaticity (R≈G≈B = piece, else background), sample full bbox. Broke
  30 fixtures because the chromaticity-filter still let in bright-anti-
  aliased edges and the larger sample area amplified the dark-outline bias.
- **Cell-centre sampling**: snap sampling to the chess cell centre rather
  than the bbox centre. Broke 34 fixtures because rooks/bishops don't have
  their bright body at the cell centre — the centre lands on the dark
  finial / mitre tip and almost no bright pixels are caught.

Both failed for the same reason: they tried to make the heuristic *more
informative* when the right move was to make it *more conservative*.

## Example: Asymmetric margin (2026-05)

Same codebase, follow-up. After the symmetric-margin fix, the corpus still
showed 5 chess.com green fixtures with white bishops on chromatic dark
squares (square luminance 133, so the bins-path / Path A was selected)
being mis-labelled as black by YOLO. Path A read `bright_ratio ≈ 0.36,
dark_ratio ≈ 0.30` — a 0.06 margin in the WHITE direction, just below the
symmetric `FLIP_MARGIN = 0.10` so the heuristic deferred to YOLO and the
mis-label stood.

The diagnostic that nailed it: the SAME position rendered on Lichess brown
hit nearly identical bin counts (`bright 0.37, dark 0.27`, margin 0.098,
still below 0.10) and PASSED. The difference wasn't the heuristic at all —
YOLO labelled the brown render correctly as white, so the heuristic
deferring to YOLO was correct on brown and wrong on green. The symmetric
threshold blocked recovery in BOTH directions; the brown fixture was
saved only by classifier luck.

Fix: split into `FLIP_MARGIN_TO_BLACK = 0.10` (unchanged, conservative)
and `FLIP_MARGIN_TO_WHITE = 0.05` (loose). The looser white-direction
margin recovers the marginal-evidence cases where YOLO mis-labelled a
white piece on chromatic dark squares; the strict black-direction margin
preserves the white-queen no-flip behaviour from the symmetric-margin fix.
6 corpus fixtures flipped to passing (5 green + 1 brown variant of the
same dutch-defence position). No regressions across the 41 piece_detector
unit tests, the real-screenshot suite, or the bishops-long-diagonal
cluster.

The asymmetry mirrors a real asymmetry in the failure-mode evidence: YOLO
mis-labels white pieces as black far more often than the reverse on
chromatic dark squares, so the recovery direction needs the looser margin.
The reverse direction has no similar systemic bias to recover from, so it
keeps the strict threshold.

## Notes

- This pattern is a special case of "ensemble methods with weighted votes":
  when one voter has a much stronger prior (the trained classifier), the
  weaker voter (rule-based heuristic) needs a confidence margin to overrule
  it. Without the margin you're effectively giving both voters equal weight.
- It composes cleanly with other post-processing layers — apply confidence
  margins at every override hop, not just the colour one.
- Be wary of `FLIP_MARGIN = 0`: this is the bare-majority case and is the
  default when you write `if a > b { ... }`. Make the margin explicit.
- Keep the existing tight sample region (don't enlarge it). Enlargement
  shifts the bright/dark baseline and invalidates the empirical thresholds
  the original code was tuned on.

## Verification workflow

When changing a post-classification heuristic:

1. **Profile real fixtures first.** Sample pixels at multiple radii / regions
   for both passing and failing cases. Don't change code based on intuition
   about "where the body is."
2. **Run the regression corpus before AND after.** Compute gained / lost /
   unchanged buckets, not just aggregate pass rate.
3. **If lost > gained, revert.** A "fix" that breaks more than it fixes is
   net-negative even if the failure mode it targeted is conceptually correct.
4. **Try multiple values of the threshold.** The right value is empirical,
   not theoretical.
5. **Ratchet the manifest.** Flip `expected_pass` to lock in gains so any
   future regression on those cases is caught.

## References

- The pattern shows up in ML literature under "confidence-aware ensemble
  decisions" and "calibrated post-processing rules".
- pawn-au-chocolat existing skills that compose with this:
  `detection-greedy-legality-repair-by-confidence-demotion`,
  `detection-top2-disambiguation-gated-by-pattern`,
  `detection-sub-threshold-rescue-by-deficit`,
  `yolo-chess-colour-correction`.
