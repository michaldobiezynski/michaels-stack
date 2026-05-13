---
name: chess-board-piece-chromaticity-segmentation
description: |
  Robust way to segment chess pieces from squares in a screenshot cell crop,
  without per-piece-colour and per-square-colour thresholds. Exploits the fact
  that on major chess sites (Chess.com green, Lichess brown, Chess.com brown,
  Chess.com blue, etc.) the squares are CHROMATIC (R, G, B channels unequal)
  while the piece sprites are ACHROMATIC (white, grey, or black -- R≈G≈B).
  Marking low-chroma pixels as foreground produces a clean piece silhouette.
  Use when: (1) grayscale / Otsu thresholding collapses on "white piece on
  light square" because the piece and square are nearly isoluminant,
  (2) fixed RGB-distance thresholds work on dark squares but not light ones
  (or vice-versa), (3) you need a piece mask that works uniformly across light
  and dark squares and across white and black pieces, (4) building any chess
  detection / classification post-processing that needs a piece-foreground
  mask from a cell crop on a recognised theme.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Chromaticity-based piece segmentation for chess screenshots

## Problem

You have a chess-board cell crop (RGB) and need a binary mask of "piece
pixels vs square pixels". Obvious approaches fail:

1. **Grayscale + Otsu / fixed threshold**: collapses on "white piece on light
   square" (e.g. Chess.com green light = `#EEEED2`, luminance ~235; white
   piece luminance ~240-255). Otsu picks a threshold that either marks
   essentially the whole cell as foreground (`fg_frac ≈ 0.87`) or essentially
   none of it.
2. **RGB distance from expected square colour** with a fixed threshold: has to
   trade off between dark squares (piece-to-square distance ~240) and light
   squares (piece-to-square distance ~50), so one threshold can't serve both.
3. **Per-case thresholding** (white-on-light, white-on-dark, black-on-light,
   black-on-dark) works but requires four hand-tuned thresholds and knowledge
   of both piece colour and square parity.

## Context / Trigger Conditions

- You're building a chess screenshot detector / classifier that needs a
  per-cell foreground mask.
- The board is on a RECOGNISED chromatic theme: Chess.com (green, brown,
  blue, purple), Lichess (brown, blue, green), etc. **NOT** a grey or
  monochrome theme.
- You observe:
  - `fg_frac` wildly different between light-square cells and dark-square
    cells for the same piece colour.
  - Otsu-based binarisation producing almost-all-foreground or almost-all-
    background masks on certain squares.
  - Piece-colour + square-colour interactions (4 separate regimes) make
    any single grayscale threshold fragile.

## Solution

Gate on "recognised chromatic theme" (so you know the squares are chromatic),
then binarise by **chromaticity**: a pixel is piece-foreground iff its RGB
channels are nearly equal.

```rust
fn binarise_by_chromaticity(crop: &RgbImage) -> GrayImage {
    // Colour-channel spread <= 25 counts as achromatic (piece).
    // Real chess.com / lichess squares have chroma > 50.
    const CHROMA_THRESHOLD: i32 = 25;
    let mut out = GrayImage::new(crop.width(), crop.height());
    for (x, y, rgb) in crop.enumerate_pixels() {
        let r = rgb[0] as i32;
        let g = rgb[1] as i32;
        let b = rgb[2] as i32;
        let chroma = (r - g).abs() + (g - b).abs() + (r - b).abs();
        let fg = chroma < CHROMA_THRESHOLD;
        out.put_pixel(x, y, image::Luma([if fg { 255 } else { 0 }]));
    }
    out
}
```

Properties:
- **Theme-agnostic** within the "chromatic squares" gate: works on green,
  brown, blue board themes without retuning.
- **Piece-colour-agnostic**: white pieces (255,255,255) and black pieces
  (0,0,0) are both achromatic, both register as foreground.
- **Square-colour-agnostic**: light and dark squares on the same theme are
  both chromatic (the square colour is the same hue at different lightness);
  both register as background.
- **Anti-aliasing-robust**: blended edge pixels (piece half-blended with
  square) become chromatic (pick up some of the square's hue) and fall on
  the background side. This tightens the mask around the solid piece
  interior rather than inflating it with a halo.

Guard it with theme detection so the method stays safe on unknown themes:

```rust
if let Some(theme) = detect_theme(board) {
    // proceed with chromaticity segmentation — safe on known chromatic themes
} else {
    // graceful no-op: unknown theme might be grey/monochrome; bail out
}
```

## Verification

Sample `fg_frac` (foreground pixel fraction) across the four colour regimes:

| piece | square | grayscale + Otsu | chromaticity |
|-------|--------|------------------|--------------|
| white | light  | ~0.87 (collapse) | ~0.35-0.45   |
| white | dark   | ~0.25            | ~0.35-0.45   |
| black | light  | ~0.30            | ~0.35-0.45   |
| black | dark   | ~0.45            | ~0.35-0.45   |

Chromaticity keeps `fg_frac` in a narrow, predictable band regardless of the
piece / square pair. That consistency is what downstream matching / scoring
depends on.

## Example

On `/tmp/chess_original_2.png` (Chess.com green with a white piece at c8,
YOLO mislabelled as bishop):

- Grayscale + Otsu: `fg_frac = 0.868` — threshold-trust-band gate rejects
  the probe, no flip attempted.
- Chromaticity: `fg_frac = 0.396` — well inside a `[0.03, 0.50]` trust band,
  match proceeds with a clean piece silhouette.

## Notes

- Use a threshold around 25 for channel-spread sum. Real squares on the
  recognised themes sit at 50-130 chroma; pure piece pixels at 0. A 25
  threshold cleanly separates them and rejects anti-aliased edges.
- **Do not apply to grey themes.** Chess.com and other sites support grey
  board themes where squares are achromatic. On those themes, pieces and
  squares are both achromatic, and chromaticity segmentation fails. The
  recognised-theme gate prevents this: list only chromatic themes in the
  table.
- Extend the theme table carefully: for every new theme added, confirm the
  light AND dark square medians have chroma well above the threshold.
- For pieces with coloured accents (rare custom piece themes) some accent
  pixels may drop out of the mask. For the standard piece sets on
  Chess.com / Lichess this isn't a practical issue.

## References

- [Colour theory: chroma and chromaticity](https://en.wikipedia.org/wiki/Chromaticity)
- No framework docs cover this specific trick — it's an applied observation
  from pawn-au-chocolat's chess screenshot pipeline.
