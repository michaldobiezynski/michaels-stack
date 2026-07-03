---
name: reproduce-failure-on-the-pending-population-not-the-default-sample
description: |
  When reproducing a batch/resume-job failure, sample the ACTUAL unprocessed
  (pending) items, not the convenient default scan/`limit()` order - which in
  a resumable job returns the items that ALREADY SUCCEEDED, so your repro
  "works" and you misdiagnose the cause. Use when: (1) a --skip-existing /
  resumable pipeline stalls and your hand-reproduction of "one item" keeps
  succeeding while the real run keeps failing, (2) you are about to conclude
  quota/concurrency/model-drift from a probe that used `table.limit(N)` or the
  first rows, (3) progress is frozen at a count and you want to know why the
  NEXT item fails. The fix: subtract the done-set and pull items the job has
  NOT yet processed; run the exact failing call on THOSE and capture raw
  output. Also: a long-running subprocess loop needs a no-progress watchdog
  (bounded work-unit + per-call timeout) or one hung child blocks it forever.
author: Claude Code
version: 1.0.0
date: 2026-06-13
---

# Reproduce on the Pending Population, Not the Default Sample

## Problem

A resumable batch job (`--skip-existing`, ledger/graph-gated) stalls. You
reproduce "one item" by hand to see the failure - using the natural default:
`table.search().limit(8)`, `SELECT ... LIMIT 8`, the first files in a glob.
It succeeds, every time. So you blame the environment: quota, rate limits,
concurrency, model drift. Every one of those is wrong, because **the default
order returns the items the job ALREADY COMPLETED** (they were processed
first and succeeded - that is why they are done). The job is failing on the
PENDING items, which have different characteristics (here: low/no-concept
chit-chat, non-English audio, ASR garbage that the model correctly returns
empty for), and you never tested those.

## Context / Trigger Conditions

- A resume/skip-existing job is stuck; your single-item repro keeps working.
- Your probe used `limit(N)` / first-N / default scan order rather than the
  complement of the done-set.
- Progress is frozen at an exact count - the failure is whatever the NEXT
  unprocessed item triggers, not a global condition.
- You have cycled through several "environmental" hypotheses (quota,
  concurrency, throttling) that each seemed plausible and each was wrong.

## Solution

1. **Compute the done-set and sample its complement RANDOMLY, not
   consecutively.** e.g. `pending = [r for r in all if r.id not in done];
   sample = random.sample(pending, 25)`. A CONSECUTIVE slice of pending is
   as biased as `limit(N)`: items cluster by source/episode/partition, so
   the first N pending may all be one anomalous group. (Real miss: 8
   consecutive pending chunks were all one non-English episode -> "the tail
   is conceptless filler"; a RANDOM 25 was 25/25 substantive, identical to
   done. Two opposite wrong conclusions from the same population, both from
   non-random sampling.) Run the EXACT production call on the random items.
2. **Capture the raw output**, not just the parsed/exit result. The pending
   items here returned empty model output (correct for conceptless text); the
   parser then yielded zero, which a circuit breaker mis-aborted on. Only the
   raw dump made that obvious.
3. **Classify the pending population.** A cheap heuristic pass (length,
   script, repetition) tells you what fraction is genuinely junk vs real - and
   whether "finish the backlog" is even worth the spend, or the substantive
   work is already done.
4. **Harden the loop against hangs.** A resumable subprocess loop that does
   `subprocess.run(child)` with no timeout blocks forever if the child hangs
   (observed: a 5h wedge with zero output). Use BOUNDED work units per call
   (small `--limit`) plus a per-call wall-clock `timeout=`; on TimeoutExpired,
   kill the child, clear any stale lock, and continue. Stop on all-done or N
   consecutive no-progress cycles.

## Verification

After sampling pending items, your repro should FAIL the same way the job
does (or reveal the items are legitimately empty). After the watchdog, a
hung cycle shows up as `[HUNG-killed]` and the loop proceeds to the next
cycle rather than freezing.

## Example

council-of-thinkers #191 host extraction stalled; count looked frozen.
Four wrong diagnoses in a row (quota -> sleep-timing -> concurrency ->
breaker-misfire), each from probes that used `limit()` and so tested
already-extracted chunks (which extract perfectly). Sampling the COMPLEMENT
of the done-set revealed the pending chunks were chit-chat / non-English /
"I'm happy I'm happy"x15 ASR garbage; the model correctly returned empty and
the circuit breaker aborted on it. Separately, a driver hung 5h with no
output because the orchestrator's `subprocess.run` had no timeout; fixed with
bounded 300-chunk cycles + a 45-min per-call timeout that kills and retries.

## Notes

- Sibling skills from the same incident: retry-loop-exit-code-hides-real-
  failure (rc mislabelling), adaptive-backoff-diagnoses-stall-cause (sleep vs
  resource), batched-prompt-extraction-density-decay. This one is the meta-
  lesson tying them together: test the RIGHT population first and most of the
  others never arise.
- A circuit breaker that aborts on "zero results" cannot tell "correctly
  found nothing" from "malfunctioning"; for a tail of legitimately-empty
  inputs, disable or raise it rather than letting it wedge the run.
