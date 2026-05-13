---
name: ffmpeg-ss-t-position-multi-input
description: |
  Diagnose and fix ffmpeg producing wildly wrong output duration (e.g. an
  88-minute MP4 from what should be a 43-second cut) when an ffmpeg command
  has MULTIPLE `-i` inputs and `-ss`/`-t` is positioned AFTER the source
  video `-i` but BEFORE the next `-i` (typically image overlays for
  watermarks, captions, intro stings). Use when:
  (1) ffmpeg output is much longer than expected with no error,
  (2) output filesize is suspiciously huge (hundreds of MB for what should
  be seconds of content),
  (3) ffprobe reports duration matching the FULL source instead of the
  requested cut window,
  (4) the command worked when there was only one `-i`, then stopped working
  after adding a second `-i` (PNG overlay, image watermark, intro logo).
  Caused by ffmpeg attaching `-ss`/`-t` to the NEXT `-i` it sees, not the
  PREVIOUS one. The flags are silently bound to the wrong input.
author: Claude Code
version: 1.0.0
date: 2026-05-10
---

# ffmpeg `-ss`/`-t` argument-position trap with multi-input commands

## Problem

You're cutting a clip from a video and overlaying one or more images
(watermark, caption PNG, intro logo). The command looks reasonable:

```bash
ffmpeg -y -i source.mp4 -ss 616.5 -t 43.5 \
  -i caption_001.png -i caption_002.png \
  -filter_complex "..." -map "[outv]" -map 0:a out.mp4
```

What you expect: a 43.5-second output starting at 616.5s of `source.mp4`.

What you get: an output covering the FULL `source.mp4` from start to end
(possibly hours). File size is huge. ffprobe reports a duration matching
the source video, not the requested cut.

There is no error. ffmpeg encodes happily. The only sign of trouble is
the absurd output length.

## Context / Trigger conditions

This bug fires when ALL apply:

- The ffmpeg command has TWO OR MORE `-i` inputs (typical for overlay
  workflows: source video + caption PNGs / watermark / sting images)
- `-ss <start>` and/or `-t <duration>` are positioned BETWEEN inputs,
  e.g. `-i source.mp4 -ss S -t D -i overlay.png`
- The intent was for `-ss`/`-t` to apply to `source.mp4`

The same code with ONE `-i` (no overlay) appears to work, because the
flags happen to land in a valid output-options position. Add a second
`-i` and the bug appears.

## Root cause

ffmpeg's argument parsing treats `-ss` and `-t` as **input options**: they
attach to the input that COMES AFTER them. Position relative to `-i`
matters and is order-sensitive:

| Position | Meaning |
|---|---|
| `-ss S -i FILE` | Seek INPUT to S (input-side seek). Fast/keyframe-based. |
| `-i FILE -ss S` (followed immediately by output spec) | `-ss S` is treated as an OUTPUT option (output-side seek). Slow/accurate. |
| `-i FILE1 -ss S -i FILE2` | `-ss S` is an INPUT option for FILE2 — NOT FILE1 |

In the third row above, your `-ss`/`-t` silently retarget to the
wrong input. PNG overlays don't have a duration to seek into, so the
`-ss`/`-t` are ignored on FILE2, the source video gets neither seek nor
duration cap, and ffmpeg processes the entire source.

## Solution

Place `-ss` and `-t` BEFORE the source `-i`:

```bash
ffmpeg -y \
  -ss 616.5 -t 43.5 -i source.mp4 \
  -i caption_001.png -i caption_002.png \
  -filter_complex "..." -map "[outv]" -map 0:a out.mp4
```

This is "input-side seek" on the source. With `-c copy` it lands on the
nearest keyframe before S; with re-encoding (most filter_complex pipelines
are re-encoding anyway) it produces an accurate cut.

If you specifically need OUTPUT-side seek (frame-accurate, slower) AND
have multiple inputs, use the `trim` and `atrim` filters in
`filter_complex` instead of `-ss`/`-t`:

```
[0:v]trim=start=616.5:end=660.0,setpts=PTS-STARTPTS[v0]
[0:a]atrim=start=616.5:end=660.0,asetpts=PTS-STARTPTS[a0]
```

Then continue the graph from `[v0]`/`[a0]`. This binds the cut to the
specific stream regardless of input order.

## Verification

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 out.mp4
```

If the duration matches your `-t`, the fix worked. Pre-fix you'll see
the FULL source duration (or close to it).

A second sanity check: file size. A 43-second 1080p clip should be a
few MB. If you're seeing hundreds of MB, the cut wasn't applied.

## Example

In a Shorts pipeline that cuts a 43-second segment from a 9.5-minute
source video and overlays caption PNGs, this command produced a 5300-second
(88-minute) 625 MB MP4:

```bash
# WRONG - flags are between inputs, bind to the first PNG
ffmpeg -y -i source.mp4 -ss 616.5 -t 43.5 \
  -i cap_0.png -i cap_1.png -i cap_2.png ... \
  -filter_complex "..." out.mp4
```

Reordering to put `-ss`/`-t` before `-i source.mp4` produced a correct
43.5-second 6 MB output:

```bash
# RIGHT - flags bind to the source video
ffmpeg -y -ss 616.5 -t 43.5 -i source.mp4 \
  -i cap_0.png -i cap_1.png -i cap_2.png ... \
  -filter_complex "..." out.mp4
```

No filter graph or output codec changes were needed. The fix is purely
argument ordering.

## Notes

- This trap is most likely to bite when you're refactoring a working
  single-input cut command to add overlays. The original `-ss`/`-t`
  position was fine in single-input form; adding `-i` inputs after it
  silently breaks the cut.
- Audio still works because `-map 0:a` correctly references the source's
  audio stream regardless of seeking — the audio track plays for as long
  as the (unseeked, untrimmed) source has audio. So you'll hear the right
  speaker, just for far too long.
- The `concat` demuxer command form (`-f concat -i list.txt`) doesn't hit
  this bug because there's a single input list. The bug is specific to
  multiple `-i` inputs.
- `-frames:v` and `-to` follow the same input-vs-output positioning rules
  and have the same potential trap.

## References

- [ffmpeg input/output options docs](https://ffmpeg.org/ffmpeg.html#Main-options) -
  the `-ss` documentation explicitly notes "When used as an input option..."
  vs "as an output option"
- [ffmpeg seeking wiki](https://trac.ffmpeg.org/wiki/Seeking) - covers the
  before-vs-after-`-i` distinction but doesn't call out the multi-input
  retargeting behaviour explicitly
