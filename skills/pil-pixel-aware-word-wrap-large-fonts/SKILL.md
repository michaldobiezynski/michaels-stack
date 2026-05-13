---
name: pil-pixel-aware-word-wrap-large-fonts
description: |
  Fix for text bleeding off the edge of a PIL-rendered canvas when using
  textwrap.wrap with large fonts (60pt+) or all-caps headlines, AND the
  follow-up case where pixel-aware wrap alone still overflows because
  (a) too many wrapped lines exceed the canvas height, or (b) a single
  word is wider than the safe area on its own. Use when:
  (1) leading or trailing characters of a wrapped line clip past the
  canvas edge, (2) you're rendering vertical Shorts hook frames, title
  cards, lower thirds, or end cards with PIL, (3) you call
  _draw_centred_line (or similar) which computes x = (W - line_width) // 2
  and the line is wider than W so x goes negative, (4) the fallback text
  is too long and wraps to 10+ lines, bleeding off the top or bottom
  of the canvas, (5) a single long word (PROCRASTINATION, MANOSPHERE)
  is wider than max_text_w and overhangs even after pixel-aware wrap.
  The root fix is layered: (i) pixel-aware wrap via font.getlength()
  instead of textwrap.wrap, then (ii) auto-shrink the font until BOTH
  block height and widest line fit the canvas.
author: Claude Code
version: 1.1.0
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

### Step 2: auto-shrink the font for the two leftover cases

Pixel-aware wrap alone catches the common case (long phrase, wraps
across many lines, each line individually fits the width). It does
NOT catch:

- **Vertical overflow**: a long fallback string (e.g. a 20-word
  speaker's hook used because the LLM left the punchy headline field
  empty) wraps to 10+ lines and bleeds off the top and bottom of the
  canvas. The wrap helper produces correct per-line widths but the
  total block height exceeds H - 2*vert_margin.
- **Single oversized word**: a single token like `PROCRASTINATION`,
  `MANOSPHERE`, or `ENTREPRENEURSHIP` is wider than max_text_w on
  its own. `wrap_by_pixel_width` keeps it on its own line (better
  than dropping content) and lets it overhang the canvas. The wrap
  helper cannot fix this because there's nowhere to break it.

Both are fixed by an auto-shrink loop that tries the maximum font
size first and steps down until both dimensions fit:

```python
FONT_SIZE_MAX = 110
FONT_SIZE_MIN = 60
SIDE_MARGIN = 90
VERT_MARGIN = 160

max_text_w = W - 2 * SIDE_MARGIN
max_block_h = H - 2 * VERT_MARGIN

size = FONT_SIZE_MAX
while True:
    font = ImageFont.truetype(font_path, size)
    wrapped = wrap_by_pixel_width(text, font, max_text_w) or [text]
    ascent, descent = font.getmetrics()
    line_height = int((ascent + descent) * 1.05)
    block_h = line_height * len(wrapped)
    widest = max((font.getlength(L) for L in wrapped), default=0)
    fits_vert = block_h <= max_block_h
    fits_horiz = widest <= max_text_w  # catches the oversized-single-word case
    if (fits_vert and fits_horiz) or size <= FONT_SIZE_MIN:
        break
    size -= 10
```

Why a step-down loop instead of math: PIL fonts don't scale linearly
in width-at-a-given-text. A 110pt font that just barely overflows
might fit at 100pt or might still overflow at 90pt depending on which
glyphs the wrap helper kept on the widest line. A 10pt step finds the
largest size that fits, which is what you want for readability.

Also remember to **scale the stroke width with the font**, otherwise
shrunk text gets disproportionately heavy outlines:

```python
stroke_w = max(4, int(STROKE_WIDTH_MAX * size / FONT_SIZE_MAX))
```

### Step 3: prefer always-bounded fields in fallback chains

The auto-shrink is belt-and-braces. The cleaner fix is to AVOID
hitting it in the first place by ordering your fallback chain so the
always-bounded option comes BEFORE the maybe-unbounded one.

Example: a clip-rendering pipeline picks the hook text via
`preceding_question -> hook -> topic`. Intuitively the speaker's own
`hook` is "higher quality" than the topic label. But `hook` is a full
sentence (10-25 words); `topic` is constrained to <=6 words by the
prompt. So pick `topic` over `hook`:

```python
# WRONG: order by perceived quality
return preceding_question or hook or topic

# RIGHT: order by guarantee-of-fit, with auto-shrink as last resort
return preceding_question or topic or hook
```

The general principle: **in a fallback chain that feeds a fixed-size
canvas, order options by upper-bound on size, not by quality**. The
auto-shrink will save you when none of the bounded options exist,
but for the common case it's better to never need it.

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
