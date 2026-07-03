---
name: council-guest-mislabelled-to-host-enrolment-cutoff
description: |
  Diagnose why a known 20VC guest's episode in the council-of-thinkers corpus is
  attributed entirely to the host (harry_stebbings) and the guest is not a speaker.
  Use when: (1) a guest who is clearly named in a video is missing from speakers.yaml
  / query_speaker(<guest>) returns nothing / compare_speakers or explore_speaker on
  them fails because they don't exist; (2) every chunk of an interview episode is
  labelled harry_stebbings; (3) someone asks "how did we not attribute this to X?".
  The root cause is almost always a STALE ENROLMENT BACKLOG (the episode's upload_date
  is past the last guest-report sweep), NOT a title-parse or LLM-extraction failure.
  Includes the full diagnostic chain that distinguishes the two, and the fix.
author: Claude Code
version: 1.0.0
date: 2026-06-18
---

# Council guest mislabelled to host = enrolment-cutoff staleness, not a parse bug

## Problem

A 20VC interview episode is attributed wholesale to the host **harry_stebbings**.
The guest (e.g. Nico Laqua, Corgi Insurance) is not a speaker, so any
`query_speaker` / `explore_speaker` / `compare_speakers` on them is impossible,
and their words surface (via `query_council`) under the host's name.

The tempting explanations are wrong:
- "The clickbait title has no guest name" — red herring. The extractor reads the
  **description** too, and the name is usually there.
- "The LLM failed to extract the name" — usually false; re-running it works.
- "Extraction errored and was dropped" — check the report; the error bucket is
  often empty.

The real cause is almost always: **guest enrolment is a manual/periodic backfill,
and the episode was published after the last sweep's coverage cutoff.**

## Context / Trigger conditions

- `query_speaker(speaker="<guest>", ...)` returns nothing, or the guest is absent
  from `speakers.yaml`, despite a real interview existing.
- A speaker comparison/exploration request names someone who "should" be in the
  corpus but isn't.
- All chunks of an episode carry `attribution_method: config` and
  `speaker_id: harry_stebbings`.

## Solution — the diagnostic chain (run in order)

From the `council-of-thinkers` project root. Replace `<VID>` with the YouTube id.

1. **Confirm it was ingested but host-labelled** (ledger):
   ```python
   # ledger.db -> episodes: ingest_stage='done', speaker_id='harry_stebbings'
   ```
   And the chunks file `chunks/**/<date>_<VID>.chunks.jsonl` has every row
   `attribution_method=config` -> the host. This is the **Phase-0 default for
   every 20VC episode** before a guest is enrolled; it is expected, not the bug.

2. **Confirm the guest is absent from the report**:
   ```bash
   grep -niE "<guest>|<VID>" 20vc_guests.md   # -> nothing
   ```
   `20vc_guests.md` (built by `scripts/report_guest_samples.py`) is the gating
   artifact for enrolment. Absent from all three sections (`to enrol`,
   `no single guest`, `unidentified guest`) AND no `failed guest extraction`
   section/`WARNING` => the episode was **never in the report's episode set**.

3. **Find the report's coverage cutoff** and compare to the episode's date:
   ```python
   # max upload_date among the v=<id> links in 20vc_guests.md, via ledger.db
   ```
   If the episode's `upload_date` is **newer** than the cutoff, the staleness is
   confirmed. (Verified case: report covered through 20260529; the episode was
   20260530 — one day past.)

4. **Rule out a parse/LLM failure by reproducing the extractor** (must use the
   project venv for pyarrow/lancedb):
   ```bash
   .venv/bin/python3 -c "
   import importlib.util
   s=importlib.util.spec_from_file_location('rgs','scripts/report_guest_samples.py')
   m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
   epid='20VC with Harry Stebbings:<VID>'
   title='<the real title>'
   print(m._extract_guest(title, m._description_for(epid)))"
   ```
   If this returns `('guest', '<Correct Name>')` (it did, 3/3, deterministically),
   the extractor works **today** — so the only reason the guest is missing is that
   the episode was never fed to it (the cutoff), not that it couldn't name them.

5. **Confirm the daily pipeline cannot self-heal it**:
   ```bash
   grep -niE "report_guest_samples|enrol_from_episode|guest" scripts/daily_ingest.sh
   ```
   You will find that enrolment is **not** in the daily run, and that
   `diarize_pending.py` **SKIPS episodes whose guest voice sample is missing**.
   So a guest published after the last sweep stays host-labelled indefinitely.

## The fix — verified runbook (2026-06-18)

The chain is FOUR scripts with distinct jobs (a common mistake is thinking
`enrol_from_episode` writes `speakers.yaml` — it does NOT, it only cuts `.wav`s):

1. **Identify guests.** `report_guest_samples.py --out 20vc_guests.md` reclassifies
   ALL host-labelled episodes (slow, rate-limit-prone). To target just the cutoff
   gap, scope it: classify only the post-cutoff episodes with the SAME supported
   `_extract_guest`/`_description_for`, and emit a `## N guest(s) to enrol` report
   in the exact format `ingest.enrol_sample.parse_guests` expects
   (`### Name -> \`speaker_samples/slug.wav\`` then `- URL (kind) Title`).
2. **Cut voice samples.** `enrol_from_episode.py --report <rpt> --all --promote
   --skip-existing --device mps` diarises each guest's own episode, cuts a 30-60 s
   guest-only `.wav`, scores confidence, and writes `voice_sample_candidates.md`.
   `--promote` moves conf≥0.6 unflagged samples to `speaker_samples/`.
3. **Register in speakers.yaml.** `enrol_guests.py --manifest <…> --apply` appends a
   speaker block (voice_sample + per-episode `multi_speaker_candidates`) for the
   CLEAN tier only — **conf≥0.70, no disqualifying flags** (note the 0.70 bar is
   stricter than enrol_from_episode's 0.6 promote bar, so a 0.69 guest is promoted
   but NOT registered).
4. **Relabel chunks.** `phase1_5_diarize.py` / `diarize_pending.py` re-diarises and
   moves chunks `harry_stebbings → <guest>` in LanceDB + updates the graph.
   **Dry-run first** (`--dry-run`): it prints `{kept, relabelled, dropped}` per
   episode; proceed live only if `dropped == 0`. Back up first
   (`backup_corpus.sh`) — a wrong reference HARD-DELETES the guest's chunks.

### Two gotchas that cost real time

- **Relabel needs the LadybugDB graph WRITER lock, so the running MCP server must be
  stopped first.** Otherwise `phase1_5_diarize.run_one` dies with `CotLockedError:
  LadybugDB ... held open by PID <council_mcp.server>`. Stop the MCP backend
  (`dev-down.sh` or kill the `council_mcp.server` pid), clear the stale lock, relabel,
  then restart it (`dev-up.sh`). This is by design — `daily_ingest.sh` SKIPS diarise
  while `council_mcp.server` runs. See `council-mcp-over-http-and-ladybug-writer-lock`.
- **Scope the relabel.** `select_targets(only_ids=…)` ADDS to the full multi_speaker
  set rather than restricting to it, so `diarize_pending`/`phase1_5_diarize` relabel
  EVERY pending all-host episode, not just yours. To do only your N, filter
  `select_targets()` to your video ids and call `run_one` yourself.

Do all of this only after the diarisation path is healthy — it shares the pipeline
that fails under FD exhaustion / the wedged daily ingest (see Notes).

### "Pending relabel > 0" does NOT mean unattributed guests remain

The pending set (multi_speaker episodes still 100% host) permanently includes two
kinds of episode that can NEVER be relabelled, so don't chase the count to zero:

- **Short clips** (1-5 chunks): the guest's voice often isn't separable in a
  30-120 s clip, so diarisation returns `relabelled=0, dropped=0` every run and the
  clip correctly stays host. Re-runs are harmless churn (a few seconds each).
- **Host-solo episodes mis-flagged `multi_speaker`** with the HOST as the "guest"
  (e.g. "Harry on the science of content"). EXCLUDE these from a relabel: if such an
  episode is actually two-speaker but registered with `multi_speaker_candidates:
  [host, host]`, the relabel finds a second cluster, matches it to NO allowed
  reference, and **DROPS** those chunks. Always read the dry-run `dropped` per
  episode; investigate any episode whose only allow-listed speaker is the host.

To stop the perpetual churn, drop the `multi_speaker` flag on these in
`speakers.yaml` — a cleanup, not a correctness fix.

## Verification

After the fix, `query_speaker(speaker="<slug>", query="...")` returns the guest's
own chunks (not host-labelled), and the guest exists in `speakers.yaml`.

## Notes

- **`_description_for` reads only the first 8 lines of the yt-dlp `.description`.**
  The guest name is frequently in those lines even when the title is pure
  clickbait — that is exactly why the extractor uses the description, and why a
  nameless title is not the cause.
- The whole late-publish backlog shares this fate: if the daily ingest is broken
  (FD exhaustion `Too many open files` in diarise, or a wedged concept-extraction
  job), **every** episode past the last sweep is still `harry_stebbings`. The guest
  you are chasing is usually one of many.
- Don't confuse two different "Nico"s (or any common first name): the corpus may
  contain a different person with the same first name who *is* enrolled. The
  unattributed one and the enrolled one are not the same speaker.
- Related: `council-of-thinkers-compare-speakers-needs-resolved-concept`,
  `council-of-thinkers-local-dev`,
  `council-mcp-over-http-and-ladybug-writer-lock`.
