---
name: hough-cluster-multi-instance-spurious-intersections
description: |
  Why naive "cluster Hough-line intersections to separate multiple instances of
  pattern X in one image" pipelines silently produce wrong results. Use when:
  (1) building multi-board chess detection (two boards in one screenshot, want
  the largest); (2) multi-table OCR or multi-document layout segmentation that
  voted for grids via Hough; (3) any computer-vision pipeline that finds
  instances by detecting a regular line pattern, computing line crossings, and
  clustering the crossings spatially; (4) the unit tests on synthetic
  intersection sets pass but the integration test on a real composed image
  fails with one giant cluster spanning everything; (5) you reach for
  union-find or DBSCAN on Hough intersections expecting per-instance clusters.
  Root cause: the standard Hough → polar → cartesian pipeline extends each
  detected line across the FULL image (line length = 2 * max(image_w,
  image_h)), so horizontals from instance A intersect verticals from instance
  B in the blank space between them, producing intersection points that have
  no corresponding visual feature but bridge the per-instance clusters via
  any spatial-proximity clustering. The fix is NOT a different clustering
  algorithm; it is filtering intersections against the underlying Canny edge
  image so only points where edges actually cross are kept. Adjacent insight
  about quad-area: shoelace area on a 4-point set ordered as
  [TL, BL, TR, BR] (a self-crossing path) returns 0 for axis-aligned
  rectangles - use bounding-box area instead when the point order is
  inherited from min/max-of-sum/diff corner extraction.
author: Claude Code
version: 1.0.0
date: 2026-05-14
---

# Hough-line clustering bridges multiple instances via spurious intersections

## Problem

You have an image containing N>1 instances of a regular grid-shaped pattern
(chessboards, tables, spreadsheet cells, document margins). You want to
locate each instance separately so you can pick the largest, or process
each one. The natural pipeline is:

1. Canny edge detection on greyscale.
2. Hough line transform to get polar lines (r, theta).
3. Convert to cartesian segments via `polar_to_cartesian`.
4. Find all line-line intersections.
5. Cluster the intersections by spatial proximity (DBSCAN, union-find, etc).
6. Each cluster = one instance; pick the largest by bounding-box area.

This pipeline is correct on synthetic input where you hand-craft per-instance
intersection sets and pass them directly to step 5. It silently fails on
real image input because step 3 extends each polar line across the FULL
image. With two grids in one frame, the horizontals from grid A intersect
the verticals from grid B in the blank space between them. Those
intersection points have no visual feature backing them, but they exist in
the intersection set, and step 5's spatial clustering happily bridges the
per-instance clusters via union-find, producing one giant cluster that
spans both grids. Picking "the largest" then returns a bbox that encloses
both instances (or just the merged cluster's extent).

## Context / Trigger Conditions

- You are building or maintaining a CV pipeline that needs to find multiple
  instances of a grid-shaped pattern in one image.
- Unit tests on synthetic intersection sets (e.g. hand-crafted points
  arranged as a 9x9 grid) PASS — you confirm the clustering algorithm
  correctly produces one cluster per grid.
- An end-to-end test on a real composed image (e.g. two checkerboards
  rendered onto one canvas) FAILS — typically the picked bbox starts at
  (0, 0) or has dimensions matching the image rather than either grid.
- You are using `imageproc::hough::detect_lines` or any other Hough
  implementation that returns polar `(r, theta)` lines.
- Your codebase has a function like `polar_to_cartesian` that produces
  `Line { x1, y1, x2, y2 }` segments by extending the polar line with
  some `extent` factor (typically `2 * max(image_w, image_h)`).
- Your intersection finder treats those segments as line segments and
  clips ua/ub to [0, 1], so any horizontal-vertical pair within the
  extended segments produces an intersection regardless of whether
  there's a real visual line crossing at that pixel.

## Solution

The clustering algorithm is fine. The intersection set is the problem.
There are three viable fixes; (A) is the cleanest:

### A. Filter intersections by Canny edge presence (recommended)

After computing the intersection set, sample a small neighbourhood
(e.g. 3x3 or 5x5) around each intersection in the original Canny edge
image. Discard any intersection where edge density in the neighbourhood
falls below a threshold (e.g. <2 edge pixels in a 5x5 window). This
keeps only intersections where the lines actually cross visually.
Implementation cost: pass the Canny edge image through to the
clustering step; ~30 lines of Rust.

### B. Cluster lines first, intersect within-cluster

Group lines into per-instance subsets BEFORE intersecting. Two lines
belong to the same subset if they share orientation (within a small
delta) AND their perpendicular distance is below some threshold AND
they overlap in their parallel direction. Then for each subset,
compute intersections between its horizontals and verticals.
Implementation cost: more invasive, requires reasoning about line
geometry; ~80 lines.

### C. Use connected-component analysis on the edge image directly

Skip Hough entirely for the LOCALISATION step. Run flood-fill on the
Canny edge image; each large connected component is a candidate
instance. Bounding box of each component = candidate region. Use
Hough only on each cropped region for fine-grained corner extraction.
Implementation cost: replaces the whole pipeline; semantically
different.

### Adjacent insight: quad area for largest-pick

If your corner-extraction step uses the standard "min/max of x+y and
x-y" trick to find the four corners of a quad, the returned order is
typically `[TL, BL, TR, BR]`. That is a SELF-CROSSING path (top-left
to bottom-left, then to top-right diagonally crossing the polygon,
then to bottom-right). Shoelace area on this point ordering returns
0 for axis-aligned rectangles, so `largest_candidate` picks
arbitrarily. Use bounding-rectangle area instead:

```rust
fn bbox_area(corners: &[(f64, f64); 4]) -> f64 {
    let xs: [f64; 4] = corners.map(|p| p.0);
    let ys: [f64; 4] = corners.map(|p| p.1);
    let min_x = xs.iter().cloned().fold(f64::INFINITY, f64::min);
    let max_x = xs.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let min_y = ys.iter().cloned().fold(f64::INFINITY, f64::min);
    let max_y = ys.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    (max_x - min_x).max(0.0) * (max_y - min_y).max(0.0)
}
```

Bbox area also tends to match the user's mental model of "biggest"
better than polygon area for slight-perspective-distorted boards.

## Verification

The failure is verified by composing two grids of different sizes onto
one canvas and running the end-to-end pipeline. With the naive
intersection-clustering approach:

- Result: `Some((board, bbox))` is returned but `bbox.x` is at the
  left edge of the image (= the smaller left grid OR the merged
  super-cluster spanning both).
- Expected: `bbox.x` should land in the right half of the image
  (where the larger grid is).

**Fix (A) implemented and verified in pawn-au-chocolat 2026-05-15**:
the source project shipped `filter_intersections_to_edges` in
`src-tauri/src/image_detection/board_detector.rs`. Empirically
verified against a real chess.com window screenshot
(3022x1738 capture with board on left half + sidebars):

- Pre-fix: bbox spanned the whole window, FEN garbage (3 white +
  10 black pieces from a clean 16+16 starting position), confidence
  55%, "could not auto-detect" banner shown.
- Post-fix: bbox `(480, 70, 1413, 1663)` lands squarely on the
  board region, sidebar UI no longer pollutes the cluster.

Test fixture and assertion live at
`src-tauri/src/image_detection/real_screenshots.rs::chesscom_starting_position_window_auto_detect_picks_only_the_board`.

**Implementation gotcha (Sobel, not Canny)**: imageproc 0.26's
`canny` has a hysteresis-BFS underflow bug
(`edges.rs:135` computes `nx - 1, ny - 1` on `u32` without bounds
checks; if the BFS walks unbroken to column 0 / row 0 the panic
fires with index `(4294967295, 1)`). Synthetic test fixtures with
uniform backgrounds and sharp checkerboards reliably trigger this
because their gradients form a connected path to the canvas
boundary. Real screenshots have JPEG noise that breaks that
connectivity, so the existing line-detection canny path is fine
in production - but using canny for the EDGE-MASK helper means
running canny on every input including weird ones. Use Sobel +
fixed threshold for the membership-check mask:

```rust
fn compute_edge_mask(gray: &GrayImage) -> GrayImage {
    let gradient_threshold: u16 = 80;
    let sobel = imageproc::gradients::sobel_gradient_map(gray, |g| {
        image::Luma([if g[0] >= gradient_threshold { 255u16 } else { 0 }])
    });
    let mut out = GrayImage::new(sobel.width(), sobel.height());
    for (x, y, p) in sobel.enumerate_pixels() {
        out.put_pixel(x, y, Luma([p[0].min(255) as u8]));
    }
    out
}
```

Sobel doesn't have the BFS underflow. The threshold is a tuning
parameter (80 worked for chess UI; raise for noisy inputs).

## Example

Pawn au Chocolat (Tauri chess analysis app), branch
`feat/live-auto-board-detection`, file
`src-tauri/src/image_detection/board_detector.rs`.

```rust
// Test that exposes the failure (currently #[ignore]'d):
#[test]
#[ignore]
fn detect_largest_board_picks_the_larger_of_two_grids() {
    let mut canvas: RgbImage =
        ImageBuffer::from_pixel(1400, 700, Rgb([160u8, 160, 160]));
    paint_checkerboard(&mut canvas, 50, 270, 20);    // small left grid (160px)
    paint_checkerboard(&mut canvas, 700, 110, 60);   // big right grid (480px)

    let png = encode_png(&canvas);
    let result = detect_largest_board(&png).expect("locator must not error");
    let (_, bbox) = result.expect("should locate at least one board");

    // Currently FAILS with bbox.x = 0 (smaller left grid OR merged cluster).
    // Should pass after Canny-edge-mask intersection filtering.
    assert!(bbox.x >= 500, "expected the bigger right-hand grid; got bbox.x = {}", bbox.x);
}
```

```rust
// The naive clustering (works on synthetic input, fails on real images):
pub fn find_board_candidates(
    intersections: &[(f64, f64)],
    image_w: u32,
    image_h: u32,
) -> Vec<[(f64, f64); 4]> {
    let max_dim = image_w.max(image_h) as f64;
    let eps = (max_dim / 16.0).max(20.0);
    let clusters = connected_components(intersections, eps);
    clusters
        .into_iter()
        .filter(|cluster| cluster.len() >= MIN_INTERSECTIONS_PER_BOARD)
        .filter_map(|cluster| {
            let points: Vec<(f64, f64)> =
                cluster.iter().map(|&i| intersections[i]).collect();
            find_board_corners(&points)
        })
        .collect()
}
```

## Notes

- The pattern generalises well beyond chess. Multi-document layout
  detection, multi-table OCR, multi-receipt scanning, and any "find all
  instances of grid-aligned pattern X" pipeline that reaches for Hough
  voting hits the same trap.
- The eps-tuning rabbit hole is a red herring: no eps value separates
  per-instance intersections from the spurious cross-instance ones,
  because the spurious points are spatially interspersed with the
  real ones (they fall on grid B's vertical lines at grid A's horizontal
  ys, which is a perfectly grid-shaped pattern of points).
- The fix needs to filter the INTERSECTION SET against the EDGE IMAGE
  (or equivalently, the original greyscale gradient). The clustering
  algorithm itself does not need to change.
- If your single-instance use case is the dominant case (typical chess
  UI shows one board with surrounding chrome, not multi-board), you can
  ship the naive clustering and document the multi-instance limitation;
  the rare multi-instance case is usually addressable via a manual
  fallback in the user UI.
- The shoelace-on-self-crossing-path quirk for `bbox_area` vs polygon
  area is independent of the main issue and applies any time you derive
  4 corners via min/max of x+y and x-y extrema. The point order is
  `[(min_sum), (min_diff), (max_diff), (max_sum)] = [TL, BL, TR, BR]`
  which is geometrically a "Z" path, not a rectangle perimeter.

## References

- imageproc Hough line detection: <https://docs.rs/imageproc/latest/imageproc/hough/fn.detect_lines.html>
- Polar-to-cartesian conversion in OpenCV (same trap):
  <https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html>
- Connected-components in OpenCV (alternative localisation approach C):
  <https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html#ga107a78bf7cd25dec05fb4dfc5c9e765f>
