---
name: asr-vad-trim-discards-offsets-timestamp-drift
description: |
  Diagnose and fix GROWING clip/word timestamp drift in an ASR + diarisation
  pipeline (council-of-thinkers and similar). Use when: (1) a clip plays the wrong
  moment and the error gets WORSE deeper into the episode (small early, large late),
  (2) a chunk packs far more words than its start/end span allows (e.g. 380 tokens
  of dialogue in a 0-80s window), (3) clip timestamps were derived straight from
  word times yet still do not line up with the YouTube/original audio, (4) you are
  about to "fix" drift by re-transcribing + forced alignment. Root cause is almost
  always a VAD/silence-trim stage that concatenates speech-only audio and DISCARDS
  the per-region offsets, so ASR + diarisation timestamps live in a compressed
  "speech-only" clock. The cheap fix is a piecewise trimmed->original remap (re-derive
  the SAME Silero regions), NOT re-transcription. Also covers: diarisation running on
  the trimmed wav, and the empirical golden check (re-ASR the clip window from the
  ORIGINAL audio).
author: Claude Code
version: 1.1.0
date: 2026-06-25
---

# ASR VAD-trim discards offsets -> growing timestamp drift

## Problem

Clip timestamps drift from the real audio, and the drift GROWS through the episode.
The trap: because clip times are derived straight from Whisper word timestamps,
"growing drift" looks like Whisper word-timestamp inaccuracy, whose textbook fix is
re-transcription + forced alignment (expensive, whole-corpus). That is usually the
WRONG diagnosis.

## Context / Trigger conditions

- A clip opened at its stored `t=Ns` does not contain the words the transcript claims;
  the gap is small at the start of an episode and large near the end.
- A stored chunk packs many more words than its `[start, end]` span could hold (e.g.
  chunk `#0000` with ~380 tokens of dialogue and `timestamp_start=0.0, end=80.3`).
- The pipeline has a VAD pre-pass (e.g. Silero `get_speech_timestamps` +
  `collect_chunks` + `save_audio`) that runs BEFORE ASR.
- ASR (and often diarisation) reads the VAD output wav, not the original audio.

## Root cause

The VAD stage trims silence and *concatenates* the speech-only regions into a shorter
wav (`silero_vad.collect_chunks` then `save_audio`). ASR transcribes THAT wav, so every
word `start`/`end` is in "speech-only" (compressed) time. Nothing adds back the removed
silence, so the offset versus the original clock accumulates with every removed gap ->
linear growing drift. Diarisation frequently runs on the same trimmed wav, so its turns
are in the same compressed clock. The original per-region offsets (`speech_ts`) existed
transiently in the VAD function and were thrown away.

Confirm fast: compare the transcript's last word end (or diarisation max turn end) to the
true episode duration. If it is ~1-3% short (e.g. 4774s vs 4924s), silence was trimmed and
never re-added.

## Solution (remap, do NOT re-transcribe)

1. Re-derive the EXACT same Silero regions on the ORIGINAL audio, mirroring the VAD
   stage's parameters precisely (threshold, min_speech_duration_ms, min_silence_duration_ms,
   sample_rate). Silero is deterministic, so identical params + audio reproduce the regions
   the trimmed wav was built from. Silero returns SAMPLE indices by default
   (`return_seconds=False`); divide by the sample rate for seconds.
2. Validate: `sum(region_end - region_start)` must equal the trimmed wav length / diarisation
   max end to ~0.1s. If it diverges (>~5s), a Silero version/param drift broke the remap;
   stop and fix params before trusting anything.
3. Build a piecewise map `trimmed_to_original(t)`: walk regions accumulating durations;
   for trimmed time t in `[cum_before_i, cum_before_i + dur_i)`, return
   `region_i.start + (t - cum_before_i)`. Clamp outside range. Use `bisect` on the cumulative
   trimmed starts for O(log n).
4. Apply the map to diarisation turn times (keeps them consistent with the words).
5. For the WORDS: either remap the existing (trimmed-clock) transcript with the same map, OR
   (cleanest, if "no silence cutting" is wanted) transcribe the FULL original audio so word
   times are already in original clock, then drop words whose midpoint falls outside any
   speech region (removes intro/music hallucinations WITHOUT shifting the clock).

This is pure arithmetic: no re-ASR of the corpus, no forced alignment.

## Verification (golden check, no human ears)

Empirically prove timestamps: for sampled chunks, cut `[start, start+6s]` from the ORIGINAL
audio, re-ASR just that window (mlx_whisper accepts a numpy slice; the per-call model is
cached per process), and score how many of the chunk's first content words are actually
heard. Run the SAME check on the OLD chunks for a before/after. A correct fix shows a large
gap (observed: rebuilt 15/15 = 100% vs old 1/15 = 7%; the single old pass is the t=0 chunk,
before drift accumulates).

## The best-of-both fix (v1.1 refinement, verified)

Neither "trim the audio" (corrupts the clock) nor "transcribe the full audio"
(fixes the clock but invites hallucination) is right. Untrimmed audio has a
SECOND failure mode beyond generic babble: Whisper inserts PHANTOM SPEAKER
NAMES at silence boundaries (observed: "Robert Leonard", a real podcast host
whose name leaks from speaker-labelled training transcripts; 81 insertions in
one 82-min episode, zero in the trimmed version). A midpoint-in-region word
filter does NOT catch these because whisper stamps them with in-region times.

The correct fix: pass the Silero speech regions to whisper as
`clip_timestamps=[s1, e1, s2, e2, ...]`. Whisper then never sees the silences
(no hallucination bait) AND returns timestamps in the ORIGINAL clock — verified
in mlx_whisper's transcribe loop: `seek` walks original-audio frames per clip
and `time_offset = seek * HOP_LENGTH / SAMPLE_RATE` anchors every word to the
true position. Result on re-pilot: 0 phantom names, real-clock max word end,
golden re-ASR window checks all passing.

## Notes / gotchas

- "Growing drift therefore re-transcribe + forced alignment" is the decision-tree trap; check
  for the VAD-trim offset bug FIRST, it is far cheaper.
- Diarisation usually runs on the trimmed wav too: its turns are remappable with the same map,
  so you do NOT need to re-run pyannote or re-identify speakers.
- Fixed offset (constant gap on every clip) is a different bug (intro/sponsor length mismatch
  between transcribed audio and served video); growing offset is the VAD-trim bug.
- Keep VAD as a region FILTER (drop non-speech words) rather than an audio TRIMMER to retain
  its anti-hallucination benefit without compressing the clock.

## References

- council-of-thinkers: `ingest/vad.py` (`trim_silence` + `collect_chunks`), `ingest/clock_remap.py`
  (`ClockRemapper`, `compute_speech_regions`), `scripts/golden_check.py`, PR #258.
- Related skill: `pyannote-diarise-vad-timeline-and-embed-reload` (VAD timeline for diarisation,
  distinct concern); `audit-cheap-output-before-expensive-downstream-step`.
