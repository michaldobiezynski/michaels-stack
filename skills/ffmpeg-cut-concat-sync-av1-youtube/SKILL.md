---
name: ffmpeg-cut-concat-sync-av1-youtube
description: |
  Fix silent A/V desync, frame distortion, and inflated-duration bugs when
  cutting and concatenating AV1-encoded YouTube videos with ffmpeg. Use when:
  (1) a compilation made from yt-dlp downloads has audio drifting away from
  video, (2) clip starts show garbled or frozen frames before the speaker
  appears, (3) ffprobe reports a much longer duration than the sum of clip
  durations, (4) videos play fine individually but a concatenated MP4 looks
  scrappy. Covers the combined fix: output-side seek, PTS reset, constant
  framerate, audio resample-with-async, and re-encode-during-concat instead
  of `-c copy`. Applies whenever the source is YouTube AV1 output (the
  default `bestvideo` selection on most modern videos).
author: Claude Code
version: 1.0.0
date: 2026-05-09
---

# ffmpeg cut + concat sync for AV1 YouTube videos

## Problem

You download YouTube videos with `yt-dlp`, cut clips out with ffmpeg, and concat
them into one MP4. The output has any combination of:

- Audio that drifts further out of sync as the video plays
- Frame distortion or frozen frames at the start of each clip
- A reported duration that is much longer than the sum of clip durations
  (e.g., 15 clips totalling 11m26s but ffprobe reports 19m43s)
- "Junk" frames where the speaker hasn't appeared yet

Each individual cut may look fine when previewed; the problems get worse at
concat time.

## Context / Trigger conditions

This stack of bugs appears together when ALL of these are true:

- Source is YouTube `bestvideo` output (modern downloads default to **AV1**;
  check with `ffprobe -select_streams v:0 -show_entries stream=codec_name`)
- Cuts are made with `-ss <start>` placed BEFORE `-i <input>` (fast keyframe
  seek)
- Concat uses the demuxer with `-c copy` (`ffmpeg -f concat -i list.txt -c copy ...`)
- Clips come from MULTIPLE different source files (15 different videos, not 15
  cuts of one source)

AV1 uses long GOPs with sparse keyframes. Fast input seek lands on the nearest
keyframe BEFORE the requested start, but `-ss` before `-i` keeps that timestamp
as the "start" of the output, producing a clip whose first frames are pre-
keyframe junk being decoded toward the actual cut point. Then `-c copy` concat
inherits each clip's timestamp baseline, so cumulative drift across 15 inputs
breaks both A/V sync and the container's reported duration.

## Solution

Fix BOTH the cut step and the concat step. Half a fix won't work.

### Cuts (per-clip ffmpeg command)

```
ffmpeg -y \
  -i SOURCE.mp4 \
  -ss START -t DURATION \              # -ss AFTER -i = accurate seek
  -c:v libx264 -preset veryfast -crf 20 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -pix_fmt yuv420p \
  -fps_mode cfr -r 30 \                # uniform constant framerate
  -vf "setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" \
  -af "aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS" \
  -avoid_negative_ts make_zero \
  -movflags +faststart \
  CLIP_NN.mp4
```

Key parts:

- `-i ... -ss START` (output-side seek): accurate to the requested frame, not
  to the nearest keyframe. Slower than fast seek but mandatory for AV1 cuts.
- `setpts=PTS-STARTPTS`: zeros the video PTS so each clip starts at 0:00.
- `aresample=async=1` + `asetpts=PTS-STARTPTS`: handles VFR audio drift and
  zeros audio PTS. `aresample` alone is not enough.
- `-fps_mode cfr -r 30`: forces constant framerate. Without this, sources at
  25/30/60 fps mix unpredictably during concat.
- `-avoid_negative_ts make_zero`: belt-and-braces against PTS going negative
  after the resets.

### Concat: re-encode, do NOT `-c copy`

```
ffmpeg -y -f concat -safe 0 -i list.txt \
  -c:v libx264 -preset veryfast -crf 20 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -pix_fmt yuv420p \
  -fps_mode cfr -r 30 \
  -movflags +faststart \
  compilation.mp4
```

Re-encoding during concat is fast (the inputs are already H.264 so the encoder
runs near real-time) and eliminates the SPS/PPS-mismatch and timestamp-baseline
issues that silently break `-c copy` across multi-source inputs.

## Verification

1. **Sum of clip durations matches container duration**: compute the manifest
   sum, then `ffprobe -v error -show_entries format=duration compilation.mp4`.
   If those don't match within ~1 second, sync is broken.
2. **Single codec/profile across the file**: `ffprobe -show_streams compilation.mp4`
   should show one consistent stream throughout, not segments with different
   `nb_frames` or `r_frame_rate`.
3. **Eyeball the first 2 seconds of every cut**: with the fix, each clip starts
   on the speaker's mid-sentence. Without the fix, you'll see frozen/garbled
   frames for ~0.5-2s.
4. **Watch the last 30 seconds**: drift accumulates, so listen for lip-sync at
   the end. With CFR + reset PTS + concat re-encode, this is rock-solid.

## Example - failure symptom and fix

The first attempt at a 15-clip Reform UK compilation reported `duration=1183.147735`
but the manifest summed to 685.7s. Audio drifted across clips and several clips
started with garbled frames. The configuration was:

- Source: yt-dlp default → AV1 video at 25fps
- Cut: `ffmpeg -ss <s> -i src.mp4 -t <d> -c:v libx264 ...`
- Concat: `ffmpeg -f concat -i list.txt -c copy out.mp4`

After applying both fixes (output-side seek with PTS reset on cuts, plus full
re-encode at concat), the next run produced `duration=686.033333` matching the
sum, with clean cuts and stable sync across all 15 clips.

## Notes

- If you only need to extract ONE clip from ONE source, fast seek with
  `-ss BEFORE -i` and `-c copy` will probably look fine. The bug stack only
  fires when you combine multi-source + cut + concat.
- `-c copy` concat is fine when the inputs are guaranteed-identical streams
  (e.g., from the same source split by `-segment`). It's the heterogeneous
  inputs that break it.
- `-fps_mode cfr` replaces the older `-vsync cfr` in modern ffmpeg. Both work
  on 4.x+ but `-fps_mode` is preferred and the deprecation warning is verbose.
- If you need text overlays via `drawtext`, note that Homebrew's stock `ffmpeg`
  formula does NOT include libfreetype (no drawtext). Install `ffmpeg-full`
  or skip overlays.
- The concat filter (`-filter_complex concat=n=N:v=1:a=1`) is an alternative
  to the demuxer + re-encode approach. It's more flexible but slower for many
  inputs and the filter graph gets unwieldy past 5-6 clips.

## References

- [ffmpeg seek documentation](https://trac.ffmpeg.org/wiki/Seeking) - covers the
  `-ss` before-vs-after-`-i` distinction
- [ffmpeg concat documentation](https://trac.ffmpeg.org/wiki/Concatenate) -
  the demuxer is "stream copy" by default, hence the `-c copy` trap
- [yt-dlp format selection](https://github.com/yt-dlp/yt-dlp#format-selection)
  - explains how AV1 became the default `bestvideo` pick on modern YouTube
