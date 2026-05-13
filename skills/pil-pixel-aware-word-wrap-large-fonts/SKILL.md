---
name: pil-pixel-aware-word-wrap-large-fonts
description: |
  Fix for text bleeding off the edge of a PIL-rendered canvas when using
  textwrap.wrap with large fonts (60pt+) or all-caps headlines. Use when:
  (1) leading or trailing characters of a wrapped line clip past the
  canvas edge, (2) you're rendering vertical Shorts hook frames, title
  cards, lower thirds, or end cards with PIL, (3) you call
  _draw_centred_line (or similar) which computes x = (W - line_width) // 2
  and the line is wider than W so x goes negative. The root cause is
  always the same: textwrap.wrap counts characters, but at 110pt all-caps
  black weight, 14 characters of W/M/K easily exceed 1080px even though
  "ililili" of the same length is half as wide. Fix: greedy word-wrap
  by font.getlength() pixel width, not character count.
author: Claude Code
version: 1.0.0
date: 2026-05-13
---

# Pixel-aware word wrap for large-font PIL canvases

## Problem

`textwrap.wrap(text, width=N)` wraps by character count. For monospace
fonts that works. For every other font, and especially for large or
all-caps text, character count is a bad proxy for pixel width because
glyphs vary: at 110pt all-caps black weight, "WORKPLACE?" is roughly
twice as wide as "ilililili?". You set a char limit that looks safe in
the IDE, ship it, and discover that some headlines bleed off the canvas
edge because the per-line pixel width exceeds the canvas width.

The bleed is silent in code (PIL happily draws past the canvas) and
visible only on rendered output - so it goes undetected until someone
watches the final video.

## Context / Trigger conditions

- You're rendering text onto a fixed-size PIL canvas (e.g. a 1080x1920
  vertical Short canvas, a 1920x1080 horizontal title card).
- You wrap text with `textwrap.wrap(text, width=N)` and pass each line
  through a centred drawer like:

      total = sum(font.getlength(t) for t in tokens) + spaces
      x = (canvas_w - int(total)) // 2

- The font is large (60pt+) or the text is force-uppercased (`.upper()`).
- Visual symptom: leading or trailing character of one or more lines
  is clipped at the canvas edge; the offending line tends to be the
  longest one in the wrap.

You will NOT hit this bug at 24pt mixed-case body text with the same
char limit. The bug surfaces specifically when glyph width-variance
times font size matters relative to the canvas width.

## Solution

Replace the char-based wrap with a greedy word-wrap that measures
actual pixel width via `font.getlength()`. Allow a side margin so the
text never touches the canvas edge.

```python
from PIL import ImageFont


def wrap_by_pixel_width(
    text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    """Greedy word-wrap by font pixel width, not character count.

    A single word wider than max_width is kept on its own line rather
    than dropped; the line will overhang but no content disappears.
    """
    words = text.split()
    if not words:
        return [text]
    space_w = font.getlength(" ")
    lines: list[str] = []
    cur: list[str] = []
    cur_w = 0.0
    for word in words:
        word_w = font.getlength(word)
        if not cur:
            cur = [word]
            cur_w = word_w
            continue
        tentative = cur_w + space_w + word_w
        if tentative <= max_width:
            cur.append(word)
            cur_w = tentative
        else:
            lines.append(" ".join(cur))
            cur = [word]
            cur_w = word_w
    if cur:
        lines.append(" ".join(cur))
    return lines
```

Use it in place of `textwrap.wrap`:

```python
# WRONG: character-count wrap, can overflow canvas
wrapped = textwrap.wrap(text, width=14)

# RIGHT: pixel-width wrap with side margin
SIDE_MARGIN = 90
font = ImageFont.truetype(font_path, 110)
wrapped = wrap_by_pixel_width(text, font, W - 2 * SIDE_MARGIN)
```

Pick the side margin so that even the widest legitimate line of text
has visible breathing room from the edge. 60-90px on a 1080px-wide
canvas is a sensible default for large headlines; narrow it for tighter
designs.

## Verification

Unit-test the wrap by measuring each output line:

```python
from PIL import ImageFont
font = ImageFont.truetype(font_path, 110)
max_w = W - 2 * SIDE_MARGIN
for line in wrap_by_pixel_width(text, font, max_w):
    w = int(font.getlength(line))
    assert w <= max_w, f"OVERFLOW {w}px > {max_w}px on line '{line}'"
```

Visually, render one PNG with a known-bad input (long all-caps line
with wide glyphs like W/M/K) and confirm no glyph touches the canvas
edge. The fix is correct iff every glyph of every line sits at least
`SIDE_MARGIN` pixels inside the canvas.

## Notes

- The bug is silent in code. There is no Pillow warning or error when
  text is drawn past the canvas edge. Detection requires either eyeball
  inspection of rendered output or an assertion as above.
- The fix does not auto-shrink the font for very long single words; if
  one word is wider than max_width on its own, the helper keeps it on
  one line and overhangs. That preserves content (worst case: that one
  word's edges clip), but for long headlines it's worth checking
  whether the LLM that produced the text should be told to keep tokens
  short.
- For a multi-line block, vertical position math should use the line
  count returned by the wrap helper, not the assumed line count from
  the char-based wrap. If you fix the wrap but leave the layout math
  pegged to a 3-line assumption, a 4-line wrap will overflow the
  bottom margin.
- Pillow's `font.getlength()` is the right tool for the per-line
  measurement and is more accurate than `font.getsize()[0]` for thin
  stroke fonts. `getsize()` returns the bbox of the WHOLE glyph
  including any side-bearing, which slightly overstates width.

## Related skills

- `shorts-hook-frame-headline-card` - the clipsmith hook frame is
  where this bug first surfaced. The skill is updated to use this
  pixel-aware wrap.
- `ffmpeg-burn-captions-without-libass-pil-overlay` - the broader
  context of rendering text via PIL onto a canvas to overlay with
  ffmpeg, which is where this kind of bug lives.

## References

- [Pillow ImageFont.getlength](https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.FreeTypeFont.getlength) -
  per-token width measurement.
- [textwrap docs](https://docs.python.org/3/library/textwrap.html) -
  notes that it operates on characters, not pixels. The docs do not
  warn about this failure mode but it's intrinsic to how the module
  works.
