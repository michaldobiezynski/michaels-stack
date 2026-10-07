---
name: sapienslocus-clip-batch-download
description: |
  Batch-download sapienslocus.com clip links as mp4 files ready for native X/Twitter
  video upload. Use when: (1) the user pastes sapienslocus.com/clip?v=...&s=...&e=...
  links and wants the clips downloaded (e.g. from a thread bank / tweet draft doc),
  (2) any task needs a precise YouTube segment as an H.264 mp4 for social upload,
  (3) a yt-dlp --download-sections run fails mid-batch with "HTTP error 403 Forbidden"
  from a googlevideo.com URL. Key facts: the sapienslocus clip page is a YouTube embed
  with NO server-side mp4 (v= is the YouTube ID, s=/e= are start/end seconds); X rejects
  AV1 so formats must pin avc1; the 403 is transient and a plain retry fixes it.
author: Claude Code
version: 1.0.0
date: 2026-07-21
---

# Sapienslocus clip links → X-upload-ready mp4 batch

## Problem

A thread draft references clips as `https://sapienslocus.com/clip?v=<ID>&s=<start>&e=<end>`
links, and each clip must become a local mp4 named by story/tweet so it can be uploaded
natively to X. The site offers no download button or API: the clip page is a Next.js
wrapper around the YouTube iframe player. "Download from sapienslocus.com" therefore
means cutting the segment from the underlying YouTube video.

## Context / Trigger Conditions

- sapienslocus.com/clip URLs in a doc, with `v` (YouTube ID), `s`/`e` (seconds)
- Need for precise YouTube segments as H.264+AAC mp4 (X, LinkedIn, most native uploaders)
- Mid-batch failure: `Error opening input: Server returned 403 Forbidden` on a
  `googlevideo.com/videoplayback` URL, then `ERROR: ffmpeg exited with code 8`

## Solution

1. **Parse the clip URLs** into a pipe-delimited manifest, one line per output file:
   `videoId|start|end|storyNN-tweetNN-slug.mp4`. Duplicate segments (same clip used in
   two tweets) are fine — the cache step below dedupes them.

2. **Download each segment** (only the needed fragments are fetched, not the full video):

   ```bash
   yt-dlp -f 'bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/b[ext=mp4]/b' \
     --download-sections "*${s}-${e}" \
     --force-keyframes-at-cuts \
     --merge-output-format mp4 \
     --no-playlist --no-progress \
     -o "$CACHE/${vid}_${s}-${e}.mp4" \
     "https://youtu.be/${vid}"
   ```

   - `avc1` pin: yt-dlp's default bestvideo is AV1, which X rejects for native upload.
     With an H.264 source, `--force-keyframes-at-cuts` re-encodes via libx264 → the
     output is already upload-ready, no second transcode.
   - `--force-keyframes-at-cuts`: exact boundaries (verified 6.006 s for a 6 s request);
     without it the cut snaps to the nearest earlier keyframe.
   - Loop over a segment cache keyed `${vid}_${s}-${e}` and `cp` to the final name(s);
     run sequentially (avoids cache races on duplicates and YouTube rate limits).

3. **Retry transient 403s**: a signed googlevideo CDN URL can be rejected when ffmpeg
   opens it, failing that one clip while neighbouring clips of the same video succeed.
   Simply re-run the identical command; log per-clip OK/FAIL so the batch never aborts.

## Verification

For every output, check codecs and duration against the manifest (±1.5 s):

```bash
ffprobe -v error -show_entries stream=codec_name -show_entries format=duration \
  -of csv=p=0 "$out"   # expect h264, aac, ≈ (e - s)
```

## Example

36 clips across 10 stories, 23 unique videos: 35 succeeded first pass, one transient
403 succeeded on retry; all verified h264/aac with matching durations; ~4 MB per 25 s
clip at ≤1080p.

## Notes

- One yt-dlp invocation per clip is fine; sections fetch only covering fragments, so
  never download full podcast episodes (hours long, GB each) just to cut seconds out.
- Multiple clips from one video still work per-clip; the cache prevents re-downloads
  only for exact duplicate segments.
- For cutting MANY clips and concatenating them, use the
  `ffmpeg-cut-concat-sync-av1-youtube` skill instead — different failure stack.
- The clip page's "Watch full video" link (`youtu.be/<ID>?t=<s>`) confirms the mapping
  if the URL params are ever in doubt.

## References

- [yt-dlp format selection](https://github.com/yt-dlp/yt-dlp#format-selection)
- [yt-dlp --download-sections / --force-keyframes-at-cuts](https://github.com/yt-dlp/yt-dlp#download-options)
