---
name: council-diarise-host-not-found-threshold-rescue
description: |
  Rescue a council-of-thinkers diarisation relabel that drops a real speaker's
  chunks because their voice cluster sits JUST over the identity threshold. Use
  when: a phase1_5_diarize / diarize_pending dry-run on a clean two-person 20VC
  episode projects kept=0 (or a whole speaker) + dropped=N with the enrol-time
  HOST_NOT_FOUND / MULTI_GUEST flags; or relabel would delete the host's question
  chunks. Root cause is a near-miss on diarize.TAU_ID (default 0.5 cosine
  distance). Covers: measuring per-cluster distances to confirm it's a near-miss
  (not a wrong-speaker), and re-running with a loosened tau_id via run_one's
  injectable identify_fn (NOT by monkeypatching diarize.TAU_ID).
author: Claude Code
version: 1.0.0
date: 2026-06-18
---

# Council diarisation: rescue a just-over-threshold speaker instead of dropping

## Problem

A `phase1_5_diarize` / `diarize_pending` relabel of a clean two-person interview
projects something like `{kept: 0, relabelled: 29, dropped: 11}` — i.e. the HOST's
cluster matches NO reference and its chunks would be **deleted** rather than kept.
The guest enrols with flags `HOST_NOT_FOUND` and/or `MULTI_GUEST`. Going live would
lose the host's question-chunks and leave the episode answers-only.

## Context / Trigger conditions

- Dry-run `dropped > 0` and/or `kept == 0` on an episode you know is just host+guest.
- Enrol report flags `HOST_NOT_FOUND` / `MULTI_GUEST` on a normal 2-person episode.
- `transcripts/_diarisation/<chan>_<vid>.identified.json` shows
  `cluster_to_speaker: {SPEAKER_00: null, SPEAKER_01: <guest>}` — one cluster
  resolved to None.

## Root cause

`diarize._match_speaker` assigns a cluster to its nearest reference only if the
cosine DISTANCE is `<= diarize.TAU_ID` (default **0.5**; smaller = more alike). A
host recorded on a slightly different mic/room can land at e.g. **0.502** — nearest
is still the host, but 0.002 over the cutoff, so it drops to `None`.

## Solution

1. **Confirm it's a near-miss, not a wrong speaker.** Compute each raw cluster's
   distance to every allowed reference, reusing the cached diarisation segments
   (no re-diarise needed):

   ```python
   from ingest import diarize
   lib = diarize.build_reference_library(['harry_stebbings','<guest>'], SAMPLES, hf, device='mps')
   segs = json.load(open('transcripts/_diarisation/<chan>_<vid>.diarization.json'))['segments']
   # group segs by raw SPEAKER_xx label, embed each cluster, then for each ref:
   #   dist = min over ref clips of (1 - cosine(vec, ref))
   ```
   You want: the dropped cluster's NEAREST ref is the intended speaker AND the
   margin to the wrong ref is large (e.g. host_dist=0.502 vs guest_dist=0.762).
   If the nearest ref is the WRONG speaker, do NOT loosen — the drop is correct.

2. **Re-run with a loosened `tau_id` via the injectable `identify_fn`.** Pick a tau
   just above the near-miss distance and well below the wrong-ref distance (0.502 +
   0.762 → 0.55 is safe). `run_one(..., identify_fn=...)` is the supported hook:

   ```python
   idfn = lambda vad, segs, lib: diarize.identify_clusters(
       vad, segs, lib, tau_id=0.55, hf_token=hf, device=device)
   run_one(target, hf, ref, dry_run=True, device=device, identify_fn=idfn)  # expect dropped=0
   ```

   **Do NOT `diarize.TAU_ID = 0.55`** to fix this — `identify_clusters(..., tau_id=TAU_ID)`
   and `_match_speaker(..., tau_id=TAU_ID)` bind the default at definition time, so
   monkeypatching the module global has NO effect. You must pass `tau_id` explicitly,
   which means overriding `identify_fn`.

3. Dry-run, confirm `dropped == 0` and a sane host/guest split, then live. Loosen
   tau **per-episode**, never globally (the 0.5 default protects every other run).

## Verification

`query_speaker(speaker="<guest>", ...)` returns the guest's chunks; the episode
shows both speakers (e.g. `harry_stebbings: 17, <guest>: 23`) with `dropped=0`.

## Notes

- **Held episode:** if you parked the episode with `multi_speaker: false` while
  deciding, `select_targets()` won't return it. Force it with
  `select_targets(only_ids=["<vid>"])` (only_ids force-includes regardless of the
  flag). After a successful relabel it's no longer 100%-host, so `diarize_pending`
  won't re-target it — restore `multi_speaker: true` and note the tau in a comment
  (a future re-ingest + default-tau diarise would re-drop the host otherwise).
- The relabel needs the **LadybugDB graph writer lock**, so stop `council_mcp.server`
  first (see `council-mcp-over-http-and-ladybug-writer-lock`).
- Always dry-run; the chunk-level split can differ from the segment-second coverage
  (run_one re-diarises), but `dropped` is the gate that matters.
- Related: `council-guest-mislabelled-to-host-enrolment-cutoff`.
