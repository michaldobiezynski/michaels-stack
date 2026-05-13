---
name: ffmpeg-many-timed-overlays-via-concat-demuxer
description: |
  Render dozens to hundreds of time-windowed overlays (TikTok/Shorts-style
  word-by-word captions, animated lower-thirds, ticker tape, frame-accurate
  watermarks per scene) without hitting ffmpeg's filter-graph hang above
  ~25 overlay nodes. Use when:
  (1) you have a sequence of timed image/text overlays (e.g. 100+ caption
  chunks each shown for ~400ms), (2) the obvious approach of one
  `overlay=enable='between(t,X,Y)'` node per cue hangs ffmpeg (silent,
  no error - typically above 25-30 chained overlay nodes), (3) you can't
  use libass/libfreetype (e.g. Homebrew stock ffmpeg), so subtitle filters
  are off the table. Solution: render each overlay as a fullscreen PNG with
  alpha, sequence them via ffmpeg's concat demuxer with per-image `duration`
  directives to produce a single alpha video track, then composite that
  ONE track with a single overlay filter. Scales to thousands of overlay
  switches per clip; filter graph stays tiny.
author: Claude Code
version: 1.0.0
date: 2026-05-12
---

# Many timed overlays via concat demuxer (single alpha track)

## Problem

You want N timed image/text overlays on a video clip:
- TikTok-style 2-3 word captions, each shown for ~400ms
- Animated lower thirds switching per scene
- Custom watermark/logo that swaps per topic
- Time-coded annotations from a transcript

The obvious approach chains N overlay filter nodes with `enable=` time
windows:

```
[0:v][1:v]overlay=enable='between(t,0.0,0.5)':x=...:y=...[v1];
[v1][2:v]overlay=enable='between(t,0.5,1.1)':x=...:y=...[v2];
[v2][3:v]overlay=enable='between(t,1.1,1.5)':x=...:y=...[v3];
... 100 more ...
[v99][100:v]overlay=...[outv]
```

This works for small N (<= ~20). Above ~25-30 nodes, ffmpeg silently HANGS.
No error, no slow progress, just locked. The chain is too long for the
filter graph init to process in any reasonable time.

You can't use `subtitles=` or `drawtext` with timed expressions either,
because Homebrew's stock `ffmpeg` formula isn't built with libass or
libfreetype.

## Context / Trigger conditions

- You're producing word-level captions, frame-by-frame annotations, or
  per-second overlays with N >= ~25 cues
- Single-overlay approaches (e.g. one big SRT or ASS file) aren't
  available because subtitle filters aren't in your ffmpeg build
- `enable='between(t,X,Y)'` chains hang past a few dozen nodes
- You're rendering to YouTube Shorts / TikTok / Reels 9:16 verticals

## Solution

Treat the entire caption/overlay track as ITS OWN VIDEO STREAM with alpha,
built from a sequence of fullscreen PNGs using ffmpeg's `concat` demuxer.
Then composite that one video stream onto the main clip with a SINGLE
overlay filter.

### Step 1: Render each cue as a fullscreen PNG with alpha

Don't crop to the text bounding box - position the text on a full-resolution
transparent canvas so every PNG is the same size. The concat demuxer
requires uniform dimensions.

```python
from PIL import Image, ImageDraw, ImageFont
import textwrap

W, H = 1080, 1920  # Shorts vertical
CAPTION_FONT_SIZE = 64
CAPTION_STROKE_WIDTH = 6
CAPTION_BOTTOM_MARGIN = 360


def render_fullscreen_caption(text: str, out_path: str, font_path: str) -> None:
    wrapped = textwrap.fill(text, width=22)
    font = ImageFont.truetype(font_path, CAPTION_FONT_SIZE)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # fully transparent canvas
    draw = ImageDraw.Draw(img)

    bbox = draw.multiline_textbbox(
        (0, 0), wrapped, font=font,
        stroke_width=CAPTION_STROKE_WIDTH, align="center",
    )
    text_w = int(bbox[2] - bbox[0])
    text_h = int(bbox[3] - bbox[1])

    x = (W - text_w) // 2 - int(bbox[0])
    y = H - text_h - CAPTION_BOTTOM_MARGIN - int(bbox[1])

    draw.multiline_text(
        (x, y), wrapped, font=font,
        fill=(255, 255, 255, 255),
        stroke_width=CAPTION_STROKE_WIDTH,
        stroke_fill=(0, 0, 0, 255),
        align="center",
    )
    img.save(out_path)
```

Also render a single all-transparent PNG (`blank.png`) at the same size
to use during gaps between cues.

### Step 2: Build the ffconcat list

```python
def write_concat_list(
    cues: list[dict],  # [{start, end, text}], times relative to clip start
    blank_png: str,
    cue_pngs: list[str],
    clip_duration: float,
    out_path: str,
) -> None:
    lines = ["ffconcat version 1.0"]
    t = 0.0
    eps = 0.01
    for i, cue in enumerate(cues):
        cs = max(0.0, float(cue["start"]))
        ce = min(clip_duration, float(cue["end"]))
        if ce <= cs:
            continue
        if cs - t > eps:
            lines.append(f"file '{blank_png}'")
            lines.append(f"duration {cs - t:.4f}")
        lines.append(f"file '{cue_pngs[i]}'")
        lines.append(f"duration {(ce - cs):.4f}")
        t = ce
    if clip_duration - t > eps:
        lines.append(f"file '{blank_png}'")
        lines.append(f"duration {clip_duration - t:.4f}")
    # Final repeat of the last file (no duration) - required so ffmpeg
    # knows the previous segment terminated.
    lines.append(f"file '{blank_png}'")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
```

### Step 3: Single ffmpeg invocation with concat demuxer as input

```bash
ffmpeg -y \
  -ss 100 -t 60 -i source.mp4 \
  -f concat -safe 0 -i caption_concat_list.txt \
  -filter_complex "
    [0:v]setpts=PTS-STARTPTS,split=2[m_in][b_in];
    [b_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=22[bg];
    [m_in]scale=1080:-2[main];
    [bg][main]overlay=(W-w)/2:(H-h)/2[clip_v];
    [clip_v][1:v]overlay=0:0:shortest=0,format=yuv420p[outv]
  " \
  -map "[outv]" -map 0:a \
  -c:v libx264 -preset veryfast -crf 20 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -pix_fmt yuv420p -fps_mode cfr -r 30 \
  -movflags +faststart \
  out.mp4
```

Critical:
- `-ss`/`-t` BEFORE `-i source.mp4` (see related skill
  `ffmpeg-ss-t-position-multi-input`).
- `-f concat -safe 0 -i list.txt` treats the PNG sequence as one input
  stream whose alpha channel survives through the overlay.
- `[clip_v][1:v]overlay=0:0:shortest=0` is the ONLY overlay node for the
  captions. The filter graph stays tiny no matter how many caption
  switches there are.

The concat demuxer streams PNG frames in order with each duration directive,
giving you a logical "alpha video" track without ever encoding an
intermediate file. ffmpeg's overlay filter handles the alpha automatically.

## Verification

For 100+ caption cues:

```bash
ls cap_dir/cap_*.png | wc -l       # Should match cue count + 1 for blank
wc -l caption_concat_list.txt       # ~2N lines (file + duration pairs)
```

Render time should be similar to the no-captions case (PNGs are cheap to
decode). A 60s 1080x1920 clip with 100 cues renders in 20-40s on Apple
Silicon at `preset veryfast`. If it hangs, you've hit a different bug -
the concat demuxer doesn't have an overlay-chain limit.

Visual check: each caption appears for its duration window, switches
instantly to the next. No fades, no flicker (if cues are >= ~250ms).

## Example

In a Shorts pipeline:
- Old approach with chunk consolidation: `MAX_CHUNKS_PER_CLIP = 14`,
  cues of 2.5-5s each, blocks of 5-10 words at a time.
- New approach: 100-150 cues per 60s clip, 300-700ms each, 2-3 words
  at a time. Same encode time. Same filter graph size (one overlay node).

The grouping logic that turns phrase-level VTT cues into word-level chunks:

```python
def group_words(words, target=2, max_words=3, min_dur=0.30, max_dur=0.80):
    chunks = []
    i = 0
    while i < len(words):
        start = words[i]["start"]
        end = words[i]["end"]
        toks = [words[i]["text"]]
        j = i + 1
        while j < len(words):
            new_end = words[j]["end"]
            cur_dur = end - start
            if new_end - start > max_dur:
                break  # hard ceiling
            # Soft caps - only enforce word count once min duration met.
            if len(toks) >= target and cur_dur >= min_dur:
                break
            if len(toks) >= max_words and cur_dur >= min_dur:
                break
            toks.append(words[j]["text"])
            end = new_end
            j += 1
        chunks.append({"start": start, "end": end, "text": " ".join(toks)})
        i = j
    # Stretch any tail-end short chunks up to min_dur (without overlapping
    # the next chunk).
    for k in range(len(chunks)):
        if chunks[k]["end"] - chunks[k]["start"] >= min_dur:
            continue
        next_s = chunks[k+1]["start"] if k+1 < len(chunks) else float("inf")
        chunks[k]["end"] = min(chunks[k]["start"] + min_dur, next_s)
    return chunks
```

The soft-cap rule (only break on word-count once min duration is met) is
necessary because YouTube auto-VTT sometimes emits cue groups where 3
words share a 5ms timing window - per-word division would produce
flicker-fast chunks.

## Notes

- This works for ANY kind of timed overlay, not just captions. Animated
  emoji reactions, scene labels, kinetic typography frames, time-stamped
  callouts - anything you can render to a PNG at fixed resolution.
- Disk impact: N fullscreen RGBA PNGs per clip. PNG compresses transparent
  areas very well (1080x1920 mostly-transparent + small text = 30-80KB).
  For 100 cues that's 3-8 MB per clip, deleted after the encode.
- The concat demuxer requires every `file` to be the same dimensions and
  pixel format. If you mix bbox-cropped sprites and fullscreen frames,
  it'll error. Always render to a consistent size.
- For a "fade-in" caption look, render multiple PNGs per cue (e.g. 5%, 30%,
  70%, 100% alpha) and stagger them ~50ms apart in the concat list.
- This bypasses the libass/libfreetype requirement entirely. PIL renders
  the text into the PNGs; ffmpeg just plays them as a slideshow.

## Related skills

- `ffmpeg-burn-captions-without-libass-pil-overlay` - the predecessor
  approach with `enable='between(t,X,Y)'` overlays. Use that for fewer
  than ~14 cues per clip; switch to this skill above.
- `ffmpeg-ss-t-position-multi-input` - critical when adding a second
  `-i` for the concat list.

## References

- [ffmpeg concat demuxer docs](https://ffmpeg.org/ffmpeg-formats.html#concat) -
  the `duration` directive and ffconcat list syntax.
- [ffmpeg overlay filter](https://ffmpeg.org/ffmpeg-filters.html#overlay-1) -
  alpha handling via the implicit `[in1][in2]overlay` form.
