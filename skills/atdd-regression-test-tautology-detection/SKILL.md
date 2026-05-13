---
name: atdd-regression-test-tautology-detection
description: |
  Catch tautological regression tests during ATDD/TDD: a new test that passes on
  its first run, without ever observing the RED state, may not actually exercise
  the failure mode it claims to guard. Use when: (1) adding a regression test for
  a bug-fix or for a guard/filter/gate function and the test goes GREEN immediately,
  (2) the test name/comment claims it exercises a specific failure-mode but the
  asserted condition is also trivially true on neutral/no-signal input, (3) the
  test fed data through several layers of production code (geometry transforms,
  windowing, resizing) before reaching the assertion. Covers the failure mode
  where placed input fixtures don't actually reach the gate the test claims to
  test, leaving a vacuous "passes" that protects nothing and rots silently.
author: Claude Code
version: 1.0.0
date: 2026-05-13
---

# ATDD regression test tautology detection

## Problem

When adding a regression test for a guard, filter, or repair gate in a multi-step
pipeline (image-processing, parser-then-validator, deserialise-then-transform,
etc.), the test author chooses an input fixture that *should* exercise the gate
and writes the assertion. If the test passes on first run, this looks like
success — but a hidden category of bug is that the input fixture doesn't actually
reach the gate. The assertion is "true on the input the gate actually sees,"
which is a tautology when the gate is a no-op for that input.

Concrete failure modes:

1. **Geometry / windowing mismatch**: production code samples a window offset
   from the bbox centre (`SAMPLE_Y_OFFSET_FRAC * height`); test places signal at
   the bbox centre. Production's actual sample sees 0% of the placed signal and
   100% of the surrounding neutral. The assertion "no flip on neutral signal" is
   true regardless of the gate logic the test names.
2. **Filter applied earlier than expected**: production NMS / dedup / threshold
   suppresses the test fixture before it reaches the guard. The guard never
   fires; the test passes because the input was already filtered, not because
   the guard worked.
3. **Inverted/symmetric guard with wrong direction**: test fed white-on-white
   when the bug is white-on-black; guard's threshold is the same in both
   directions but the gate's signal is asymmetric. Passes for the wrong reason.
4. **Conf-threshold mismatch**: rescue/repair gate keyed to confidence < 0.10;
   test fixture lands at 0.15 detection so the gate isn't entered; assertion
   holds because the standard pass picked it up cleanly.

These bugs are invisible at review time because the test name reads correctly,
the comment claims the right thing, and the assertion is a one-line literal.
They only surface years later when the gate logic gets refactored and the test
silently continues to pass.

## Context / Trigger Conditions

Apply this skill whenever you write or review a regression test that:

- Goes GREEN on first run (before the under-test fix is applied)
- Targets a guard / filter / repair gate / disambiguator / threshold function
- Feeds data through 2+ layers of production code before the assertion
- Asserts a "no-op" behaviour (e.g. "class stays the same", "size is unchanged",
  "list is unchanged") rather than a transformation
- Was written for ATDD/TDD discipline where RED-then-GREEN was the protocol

Symptoms that the test is tautological:

- The comment says "X% bright pixels in the sample" but the test never measures
  what fraction the sample actually saw
- The comment cites the guard's specific threshold but the test input is far
  from that threshold (e.g. comment says "0.05 margin", input has 0.0 margin)
- The test passes even when you revert the fix it was written for
- The test passes even when you delete the guard function it was written for
- The test passes when you replace the guard with a no-op
- Inspecting the data at the assertion point shows the wrong intermediate state

## Solution

### Mandatory: verify RED before landing the test

Always run the test BEFORE applying the production-code fix. Confirm it fails
with the exact error you expected. If the test passes without the fix, the test
is tautological — fix it before fixing the code.

Concrete protocol for ATDD:

```
1. Write the test.
2. Run it. If it goes GREEN immediately, STOP — the test is suspect.
3. Verify by reverting any in-flight fixes:
   $ git stash
   $ cargo test <new_test>  # MUST fail
   $ git stash pop
4. If the test still passes after `git stash`, the test is tautological.
   Trace the data flow from input through production code to the assertion;
   find where the signal is being filtered, transformed, or windowed
   differently than the test assumes.
```

### Add a "signal-reached" sanity assertion

For multi-stage pipelines, add a secondary assertion that the test input
actually produced the expected intermediate state. This is cheap and durable:

```rust
// Bad: only asserts the final output
correct_detection_colours(&mut dets, &img);
assert_eq!(dets[0].class_id, 4, "must not flip");

// Good: also asserts the gate condition was actually reached
let (bright_ratio, dark_ratio) = sample_bright_dark_ratios(&img, &dets[0]);
assert!(bright_ratio > 0.10, "test must exercise the bright-bin path; got {bright_ratio:.3}");
assert!((bright_ratio - dark_ratio - 0.07).abs() < 0.02,
    "test must hit the looser-margin zone; got diff {:.3}", bright_ratio - dark_ratio);
correct_detection_colours(&mut dets, &img);
assert_eq!(dets[0].class_id, 4, "must not flip");
```

The signal-reached assertion documents WHAT the test is exercising (not just
what the assertion is). If a future refactor moves the gate, the signal-reached
assertion will RED first — a precise signal that "your refactor broke the gate
this test was guarding."

### Check geometry transforms in test fixtures

When the production code applies any spatial transform between the test input
and the assertion (image resize, bbox-to-cell mapping, coordinate offset,
windowing, sliding window), the test fixture must be placed in the *transformed*
coordinate frame, not the input frame. Compute the transform explicitly:

```rust
// Production samples a window centred at (det.x, det.y + height * 0.12)
let sample_cy = det.y + (bbox_h * SAMPLE_Y_OFFSET_FRAC as u32);
// Place test pixels at (det.x, sample_cy), NOT at (det.x, det.y)
```

If the project doesn't expose the transform constant publicly, the test must
either import it (`use super::SAMPLE_Y_OFFSET_FRAC;`) or duplicate it as a
constant in the test module with a comment cross-referencing the source.

### Reviewer checklist

When reviewing a PR that adds regression tests for guard/filter functions:

1. Does the PR author state they observed RED before applying the fix?
2. Can you `git stash` the fix and re-run the test? Does it fail?
3. Does the test exercise a non-trivial path through the production code,
   or is the input "neutral enough" that any of N gates could account for the
   assertion?
4. If you delete the guard function the test claims to test, does the test
   still pass?

## Verification

A test is *not* tautological iff:

1. Running it without the fix produces a deterministic failure with a specific
   error message
2. Inspecting intermediate state at the assertion point shows the test input
   reached the gate the test names
3. Mutating the gate's threshold (e.g. by ±10%) flips the test result
4. Deleting the gate function causes the test to fail

If your test passes ALL FOUR criteria, it is a genuine regression guard.

## Example

In a Rust chess-piece colour-correction pipeline, the existing test
`colour_correction_keeps_yolo_when_bright_dark_counts_are_close` placed 12%
bright pixels and 17% dark pixels centred at `(280, 280)` for a detection bbox
at `(280, 280, 60, 60)`. The production function `correct_detection_colours`
samples a 31×31 window centred at `(det.x, det.y + det.height * SAMPLE_Y_OFFSET_FRAC)`
where `SAMPLE_Y_OFFSET_FRAC = 0.12`, shifting the sample down by 7.2 px.

The test placed signal at y ∈ [265, 295], but production sampled y ∈ [272, 302].
The 7-pixel offset moved the entire signal out of the sample window. Production
saw 100% neutral grey (128/128/128) → `bright_ratio = 0, dark_ratio = 0` → no
margin gate ever fired → "white queen stays white" assertion was vacuously true.

The test had passed for 8 days. The bug was hidden by:
- Test name "_when_bright_dark_counts_are_close" suggested it exercised the
  margin-based flip gate
- Inline comment cited the exact percentages and the exact FLIP_MARGIN values
- The assertion `assert_eq!(dets[0].class_id, 10)` was uncontroversial because
  the class genuinely didn't flip
- Code review focused on the assertion message, not on whether the placed
  pixels actually reached the production sample window

Discovered by writing a NEW test of similar shape (black queen, 14% bright /
7% dark, asymmetric margin). The new test was expected to fail RED today (the
14% bright_ratio + 7% margin should trigger the new asymmetric FLIP_MARGIN_TO_WHITE).
It passed GREEN on first run. The geometry mismatch was identified by:
1. Reading the production code's sample-window math
2. Computing the actual sample-window coordinates by hand
3. Noticing the placement coords didn't overlap

Fix to the new test: place pixels at `cy = det_y + (bbox_h * 0.12) as u32` so
the placement window overlaps the sample window. The new test then went RED
correctly, the production-code asymmetric-evidence-floor fix made it GREEN, and
the regression was actually pinned.

## Notes

- The bug doesn't only affect image-processing code. Any pipeline where the
  test input is transformed before reaching the guard is vulnerable: parsers
  that normalise whitespace before validation, deserialisers that strip
  optional fields, network layers that apply default headers, validators that
  short-circuit on length checks before reaching the rule under test.
- For pure-function guards (no input transformation), tautology is less common
  but still possible if the test input doesn't hit the gate's specific
  precondition (e.g. testing a "n > 10" gate with `n = 5`).
- Existing tautological tests often pass for *years* because nothing trips them.
  Adding the "signal-reached" assertion is the cheap retrofit; rewriting the
  whole test from scratch is the expensive but correct one.
- Project CLAUDE.md files often document this discipline at a high level
  ("ATDD test discipline: stamp the failure-mode INPUT, not just assert that
  the gate stops no-op cases"). The skill captures the concrete debugging
  protocol when you find yourself with a too-easy GREEN.
