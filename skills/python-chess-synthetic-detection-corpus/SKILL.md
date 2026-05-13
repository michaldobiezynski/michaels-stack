---
name: python-chess-synthetic-detection-corpus
description: |
  Generate synthetic chess-board PNG fixtures for ML chess-detection pipeline
  testing using python-chess + cairosvg. Use when: (1) building an image-level
  regression corpus for a YOLO/CNN chess detector, (2) needing Lichess-parity
  board renders without downloading piece SVGs from lila, (3) testing detector
  robustness across board themes (lichess-brown, chess.com-green), (4) needing
  programmatic orientation flipping (white-bottom vs black-bottom) for
  orientation-vote test coverage. Covers the key non-obvious fact that
  python-chess's built-in SVG piece set IS cburnett (Lichess default), plus
  the exact colors-dict schema and cairosvg macOS native deps.
author: Claude Code
version: 1.0.0
date: 2026-04-24
---

# Synthetic chess-board detection corpus via python-chess + cairosvg

## Problem

You're building an ML chess-piece detector (YOLO, CNN, etc.) and want an
image-level regression corpus: hand-curated FENs rendered as PNG screenshots,
checked into the repo, run through the detection pipeline, asserting that
detected placement matches ground truth. Fixtures must be rendered
Lichess-style (because that's the detector's training distribution) across
multiple themes and orientations.

The naive path is heavy: download lila's `cburnett` piece SVGs, reimplement a
board compositor, handle theming. The light path — python-chess — is not
well-signposted in its docs and has several colour-key quirks.

## Context / Trigger Conditions

Use this pattern when:
- The detector was trained on or is routinely run against Lichess boards
  (cburnett piece set).
- You need per-theme renders (Lichess brown, Chess.com green, custom palettes).
- You need both orientations (white-at-bottom AND black-at-bottom) to exercise
  the detector's orientation vote.
- Fixtures should be checked in (rendered once, never regenerated at test
  time) to avoid a runtime Python/Cairo dependency on CI.

Do NOT use this pattern when the detector is specifically tuned to
Chess.com's "neo" / "alpha" / "wood" piece sets. The cburnett default will
not match those.

## Solution

### 1. Install

```bash
python3 -m venv .venv-corpus
.venv-corpus/bin/pip install chess cairosvg
```

On macOS, cairosvg also needs native libraries. If `cairosvg.svg2png(...)`
fails at import with an OSError about libcairo or no such file, run:

```bash
brew install cairo pango gdk-pixbuf libffi
```

### 2. Render one board

```python
import chess
import chess.svg
import cairosvg

PLACEMENT = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

# python-chess wants full FEN. Side-to-move, castling, EP don't affect
# rendering, so pad with defaults.
board = chess.Board(fen=f"{PLACEMENT} w KQkq - 0 1", chess960=False)

colors = {
    "square light": "#f0d9b5",   # Lichess brown light
    "square dark":  "#b58863",   # Lichess brown dark
    "margin":       "#ffffff",   # board margin (where rank/file labels sit)
    "coord":        "#000000",   # coordinate text colour
    # Make arrow overlays transparent in case any get drawn:
    "arrow green":  "#00000000",
    "arrow red":    "#00000000",
    "arrow yellow": "#00000000",
    "arrow blue":   "#00000000",
}

# flipped=True renders from black's perspective (black pieces at bottom,
# rank 1 at top, files reversed). Crucial for orientation-vote coverage.
svg = chess.svg.board(
    board,
    flipped=False,
    colors=colors,
    size=400,
    coordinates=True,
)

cairosvg.svg2png(
    bytestring=svg.encode("utf-8"),
    output_width=400,
    output_height=400,
    write_to="start.png",
)
```

### 3. Common theme palettes

```python
THEMES = {
    "brown":   {"light": "#f0d9b5", "dark": "#b58863"},  # Lichess brown
    "blue":    {"light": "#dee3e6", "dark": "#8ca2ad"},  # Lichess blue
    "green":   {"light": "#eeeed2", "dark": "#769656"},  # Chess.com green
    "ic":      {"light": "#eceece", "dark": "#8b7666"},  # Lichess "ic"
    "wood":    {"light": "#d18b47", "dark": "#ffce9e"},
}
```

### 4. Orient-flipped (black-bottom) render

`flipped=True` in `chess.svg.board(...)` is the only change. The FEN of the
position does NOT change — you still pass the canonical white-at-top
placement. The renderer rotates the visual 180 degrees.

This is what the detection pipeline should see when a user screenshots a
Lichess game while playing black: piece positions appear mirrored, but the
"truth" FEN is still canonical. A good detector's orientation vote flips
the grid internally so its output matches the same expected placement as
the white-bottom render.

## Verification

- Produced PNG is 400×400 RGBA, cburnett-style pieces, correct theme.
- Piece placement visually matches the FEN you passed.
- `flipped=True` render has black pieces at the image bottom and rank labels
  running 1 (top) → 8 (bottom) with files reversed (h left, a right).

## Example: full corpus generator skeleton

```python
#!/usr/bin/env python3
"""Render a committed regression corpus."""
from pathlib import Path
import json
import chess
import chess.svg
import cairosvg

OUT = Path("tests/fixtures/synthetic")
POSITIONS = [
    ("starting", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("e4-e5",    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR"),
    # ...
]
THEMES = {
    "brown": {"light": "#f0d9b5", "dark": "#b58863"},
    "green": {"light": "#eeeed2", "dark": "#769656"},
}

def render(placement, theme, flipped, out_path, size=400):
    board = chess.Board(fen=f"{placement} w KQkq - 0 1", chess960=False)
    colors = {
        "square light": theme["light"],
        "square dark":  theme["dark"],
        "margin":       "#ffffff",
        "coord":        "#000000",
        "arrow green":  "#00000000",
        "arrow red":    "#00000000",
        "arrow yellow": "#00000000",
        "arrow blue":   "#00000000",
    }
    svg = chess.svg.board(board, flipped=flipped, colors=colors, size=size)
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=size, output_height=size,
        write_to=str(out_path),
    )

OUT.mkdir(parents=True, exist_ok=True)
fixtures = []
for slug, placement in POSITIONS:
    for theme_name, theme in THEMES.items():
        for orient_name, flipped in [("white_bottom", False), ("black_bottom", True)]:
            file_slug = f"{slug}__{theme_name}__{orient_name}"
            render(placement, theme, flipped, OUT / f"{file_slug}.png")
            fixtures.append({
                "slug": file_slug,
                "file": f"{file_slug}.png",
                "expected_placement": placement,
                "theme": theme_name,
                "orientation": orient_name,
                "expected_pass": True,  # flip after triage run
            })

(OUT / "manifest.json").write_text(json.dumps(
    {"schema_version": 1, "fixtures": fixtures}, indent=2))
```

## Notes

- **cburnett parity**: python-chess's built-in SVG pieces ARE cburnett —
  the same piece set Lichess ships as its default. So python-chess renders
  are naturally high-parity with real Lichess boards, even though
  python-chess never calls itself "cburnett" in its docs. This is the key
  reason to prefer it over writing a custom renderer or downloading lila's
  SVGs separately.
- **Don't hand-edit the colors dict keys**: they're literal strings with
  spaces. `"square light"` is valid; `"square_light"` is silently ignored
  and python-chess falls back to defaults.
- **Side-to-move and castling don't affect rendering**: pad the FEN with
  `" w KQkq - 0 1"` and move on.
- **Fixtures should be committed, not regenerated on CI**: this avoids
  imposing a Python + Cairo dependency on CI runners. Regenerate only when
  adding positions or changing themes.
- **Check-in size is modest**: at 400×400 RGBA, a typical board PNG is
  ~30-50 KB. A 70-fixture corpus is under 3 MB.
- **Runtime budget for detection tests**: ONNX Runtime session init via
  `ort 2.0.0-rc.12` is roughly 500-700 ms per inference (uncached). A
  70-fixture corpus takes ~50 s on a single CPU; plan accordingly.
- **Orientation assert subset**: if your detector has a separate
  orientation-vote layer, only a small subset of fixtures needs
  black-bottom coverage — picking positions with unambiguous king
  placements (starting position, castled middlegames, clear endgames) is
  sufficient.

## References

- [python-chess docs — chess.svg](https://python-chess.readthedocs.io/en/latest/svg.html)
- [cairosvg docs](https://cairosvg.org/documentation/)
- [Lichess piece sets (cburnett is the default)](https://github.com/lichess-org/lila/tree/master/public/piece)
- Related skills: `chess-detection-placement-only-fen` (how the detector
  exposes placement-only FEN), `yolo-chess-colour-correction` (failure
  modes that this corpus surfaces),
  `detection-greedy-legality-repair-by-confidence-demotion` (ratchet
  discipline for tracking known-fail cases).
