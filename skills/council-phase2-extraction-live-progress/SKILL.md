---
name: council-phase2-extraction-live-progress
description: |
  Measure live progress / ETA of a running council-of-thinkers phase-2 concept
  extraction when the daily-ingest log shows nothing after "--- extract:
  concept-graph backfill ---". Use when: (1) someone asks "how far is the
  extraction / what's the ETA" while phase2_extract_concepts.py is running,
  (2) the daily-ingest log (logs/daily-ingest-YYYYMMDD.log) is frozen at the
  extract header because the child's stdout is block-buffered and the graph
  (ladybugdb/council) is LOCKED so you cannot query its chunk count, (3) you need
  chunks-done / chunks-remaining / rate without touching the single-writer graph.
  Key: the orchestrator phase2_run_to_completion.py redirects the child's
  --verbose output to /tmp/191_cycle.out (and cycle summaries to
  /tmp/191_final.log), NOT the daily log; the backlog total and a per-call cost
  line live there. chunks_done = (extract-concepts cost lines) MINUS (gleaning
  retry lines), because a chunk that fails the first parse makes a 2nd call.
author: Claude Code
version: 1.0.0
date: 2026-06-24
---

# Live progress + ETA of a running council phase-2 extraction

## Problem

A council concept-extraction run (`scripts/phase2_extract_concepts.py`, driven by
`scripts/phase2_run_to_completion.py` from the daily cron) is in progress and you
want progress / ETA. But `logs/daily-ingest-YYYYMMDD.log` is stuck at
`--- extract: concept-graph backfill (all speakers) ---` with nothing after it,
and you cannot query the graph for a chunk count because the running writer holds
the single-writer `ladybugdb/council.cot.lock` (any open -> CotLockedError).

## Context / Trigger conditions

- `pgrep -f phase2_extract_concepts.py` shows a live writer; `ladybugdb/council.cot.lock`
  holds its (live) PID.
- The daily-ingest log's mtime/size hasn't moved since the extract header (the
  child's stdout is block-buffered to a file, and the orchestrator runs one big
  cycle with `--limit` above the corpus size, so it only prints a cycle summary
  at the very end).
- You want done / remaining / rate / ETA mid-run.

## Solution

The orchestrator sends the child elsewhere (see `phase2_run_to_completion.py`:
`LOG = /tmp/191_final.log`, `CYCLE_OUT = /tmp/191_cycle.out`; confirm these
constants in case they change). Read those, not the daily log.

```sh
# Backlog total (printed once at the child's start):
grep -a 'skip-existing' /tmp/191_cycle.out | head -1
#   "--skip-existing: filtered out 35424 of 38745 chunks ...; 3321 remain."
TOTAL=3321

# Chunks DONE = first-attempt cost lines = (all cost lines) - (gleaning retries),
# because a chunk whose first response has no parseable tuples makes a 2nd
# "(gleaning retry) cost" call for the SAME chunk.
CALLS=$(grep -ac 'extract-concepts cost' /tmp/191_cycle.out)
RETRIES=$(grep -ac 'gleaning retry' /tmp/191_cycle.out)
DONE=$((CALLS - RETRIES))

# Rate from elapsed wall time since the first cost line's timestamp.
# rate = DONE / elapsed_min ; ETA_min = (TOTAL - DONE) / rate
```

Liveness/health without the lock: `ladybugdb/council.wal` mtime should be within
the last few seconds and growing (~15-20 KB/min); a `claude -p
--model claude-sonnet-4-6` process should be present (one ~10-20s call per
passage, serial). Same writer PID over time = no hang-relaunch.

## Verification

- `DONE/TOTAL` matches the rough backlog from `lancedb` count minus the graph's
  last-known chunk count (e.g. 38745 - 35578 ~= 3167, close to the 3321 the child
  reports after `--skip-existing`).
- A second sample minutes later shows `DONE` increased and the WAL grew.

## Example

24 Jun: after clearing a 6-day stale-lock skip, the catch-up extraction ran with
the daily-default `--workers 1 --prompt-batch 1`. Daily log frozen at the extract
header. `/tmp/191_cycle.out` showed `3321 remain`; `877 cost lines - 110 gleaning
retries = 767 chunks done (~23%)` in 269 min -> ~2.85 chunks/min -> ~21h ETA.
That (correctly) revised an earlier hand-wave of "a few hours" and showed the run
would still be live at the next 10:00 cron (which then safely skips, per
stale-lock-shell-guard-skips-scheduled-phase).

## Notes

- Speed lever is `--prompt-batch N` (passages per claude call), NOT `--workers`
  (force-capped to 1 on the subscription; concurrent claude -p calls trip the
  breaker). Restart is safe/resumable via `--skip-existing` + the graph (the WAL
  replay on the next open commits already-finished batches, so a kill loses at
  most the in-flight batch).
- **WARNING - `--prompt-batch >1` STICKILY REDUCES concept density. Default to
  `--prompt-batch 1` (per-chunk) for any permanent corpus.** docs/channel-onboarding.md
  (the measured 20VC record, #55) is explicit: `--prompt-batch 3` -> ~75% density,
  `--prompt-batch 10` -> ~50% (2.0 vs 4.0 mentions/chunk), and the deficit is STICKY
  because `--skip-existing` never revisits those chunks. Use batching (<=3, never
  near 10) ONLY for low-stakes bulk. The runbook also states "wall-clock is the
  same; batching only saves tokens" - which CONFLICTS with a 24 Jun observation of
  ~2.85 -> ~7 chunks/min at `--prompt-batch 5`; treat that measured speedup as
  unverified/confounded and do NOT trade density for it on a corpus you care about.
  (24 Jun: ran the 20VC catch-up of ~2,292 chunks at `--prompt-batch 5` before
  consulting the runbook -> those chunks are stickily under-extracted; remediation
  is wipe+re-extract at `--prompt-batch 1`, not a plain re-run.) ALWAYS read
  docs/channel-onboarding.md before tuning phase2 flags.
- **PITFALL: do NOT extrapolate the rate from the first few batched calls.** At
  start they can clock ~2-3s each (short/empty opening passages), which falsely
  projected ~25x / ~40min; the true steady rate (~30s/call) only showed after
  ~30+ batches. Always average over many batches (count `batch N/92` advanced per
  elapsed minute), not the opening burst.
- **In batched mode the writer log lines change AND the lock cycles per batch.**
  Progress lines read `batch N/92`; cost lines read `(batched) cost`. The batched
  path opens+closes the graph PER BATCH ("progress saved each batch"), so
  `council.cot.lock` is INTERMITTENTLY ABSENT between batches even while a writer
  is active - do NOT read a missing lockfile as "no writer". Confirm liveness with
  `pgrep -f phase2_extract_concepts.py`, not the lockfile. (The daily cron's guard
  already uses the process check, so this is safe.)
- To run with `--prompt-batch N` you must invoke phase2_extract_concepts.py
  directly (the orchestrator phase2_run_to_completion.py hardcodes --prompt-batch 1
  at the Popen cmd); raise `ulimit -n` and wrap in `caffeinate -i -m -s`, unset
  ANTHROPIC_API_KEY for the subscription, and detach with nohup+disown. You lose
  the orchestrator's hang-watchdog, so monitor it.
- The graph is single-writer; do NOT open it for a count while the writer runs.
- Cost lines (~$0.02-0.04 each) appear even on the subscription run (the logger
  estimates a notional USD cost); they are not real API charges when
  ANTHROPIC_API_KEY is unset.
- Related: stale-lock-shell-guard-skips-scheduled-phase, claude-p-subscription-subprocess.
