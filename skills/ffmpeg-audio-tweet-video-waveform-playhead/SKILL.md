---
name: ffmpeg-audio-tweet-video-waveform-playhead
description: |
  Turn a short audio clip (wav) into a social-media-ready MP4 (X/Twitter rejects
  bare audio) with a full-clip waveform and a sweeping playhead. Use when: (1) a
  wav/audio sample needs uploading to X/Twitter/social which require video,
  (2) ffmpeg showwaves output looks black/invisible or renders as a flat thick
  bar for speech clips, (3) you want the SoundCloud-style static waveform +
  moving playhead look. Key insight: per-frame showwaves slices (~33ms) carry no
  visible shape for speech; render the whole clip once with showwavespic
  (scale=sqrt) and animate an overlay playhead with x='(t/DURATION)*WIDTH'.
author: Claude Code
version: 1.0.0
date: 2026-08-27
---

# Audio to Tweet-Ready Video: Waveform + Playhead

## Problem
X/Twitter only accepts video, not audio. The obvious ffmpeg filter, `showwaves`,
renders each output frame from ~1/rate seconds of audio, so for speech a frame
holds ~33 ms: with `scale=lin` the wave is nearly invisible; with `scale=cbrt`
it becomes a featureless thick bar. Neither shows the utterance's shape.

## Solution
Two passes: draw the whole clip's waveform once with `showwavespic`, then
composite it with a playhead whose overlay x position is a function of `t`.

```bash
f=input.wav; out=output.mp4
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
ffmpeg -y -i "$f" -filter_complex \
  "[0:a]showwavespic=s=1272x560:colors=0xFFB454:scale=sqrt:filter=peak" \
  -frames:v 1 wave.png
ffmpeg -y -i "$f" -i wave.png -filter_complex "\
color=c=0x0E1116:s=1280x720:r=30:d=${D}[bg];\
[bg][1:v]overlay=4:70[b2];\
color=c=0xFFF1D6:s=4x560:r=30:d=${D}[ph];\
[b2][ph]overlay=x='4+(t/${D})*1272':y=70[v1];\
[v1]drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:text='caption here':\
fontcolor=0x9AA4B2:fontsize=30:x=(w-text_w)/2:y=h-60" \
  -map 0:a -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest "$out"
```

- `scale=sqrt` on showwavespic keeps quiet speech visible without flattening
- `overlay` x expressions accept `t`, giving the moving playhead for free
- `-pix_fmt yuv420p` + H.264 + AAC is what X accepts
- macOS font path for drawtext: `/System/Library/Fonts/Helvetica.ttc` works

## Verification
Extract a mid-clip frame and look at it (`ffmpeg -ss 2 -i out.mp4 -frames:v 1
check.png`); the waveform should show the clip's amplitude envelope with visible
phrasing, playhead partway across. Never ship the video on stream metadata alone:
the invisible-waveform failure probes clean.

## Notes
- Speech waveforms read best with a gap-heavy envelope: `filter=peak` preserves
  the bursts-and-pauses look.
- Duration via ffprobe must be interpolated into the filter string; guard
  against an empty value (a silent empty `d=` makes the color source fail with
  "Unable to parse d option").
