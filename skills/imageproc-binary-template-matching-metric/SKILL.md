---
name: imageproc-binary-template-matching-metric
description: |
  Counterintuitive finding when using `imageproc::template_matching::match_template`
  on BINARY (0/255) masks to discriminate between two candidate shape templates:
  `SumOfSquaredErrors` (and its normalised form) silently rewards
  background-background agreement, so a SPARSER template can win against a
  denser template purely because it has more "bg matches bg" pixels, even when
  the denser template's shape is visibly correct. Use when: (1) doing shape
  classification via imageproc template matching on 0/255 masks, (2) two
  templates differ in foreground pixel count and the "wrong" one is winning,
  (3) the scores are surprisingly close to each other on clearly-distinct
  shapes, (4) you reach for SSE because "lower SSE = better match" felt right.
  The fix is to use `CrossCorrelationNormalized` instead, which on binary
  inputs reduces to cosine similarity of the foreground pixel sets and
  therefore IGNORES bg-bg agreement.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# imageproc binary-mask template matching: SSE rewards bg-bg, use NCC instead

## Problem

You want to discriminate between two candidate shape templates (e.g. rook vs
bishop, square vs circle, one-peak vs two-peak) by running
`imageproc::template_matching::match_template` over a pair of binary masks.
Intuition says SSE (sum of squared errors) is the right metric: lower error
equals better match. So you reach for `MatchTemplateMethod::SumOfSquaredErrors`
or `SumOfSquaredErrorsNormalized`.

On real data the "wrong" template keeps winning, and the scores on distinct
shapes are surprisingly close. The reason: on a 0/255 binary image, SSE also
rewards every `(T=0, I=0)` pixel — background agreeing with background
contributes **zero** error. Given a mostly-empty template canvas, that's a huge
free win. A sparser template (fewer foreground pixels) therefore has MORE
"bg agrees with bg" pixels than a denser template, and can beat it even when
its foreground shape is clearly wrong.

## Context / Trigger Conditions

- You're comparing a binary mask against multiple binary templates in Rust with
  `imageproc 0.26.x` (or similar) using `match_template`.
- Your scores are very close (e.g. 0.78 vs 0.86 for shapes that should be
  visibly different).
- The template with FEWER foreground pixels is consistently winning or
  holding its own.
- You're using `MatchTemplateMethod::SumOfSquaredErrors` or
  `SumOfSquaredErrorsNormalized`.
- Expected ratio of "right template / wrong template" is ≤ ~1.10, not 1.3+.

## Solution

Use `MatchTemplateMethod::CrossCorrelationNormalized` instead.

On 0/255 binary inputs, NCC reduces exactly to the cosine similarity of the
foreground pixel sets:

    NCC = |T ∩ I| / sqrt(|T| · |I|)

This metric keys purely on foreground overlap and gives no credit for
bg-bg agreement, so it ranks shape similarity correctly even when one
template is substantially sparser than the other.

```rust
use imageproc::template_matching::{match_template, MatchTemplateMethod};

let out = match_template(
    &mask,
    &template,
    MatchTemplateMethod::CrossCorrelationNormalized,
);
let best = out.pixels().map(|p| p[0]).fold(f32::MIN, f32::max).max(0.0);
```

## Verification

Generate a 64×64 binary mask of shape A. Build two templates (48×20), one
of shape A and one of shape B (distinct and deliberately sparser). Score both:

- With `SumOfSquaredErrors`: ratio `sim_A / sim_B` often < 1.10, sometimes
  < 1.0 (wrong template wins).
- With `CrossCorrelationNormalized`: ratio ≥ 1.2 reliably, often 1.3+.

In one real test, the same mask gave:
- SSE: rook_sim=0.855, bishop_sim=0.819, ratio=1.045 (bishop falsely close)
- NCC: rook_sim=0.917, bishop_sim=0.647, ratio=1.417 (correct, decisive)

## Example

From a chess-piece classifier using binary cap-only templates (48×20) on
a 64×64 piece-silhouette mask:

```rust
// WRONG — SSE rewards bg-bg, sparse bishop template wins undeservedly
fn match_score_bad(image: &GrayImage, template: &GrayImage) -> f32 {
    let out = match_template(image, template, MatchTemplateMethod::SumOfSquaredErrors);
    let best_sse = out.pixels().map(|p| p[0]).fold(f32::MAX, f32::min);
    let worst = 255.0 * 255.0 * (template.width() * template.height()) as f32;
    1.0 - best_sse / worst
}

// CORRECT — NCC on binary = cosine similarity of foreground sets
fn match_score_good(image: &GrayImage, template: &GrayImage) -> f32 {
    let out = match_template(image, template, MatchTemplateMethod::CrossCorrelationNormalized);
    out.pixels().map(|p| p[0]).fold(f32::MIN, f32::max).max(0.0)
}
```

## Notes

- `imageproc 0.26.1` does NOT provide zero-mean NCC (aka OpenCV's
  `TM_CCOEFF_NORMED`). Only the regular NCC is available. For binary inputs
  this is fine because the mean is implicit; for grayscale inputs with drifting
  backgrounds you'd need to subtract means yourself.
- The ratio-based flip rule (`rook_score > bishop_score * margin`) is safer
  with NCC because NCC scores are bounded in [-1, 1] and reflect actual
  foreground similarity, so a fixed margin (e.g. 1.10) has consistent meaning
  across image sizes.
- This gotcha only applies to binary (or near-binary) inputs. On grayscale
  photographs where templates and images have similar intensity profiles, SSE
  can still be a reasonable choice.
- Related trap: matching a template whose bg happens to match the image's
  bg intensity will always score well for the same reason. If you care about
  foreground shape, binarise explicitly rather than hoping the matching
  method handles it.

## References

- [imageproc::template_matching module docs](https://docs.rs/imageproc/0.26.1/imageproc/template_matching/)
- [OpenCV template matching modes](https://docs.opencv.org/4.x/df/dfb/group__imgproc__object.html)
  (for background on CCORR vs CCOEFF vs SQDIFF)
