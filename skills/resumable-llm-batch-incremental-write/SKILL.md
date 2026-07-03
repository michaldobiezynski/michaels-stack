---
name: resumable-llm-batch-incremental-write
description: |
  How to run a LARGE, interruptible, quota-bound LLM batch job (e.g. per-chunk
  concept extraction via `claude -p` over tens of thousands of items) so it is
  actually resumable and never loses paid work. Use when: (1) a pipeline offers
  a "--workers N" / parallel mode that extracts everything into an in-memory
  cache FIRST and writes only at the end; (2) you are tempted to sub-batch with
  a small `--limit` + `--skip-existing`; (3) the job is bounded by a WEEKLY
  subscription quota (`claude -p` on a Max plan) and will be interrupted mid-run;
  (4) you see "0 processed" while most work remains, or a multi-day run that
  loses everything on a crash. Covers council-of-thinkers phase2_extract_concepts
  but the pattern is general.
author: Claude Code
version: 1.1.0
date: 2026-06-08
---

# Resumable LLM batch jobs: per-item incremental write, not parallel-cache

## Problem
You must run an expensive LLM call over a huge corpus (tens of thousands of
items) and write each result to a store (graph, DB). The job will be
interrupted long before it finishes (a weekly `claude -p` quota, a crash, a
laptop sleep). If you pick the wrong execution mode you either lose all the
paid work on the first interruption, or the "resume" silently stalls.

## Context / Trigger Conditions
- A driver script with a `--workers`/parallel flag AND a `--skip-existing`/resume flag.
- A multi-day/multi-week job whose real wall is a WEEKLY subscription quota.
- Symptoms of the traps: a re-run reports "0 processed" while most items are
  undone; or a crash mid-run leaves the store empty despite hours of LLM calls.

## Solution
Before launching the big run, read how the parallel path and the fetch actually work:

1. **Avoid parallel "extract-all-into-cache-then-write".** Many `--workers>1`
   implementations run Phase A (all the slow/paid LLM calls) into an in-memory
   cache, then Phase B writes the store. For a job that WILL be interrupted,
   this is fatal: an interrupt during Phase A loses the entire cache and nothing
   was persisted, so a re-run redoes everything. Only safe when the whole corpus
   fits in one uninterrupted Phase A.

2. **Don't sub-batch with a small `--limit` if the fetch has no order/offset.**
   `table.search().limit(N)` (LanceDB and similar) returns the SAME first N rows
   every call. With `--skip-existing`, batch 2 fetches those same N, finds them
   all done, and processes 0 - the loop stalls at "0 processed" while the bulk
   remains. Small-`--limit` batching only advances if the fetch returns
   different rows each call (un-done-first, random, or offset).

3. **Use per-item incremental mode (`--workers 1`).** Extract THEN write each
   item before the next. A crash leaves every prior item persisted; a re-run
   with a skip-already-done guard resumes. Pass a `--limit` larger than the
   corpus so one invocation walks the whole un-done set incrementally.

4. **The skip guard should check a real downstream artifact**, not a side ledger
   (e.g. "does this chunk already have a MENTIONS edge in the graph?"). That
   stays correct even if a prior run died between extract and a separate
   bookkeeping write.

5. **For a WEEKLY-quota-bound job, more workers does not shorten the calendar.**
   The weekly quota is the wall: parallelism just spends the week's quota in a
   faster burst, then stalls the same number of days waiting for reset. So
   prefer the safe incremental mode; total calendar time is quota-bound either way.

6. **Validate on a tiny `--limit` first** (e.g. 5 items): confirm auth works and
   that results actually LAND in the downstream store (count before/after), then
   commit to the multi-day run.

7. **`claude -p` uses the subscription only when `ANTHROPIC_API_KEY` is UNSET.**
   If it is set, the CLI bills the API instead. `unset ANTHROPIC_API_KEY` in the
   driver.

8. **Resume is "re-run the same command".** Wrap it in a tiny script the human
   re-runs after the weekly quota resets; `--skip-existing` makes it idempotent.

9. **Verify the PROCESSING ORDER, not just that writes land - the storage order
   can bury the high-value subset.** The same orderless `table.search().limit(N)`
   that breaks small-`--limit` batching (point 2) also fixes a single full pass
   into a deterministic STORAGE order. That order is usually ingestion order, so
   a low-value bulk (e.g. an interview HOST's ~20k question/segue chunks) can sit
   entirely AHEAD of the high-value, low-volume subset you actually care about
   (e.g. ~190 enrolled GUESTS, ~4.7k chunks clustered at the very end). A
   quota-bound run then spends days/weeks on the bulk before touching the subset
   that was the whole point. When you pause to verify, don't stop at "rows
   written += N" - also check WHICH entities those rows belong to and where the
   valuable subset falls in the queue (replicate the fetch order, cross-ref the
   skip-guard artifact, print the position of the first/last valuable item). If
   it is buried, process the valuable subset FIRST via the per-entity filter
   (`--speaker <id>` in a loop over the subset's ids, each with `--skip-existing`
   and a `--limit` above that entity's count so it is not re-truncated), then let
   the bulk grind afterwards (a later all-entities run skips the done subset).
   The deeper fix is to add a priority/ordering to the fetch so the default loop
   never buries high-value work; file that as a follow-up.

## Verification
- Tiny batch: store count rises by the expected amount; the run logs per-item
  success (e.g. `cost ~$0.0X`), `chunks_processed=N`.
- Kill the run mid-way, re-run: it skips the already-written items and continues
  (no redo, no stall).
- Order check: after a pause, replicate the fetch order, mark which rows the
  skip-guard considers done, and print where the high-value subset falls in the
  remaining queue. If the valuable items sit near the END behind a low-value
  bulk, re-prioritise (per-entity-filter loop over the subset) before resuming.
  "Writes are landing" is necessary but NOT sufficient - confirm the RIGHT rows
  are being written first.

## Example
```bash
#!/usr/bin/env bash
set -uo pipefail
unset ANTHROPIC_API_KEY                      # claude -p -> subscription, not API
# workers=1: extract+write each item before the next (incremental, resumable).
# --limit huge so one pass walks all un-done items. --skip-existing resumes.
uv run python scripts/phase2_extract_concepts.py \
    --limit 100000 --skip-existing --verbose
# Re-run this whenever the weekly quota resets; it continues where it stopped.
```

## Notes
- The single-writer store lock is held during the run, so you often CANNOT query
  the store to monitor progress mid-run - monitor via the run's own stdout/log
  (per-item cost lines, processed counts), not by querying the DB/graph.
- Related: `audit-cheap-output-before-expensive-downstream-step` (validate the
  cheap stage before the expensive one) and `claude-p-subscription-subprocess`.
- Cost anchor for context: this `claude -p` Sonnet concept extraction measured
  ~$0.02-0.07 per chunk; ~30k chunks ~= ~$1k-equivalent of subscription quota,
  multi-week.
