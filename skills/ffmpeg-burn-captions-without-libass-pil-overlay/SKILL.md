---
name: ffmpeg-burn-captions-without-libass-pil-overlay
description: |
  Burn subtitles/captions into video when ffmpeg lacks libass and
  libfreetype (so `subtitles=` and `drawtext` filters are unavailable).
  Use when:
  (1) ffmpeg's `drawtext` filter errors with "No such filter: 'drawtext'",
  (2) `subtitles=file.srt` errors with "Filter not found" or "No such filter",
  (3) you're on Homebrew's stock `ffmpeg` formula on macOS (configured
  without `--enable-libass` and `--enable-libfreetype`),
  (4) you want Shorts/TikTok-style large bold captions and need control
  over font, stroke, and positioning that subtitle filters don't give
  you anyway.
  Solves the problem by pre-rendering each caption as a transparent PNG
  with Pillow (PIL) and overlaying with ffmpeg's standard `overlay` filter
  using per-cue `enable='between(t,start,end)'` expressions. Includes the
  filter-graph-complexity guardrail (consolidate cues into <=14 chunks
  per clip, otherwise ffmpeg hangs on long overlay chains).
author: Claude Code
version: 1.0.0
date: 2026-05-10
---

# Burn captions into video without libass / libfreetype (PIL + overlay)

## Problem

You want captions burned into a video. The two standard ffmpeg approaches
don't work because:

- `drawtext=text='...'` requires ffmpeg built with `--enable-libfreetype`.
  Homebrew's stock `ffmpeg` formula does NOT include this. Error:
  `[AVFilterGraph] No such filter: 'drawtext'. Error opening output files: Filter not found.`
- `subtitles=file.srt` requires `--enable-libass`. Homebrew's stock formula
  also does NOT include this. Same kind of error.

You don't want to install `ffmpeg-full` or maintain a custom build, AND you
want full control over the caption look (large bold text, stroke, shadow,
custom position) which subtitle filters give you only crudely.

## Context / Trigger conditions

- macOS + Homebrew, default `ffmpeg` formula
- Need burned-in captions on processed video
- Source of caption text is a parsed VTT, SRT, or any list of
  `(start, end, text)` cues

## Solution

Pre-render each caption to a transparent PNG with Pillow, then add each
PNG as an extra `-i` input and overlay it with a per-cue `enable=` time
window. The standard `overlay` filter is in every ffmpeg build.

### Rendering a single caption PNG (Pillow)

```python
from PIL import Image, ImageDraw, ImageFont
import textwrap

FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"  # macOS
SIZE = 64
STROKE = 6
WRAP_CHARS = 22

def render_caption_png(text: str, out_path: str) -> None:
    wrapped = textwrap.fill(text, width=WRAP_CHARS)
    font = ImageFont.truetype(FONT, SIZE)
    # Measure including stroke
    dummy = Image.new("RGBA", (10, 10))
    d = ImageDraw.Draw(dummy)
    bbox = d.multiline_textbbox(
        (0, 0), wrapped, font=font, stroke_width=STROKE, align="center"
    )
    text_w = int(bbox[2] - bbox[0] + 2 * STROKE)
    text_h = int(bbox[3] - bbox[1] + 2 * STROKE)
    img = Image.new("RGBA", (max(1, text_w), max(1, text_h)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.multiline_text(
        (int(-bbox[0]) + STROKE, int(-bbox[1]) + STROKE),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=STROKE,
        stroke_fill=(0, 0, 0, 255),
        align="center",
    )
    img.save(out_path)
```

Critical PIL gotcha: `multiline_textbbox` returns floats when
`stroke_width` is set. Cast to `int` before passing to `Image.new` (which
takes integer dimensions) or you get
`'float' object cannot be interpreted as an integer`.

### Building the ffmpeg overlay graph

For each cue PNG, add an `-i` input and an `overlay` filter node:

```python
parts = ["[0:v]setpts=PTS-STARTPTS[base0]"]
last = "base0"
for i, (start, end, _png_path) in enumerate(cue_pngs):
    nxt = f"base{i+1}"
    input_idx = i + 1  # 0 is the source; PNGs start at 1
    parts.append(
        f";[{last}][{input_idx}:v]"
        f"overlay=enable='between(t,{start:.2f},{end:.2f})'"
        f":x=(W-w)/2:y=H-h-360"
        f"[{nxt}]"
    )
    last = nxt
parts.append(f";[{last}]format=yuv420p[outv]")
filter_complex = "".join(parts)

cmd = ["ffmpeg", "-y",
       "-ss", str(clip_start), "-t", str(duration), "-i", source_video]
for _, _, png in cue_pngs:
    cmd += ["-i", png]
cmd += ["-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", ..., out]
```

Critical ordering gotcha: `-ss`/`-t` MUST go BEFORE `-i source_video`,
not after. With multiple `-i` inputs, ffmpeg attaches input-options to
the NEXT `-i`, which would be the first PNG (silently producing
hours-long output instead of the requested cut). See the related skill
`ffmpeg-ss-t-position-multi-input`.

### Filter-graph complexity guardrail

ffmpeg HANGS (not errors, not slow — actually hangs) on overlay chains
above ~25-30 nodes. Auto-VTT cues from YouTube can be 30-50 per minute,
which trivially exceeds this. Consolidate into a manageable count:

```python
MIN_CHUNK_S = 2.5
MAX_CHUNK_S = 5.0
MAX_CHUNK_CHARS = 60
MAX_CHUNKS = 14  # safe upper bound for overlay chain

def consolidate_cues(fine_cues):
    """Merge adjacent cues until each chunk is between MIN and MAX seconds
    or hits the character cap. Cap total at MAX_CHUNKS by sampling."""
    chunks = []
    cur = None
    for c in fine_cues:
        if cur is None:
            cur = dict(c)
            continue
        cur_dur = cur["end"] - cur["start"]
        merged_text = (cur["text"] + " " + c["text"]).strip()
        merged_dur = c["end"] - cur["start"]
        if cur_dur < MIN_CHUNK_S or (
            merged_dur <= MAX_CHUNK_S and len(merged_text) <= MAX_CHUNK_CHARS
        ):
            cur["end"] = c["end"]
            cur["text"] = merged_text
        else:
            chunks.append(cur)
            cur = dict(c)
    if cur:
        chunks.append(cur)

    if len(chunks) > MAX_CHUNKS:
        step = len(chunks) / MAX_CHUNKS
        keep = sorted({int(i * step) for i in range(MAX_CHUNKS)})
        chunks = [chunks[i] for i in keep if i < len(chunks)]
    return chunks
```

### De-cumulating YouTube auto-VTT

YouTube auto-captions emit cumulative cues (each cue contains the
previous cue's text plus new words). Strip the prefix:

```python
if out and text.startswith(out[-1]["text"]):
    new_tail = text[len(out[-1]["text"]):].strip()
    if new_tail:
        text = new_tail
```

Without this you get captions that grow longer over time, then suddenly
reset. With it, you get clean phrase-by-phrase chunks.

## Verification

1. **Output renders without error**: ffmpeg exits 0 within the expected
   wall-clock time (a 60s 1080x1920 clip with 14 caption overlays should
   encode in under a minute on Apple Silicon at `preset veryfast`).
2. **Output filesize is sensible**: 5-15 MB for a 60s 1080x1920 H.264
   clip. Hundreds of MB means something is wrong (most likely the
   `-ss`/`-t` position trap, see related skill).
3. **Captions appear at the right times**: scrub the output and confirm
   the text shown at any given moment matches the active cue window.
4. **Stroke makes captions readable on busy backgrounds**: skip the
   stroke and you'll find white-on-white (suit + lectern) destroys
   readability. Stroke width 4-6 with black fill is the standard
   Shorts/TikTok look.

## Notes

- This is faster than installing `ffmpeg-full` because it doesn't touch
  the user's system tooling. It also gives better-looking captions than
  what `subtitles=` produces, since we control the font/stroke/position
  precisely.
- Font choice: `/System/Library/Fonts/Supplemental/Arial Black.ttf` is
  the most "Shorts-y" on macOS. Helvetica.ttc and Avenir Next.ttc are
  acceptable fallbacks.
- For caption Y-position on 1080x1920 (vertical Shorts), `y=H-h-360`
  places captions about 19% from the bottom — well above the YouTube
  Shorts UI overlays (likes/share buttons sit ~12% from the bottom).
- For an even cleaner look, render the bottom-left and bottom-right
  corners separately using a `[base][cap]overlay=...,format=yuv420p`
  step at the very end of the chain to flatten the alpha.

## References

- [Pillow ImageDraw documentation](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html) -
  for `multiline_text` with `stroke_width` and `stroke_fill`
- [ffmpeg overlay filter](https://ffmpeg.org/ffmpeg-filters.html#overlay-1) -
  the `enable` expression syntax for time-windowed overlays
- [ffmpeg overlay enable expressions](https://trac.ffmpeg.org/wiki/Null) -
  examples of `between(t,X,Y)` and other timeline expressions
