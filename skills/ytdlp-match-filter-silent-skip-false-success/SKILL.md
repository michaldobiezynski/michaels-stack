---
name: ytdlp-match-filter-silent-skip-false-success
description: |
  Two linked yt-dlp gotchas when (re)downloading a backlog. (1) A
  download+register wrapper around `yt_dlp.YoutubeDL` with a `match_filter`
  (e.g. a `duration > N` gate) SILENTLY SKIPS videos that fail the filter:
  `extract_info(url, download=True)` still returns an info dict (so the wrapper
  registers a DB row and returns "success") but NO audio file is written. A
  non-error return is therefore a FALSE success -- verify the artifact exists,
  not the return value. (2) A pile of ledger/DB items "stuck" at a downloaded
  stage with missing audio (that a processor 0s-skips) may not be a gap to
  backfill at all -- they can be content EXCLUDED BY DESIGN by that same filter
  (shorts / sub-N-second clips). Use when: (a) a "re-download the missing N"
  task reports success but files don't appear; (b) yt-dlp logs "does not pass
  filter (duration > N), skipping"; (c) a batch download counter looks right
  but disk usage / file count didn't change; (d) episodes show "stopped in 0s
  (stage=downloaded)" / "audio_path missing" forever; (e) before bulk-fetching
  a "missing" backlog, to check it isn't filtered-by-design. Fix: bucket the
  backlog by the filtered dimension (duration) FIRST, decide if it's a real
  gap, and verify each download landed a file before counting it.
author: Claude Code
version: 1.0.0
date: 2026-06-01
---

# yt-dlp match_filter silently skips -> false "downloaded"

## Problem

A wrapper like `download_and_register(urls)` builds `yt_dlp` opts with a
`match_filter` (very common: a duration gate to skip shorts / trailers):

```python
opts["match_filter"] = yt_dlp.utils.match_filter_func("duration > 600")
```

When a URL fails that filter, `ydl.extract_info(url, download=True)`:

- does NOT raise (no `DownloadError`),
- still returns an info dict (metadata is fetched even though the media isn't),
- writes NO media file.

So a naive wrapper does `registered.append(episode_id); return registered` and
the caller logs "1 downloaded" -- but nothing landed on disk. The DB row may
even get an `audio_path` pointing at a file that was never written. This is a
silent false-success: the count says done, the filesystem says otherwise.

The second trap is upstream: a backlog of items "stuck" with missing audio
(a processor logs `stopped in 0s (stage=downloaded)` / `audio_path missing`)
is easy to read as "downloads that failed and need retrying". But if every one
of them fails the SAME `match_filter`, they were never meant to download -- the
filter excludes them BY DESIGN (e.g. all are <=30s clips). Force-fetching them
re-adds content the pipeline deliberately drops.

## Context / Trigger conditions

- A "re-download the N missing" job logs success but `du` / file count is flat.
- yt-dlp prints `... does not pass filter (duration > N), skipping ..`.
- Items sit forever at a "downloaded" stage with null/missing `audio_path`.
- You're about to bulk-download a "missing audio" backlog to "finish" ingestion.

## Solution

1. **Verify the artifact, not the return value.** After each download, check
   the file actually exists (re-read the row's `audio_path` and `Path.exists()`),
   and only then count it as fetched:

   ```python
   download_and_register([url], speaker_id=spk, include_shorts=True)
   if _audio_present(episode_id):   # SELECT audio_path ... ; Path(ap).exists()
       ok += 1
   else:
       skipped += 1                 # filtered / unavailable -- NOT a success
   ```

2. **Bucket the backlog by the filtered dimension BEFORE downloading.** For a
   duration gate, count how many fall under it:

   ```python
   under = sum(1 for r in rows if 0 < dur(r) <= GATE)
   ```

   If ~all of them are under the gate, they're excluded by design -- stop,
   surface it, and let the human decide rather than forcing them in.

3. **To deliberately include them, lower the gate, don't remove verification.**
   e.g. an `include_shorts=True` flag drops `>600` to `>30`; a true "everything"
   pass needs `>0`. Either way keep the file-exists check.

4. **Clean up, don't churn.** Items that should stay excluded will 0s-skip on
   every run. If the churn/log-noise matters, mark them terminally in the
   ledger so they leave the pending set, rather than re-attempting forever.

## Verification

- After a download run, `find <audio_root> -newer <marker>` (or a file count /
  `du -sh`) should grow by the number you counted as "fetched".
- The "fetched" counter should match real files, and "skipped/unavailable"
  should account for everything the filter rejected.

## Notes

- `extract_info(..., download=False)` (metadata-only) is the right call when you
  only want title/duration/etc -- but note the bug is the *download=True* path
  returning info without media when filtered.
- Sibling lessons: `classifier-failure-vs-negative-bucket` and
  `audit-cheap-output-before-expensive-downstream-step` -- all three are
  "a non-error / success-looking result is not proof the work happened".
- Real instance: council-of-thinkers `scripts/download_missing_audio.py` /
  `ingest/youtube.py` (2026-06-01). 544 "missing audio" episodes were all
  <=30s clips excluded by the `duration > 30` gate; the first smoke test logged
  "1 downloaded" while writing nothing.
