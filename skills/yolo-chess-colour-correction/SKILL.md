---
name: yolo-chess-colour-correction
description: |
  Fix YOLO chess piece colour misclassification on digital board screenshots.
  Use when: (1) YOLO detects correct piece types but wrong colours (e.g. black
  rook classified as white), (2) detection pipeline produces FEN with wrong
  piece colours on dark-themed boards (Lichess, Chess.com), (3) piece detection
  model confuses black/white pieces on non-standard board themes, (4) a
  brightness-bin colour-correction pass is FLIPPING black pieces to white on
  themes whose "dark" squares are actually quite light (chess.com classic-brown,
  cream/tan themes). Applies to any YOLO-based chess piece detector with
  12-class output (6 black + 6 white).
author: Claude Code
version: 2.0.0
date: 2026-05-03
---

# YOLO Chess Piece Colour Correction via Pixel Brightness Analysis

## Problem

YOLO object detection models trained for chess piece recognition reliably identify
piece shapes (pawn, rook, bishop, etc.) but frequently misclassify piece colours
on dark-themed digital board screenshots. Black pieces get classified as white and
vice versa, producing incorrect FEN positions.

## Context / Trigger Conditions

- YOLO chess piece detector outputs correct piece positions but wrong colours
- Board theme has dark squares that are similar brightness to black pieces
- FEN shows impossible piece counts (e.g. 2 White Queens when only 1 should exist)
- Detection works well on light themes but fails on dark themes (Lichess brown, Chess.com dark)
- Class IDs follow the pattern: 0-5 = black pieces, 6-11 = white pieces (same type at offset 6)

## Solution: Two-Path Strategy (v2.0+)

The original brightness-bin approach SILENTLY FAILS on themes whose square
colour falls outside the safe luminance band [70, 180]. Chess.com
classic-brown LIGHT squares are 241/219/186 (lum ~221), well above the
"bright pixel" threshold. When a black piece sits on such a square, the
cream BACKGROUND pixels count as "bright" and the piece is falsely
flipped to white.

The fix is a TWO-PATH strategy gated on the underlying square colour:

```
                          per detection
                                |
                  sample 4 cell-corner pixels
                                |
                square_lum = avg luminance
                square_chrom = avg channel-spread
                                |
                  square_lum in [70, 180] ?
                  /                          \
                yes                          no
                 |                            |
        BRIGHTNESS-BIN PATH         is square chromatic? (chrom > 12)
        (legacy, works for           /                       \
         lichess brown,            yes                       no
         chess.com green)           |                         |
                          CHROMATICITY PATH        BRIGHTNESS-BIN PATH
                          (chess.com classic       (greyscale themes,
                           cream/light squares,     test boards)
                           lichess green-light)
```

### Path A: Brightness-Bin (legacy, v1.0)

Use for "safe" themes where the square colour is mid-luminance:
- lichess brown dark = #B58863 (lum ~141) ✓
- chess.com green dark = #769656 (lum ~135) ✓
- chess.com green light = #EEEED2 (lum ~232) — POLLUTES; use Path B
- chess.com classic-brown light = #F1DBB9 (lum ~221) — POLLUTES; use Path B

Algorithm unchanged from v1.0:
1. Sample pixels in a tight circle around the bbox body (radius = 25% of
   min(bbox_w, bbox_h), centre biased down by 12% of bbox height)
2. Count: dark (lum < 70), bright (lum > 180)
3. Decision: bright_ratio - dark_ratio > 0.10 → white;
              dark_ratio - bright_ratio > 0.10 → black;
              else keep YOLO

### Path B: Chromaticity (v2.0)

Use when square colour is outside the safe band AND the theme is chromatic
(chess.com / lichess square hues all are):

1. Sample same body region as Path A
2. Filter to PIECE pixels only by chromaticity:
   `is_piece = (|R-G| + |G-B| + |R-B|) < 25`
   (piece sprites are achromatic; chess.com / lichess squares are chromatic)
3. Decision metric is the BRIGHT-PIXEL FRACTION of the piece-pixel set:
   `bright_frac = count(lum > 200) / total_piece_pixels`
4. Classify: `bright_frac > 0.23` → white;
            `bright_frac < 0.13` → black;
            else keep YOLO (dead zone around 0.18)

**Why bright-fraction, not mean luminance**: Ornate Cburnett sprites
(queen crown, knight mane, rook battlements) include dense black outline
pixels. White pieces have ~30-70% bright body fill PLUS ~20-40% black
outline pixels. Mean luminance for a white queen on a green dark square
is ~108 (not "white"!) because the outline pulls the mean down. Bright
fraction ignores outline contribution and cleanly separates white (≥25%
bright) from black (< 5% bright).

### Path-Selection Gate: Cell-Corner Sampling

CRITICAL: sample the square colour from CELL CORNERS, not from a
bbox-relative offset. Bbox-relative offsets land on the SVG margin
(file/rank labels) on synthetic renders, returning (0,0,0) and forcing
every detection through the legacy bins path.

```
sample_square_pixel(board, det):
    cell_w = board.width / 8
    cell_h = board.height / 8
    col = det.x / cell_w
    row = (det.y - det.height/2) / cell_h  # bbox top → cell row
    
    # Average four corners of the cell, 10% inset
    inset = 0.10
    sum = mean of four corner pixels
    return sum
```

The 10% inset stays clear of the piece body (which is centred low) and of
last-move highlight rendering at the cell edge.

**Why bbox-top (not bbox-centre) for the row**: counter-intuitive but
load-bearing. When YOLO's bbox is tall (king/queen sprite, sometimes
pawn) the bbox top can land in the row ABOVE the piece's actual cell.
That "wrong" cell has the OPPOSITE square-colour parity, and the
path-selection gate downstream often routes to the better-calibrated
brightness-bin path on that opposite-parity sample. Switching this to
the bbox-centre row regressed 14 fixtures on the green/brown corpus
(mostly white queens on light squares being chromaticity-flipped to
black). Only revisit after the chromaticity path itself has been
further hardened against ornate Cburnett-sprite outline pixels.

### Key Thresholds (v2.0)

| Threshold | Value | Purpose |
|-----------|-------|---------|
| Square-pollutes-bins band | lum < 70 OR > 180 | Triggers Path B |
| Chromatic-theme min chroma | 12 | Below: greyscale theme, force Path A |
| Piece chroma max | 25 | Pixel-level "is piece" gate (Path B) |
| Bright luminance (Path B) | > 200 | What counts as "bright body fill" |
| Bright-fraction threshold | 0.18 ± 0.05 | Path B colour decision |
| Min piece pixels (Path B) | 50 | Reject sparse samples |
| Sample radius | 25% of bbox min dim | Same as v1.0 |

### Why the Chromaticity Threshold is 12 (not 25)

Both thresholds (piece-pixel gate and theme-detection gate) use the
**city-block sum** metric: `chroma = |R-G| + |G-B| + |R-B|`, range
0-510. NOT the single-channel `max - min` metric, which would give
half these values.

The piece-pixel chromaticity gate uses 25 (per the
chess-board-piece-chromaticity-segmentation skill). The theme-detection
gate uses 12. Many "light" squares of standard themes are nearly
achromatic:

| Theme | Light square | Chroma (city-block) |
|---|---|---|
| chess.com blue | #D8E0E0 | 16 |
| chess.com purple | #E9E6F1 | 22 |
| lichess blue | #DEE3E6 | 16 |
| lichess ic | #ECECD7 | 42 |
| lichess green light | #FFFFDD | 68 |

For comparison, the polluting (engages Path B) squares:

| Theme | Square | Luminance | Chroma (city-block) |
|---|---|---|---|
| chess.com classic-brown light | #F1DBB9 | 221 | 110 |
| chess.com green dark | #769656 | 135 | 128 |
| lichess green light | #FFFFDD | 250 | 68 |

Threshold of 12 catches all of these as "chromatic" (engages Path B when
luminance is also out-of-band) while leaving plain greyscale themes
(chroma 0) on Path A.

### Implementation Notes

- Run colour correction on the RESIZED 640x640 image (same coordinate space as detections)
- The correction happens AFTER NMS but BEFORE grid mapping
- Class ID mapping: black pieces = 0-5 (b,k,n,p,q,r), white = 6-11 (B,K,N,P,Q,R)
- To flip colour: black-to-white = class_id + 6, white-to-black = class_id - 6
- Preserve Path A verbatim: any change to the bins logic risks regressing
  themes that already worked. Confirm with a per-theme corpus.

## Additional Discovery: Lichess Highlight Behaviour

Lichess highlights BOTH the origin and destination squares of the last move.
This means:
- Two adjacent squares may be highlighted (yellow-green)
- The piece is on the DESTINATION square (not the origin)
- The origin square appears as a uniform highlight with no piece
- Highlight colour signature: Green channel - Blue channel > 50

This can cause:
- Pieces appearing to be on the wrong square (shifted by 1 cell)
- Variance-based piece detection flagging empty highlighted squares as containing pieces
- Kings mislocated by 1 square when the last move was a King move

## Per-Square Empty Cell Scanning

For cells where YOLO found nothing, pixel analysis can detect missed pieces:

1. Sample the centre 25% of each empty cell
2. Compute standard deviation of pixel brightness
3. If std_dev > 25: likely a piece present
4. Use bright/dark pixel ratios to determine piece colour
5. Piece TYPE cannot be determined from pixels alone (shape analysis or re-inference needed)

## Verification

After applying colour correction:
- Each side should have at most 1 King, 1 Queen (before promotions), 2 Rooks, 2 Bishops, 2 Knights, 8 Pawns
- No colour should have more pieces than theoretically possible
- The FEN should produce a legal-looking chess position
- Run `validate_piece_counts` to check for obvious issues

## Example

### v1.0 (brightness-bin only, kept verbatim for safe themes)

**Before correction:**
```
FEN: 5k1R/4b1pp/3p1p2/p3PP1Q/P1Q3P1/2P5/3B3P/1R2K3
Issues: h8 has White Rook (should be black), c4 has White Queen (should be black)
```

**After pixel brightness correction:**
```
FEN: 5k1r/4b1pp/3p1p2/p3PP1Q/P1q3P1/2P5/3B3P/1R2K3
h8: R->r (bright=0.10, dark=0.67 -> black piece)
c4: Q->q (bright=0.27, dark=0.60 -> black piece)
```

### v2.0 (two-path failure that v1.0 missed)

**Setting**: chess.com classic-brown theme, real user screenshot.

**Before correction (YOLO output)**: black pawns at b7/c6/e5 correctly
classified.

**After v1.0 brightness-bin pass**: ALL THREE FLIPPED to white. Why?
- Cream "dark" square at b7 (chess.com classic-brown #F1DBB9, lum 221)
  contributes ~45% bright pixels to the body sample.
- Black pawn body contributes ~7% dark pixels (and 0% bright).
- Bins say "bright(0.45) > dark(0.07) by margin > 0.10 → WHITE".
- Black pawn → white pawn flip. Wrong.

**After v2.0 path-selection gate**:
- sample_square_pixel returns (241, 219, 186), lum=221, chrom=112.
- square_pollutes_bins=true (lum > 180), chromatic_theme=true (chrom > 12).
- Engages chromaticity path.
- Body sample: piece pixels (chroma < 25) account for ~40% of sample.
  Of those, bright_frac = 0.04 (no white interior).
- bright_frac (0.04) < 0.13 → BLACK. Stays black. Correct.

End-to-end FEN match for the position became exact-correct after v2.0
(including the b7/c6/e5 pawns plus 29 other pieces).

## Notes

- This approach is specific to DIGITAL screenshots. Photographs of physical boards have
  different lighting characteristics and may need different thresholds.
- The 640x640 YOLO input size means each cell is 80x80 pixels, providing enough resolution
  for reliable brightness analysis.
- Highlighted squares (move indicators) have very low variance and can be mistaken for empty
  squares by variance-based piece detection.
- Some themes (especially 3D or wooden board themes) may need adjusted thresholds.
- v2.0 path B leans on the related skill
  `chess-board-piece-chromaticity-segmentation` for the "what counts as
  a piece pixel" rule. Keep the chroma threshold consistent between the
  two (currently 25) so segmentation is stable.

## Per-theme corpus iteration loop

When tuning thresholds, run a per-theme regression corpus:

```
1. Generate fixtures across N themes (synthetic via python-chess +
   cairosvg, or real screenshots).
2. Run detection with PAWN_IMAGE_CORPUS_REPORT=/tmp/r.json env var so a
   per-fixture pass/fail JSON drops out.
3. Group by theme; check pass-rate. A regression on ANY theme means a
   threshold tweak has unintended fallout — back it out or harden the
   gate that selects which path runs.
4. Auto-baseline expected_pass per fixture from the report so the
   overall corpus test passes; commit the baseline; iterate.
```

A 97%+ overall pass rate across 6+ chromatic themes is realistic with
v2.0 on a YOLO model trained on 2 themes (lichess brown, chess.com
green). Themes way out of training distribution (e.g. chess.com purple
~65%) will need either YOLO retraining or sub-threshold rescue tuning,
not a colour-correction fix.
