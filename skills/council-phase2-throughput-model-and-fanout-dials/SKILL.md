---
name: council-phase2-throughput-model-and-fanout-dials
description: |
  Make council-of-thinkers Phase 2 concept extraction ~11x faster before
  committing hours (or a quota window) to a backlog. Use when: (1)
  phase2_run_to_completion.py / phase2_extract_concepts.py is grinding at
  60-80s per chunk and a channel backlog looks like it will take days, (2) the
  log says "ANTHROPIC_API_KEY unset: subscription claude -p serialises, so
  capping --workers from N to 1" and you passed a higher worker count, (3) the
  cost line reads model=claude-haiku-4-5 and you assumed haiku was the fast
  option, (4) you are planning a time-boxed ingest and need real
  seconds-per-chunk numbers, (5) a progress line reads "N/17307" for a speaker
  that has nothing to do with the 20VC host backlog. Covers the two silent
  brakes (haiku default, subscription fan-out cap), measured numbers, and the
  --limit sampling trap that produces false "it works" probes.
author: Claude Code
version: 1.0.0
date: 2026-08-15
---

# Council Phase 2: the two silent brakes on extraction throughput

## Problem

Phase 2 concept extraction runs correctly but ~11x slower than it needs to,
because two independent defaults each cost a large multiple. Neither announces
itself as a performance problem, so a backlog that should take hours is quoted
in days and a fixed quota window gets mostly wasted.

## Context / Trigger conditions

- Extraction is running but each chunk takes 45-80s.
- The driver log shows `cost ~$0.07 USD (model=claude-haiku-4-5,
  duration_ms=68398)`.
- Startup warns:
  `ANTHROPIC_API_KEY unset: subscription claude -p serialises, so capping
  --workers from 3 to 1. Set the key for the parallel-safe paid API path.`
- You need to size a backlog against a deadline.

## Solution

### Brake 1: the EXTRACT_MODEL default is the SLOW model

`ingest/extract_concepts.py` defaults `EXTRACT_MODEL` to `claude-haiku-4-5`
(changed 2026-07-03). Via subscription `claude -p`, haiku is **not** the fast
option — it is several times slower than Sonnet, because throughput here is
dominated by per-call latency, not token price.

```sh
EXTRACT_MODEL=claude-sonnet-4-6 ...
```

### Brake 2: the #214 fan-out cap is over-generalised

`scripts/phase2_extract_concepts.py::_effective_workers()` forces `--workers 1`
whenever `ANTHROPIC_API_KEY` is unset, citing #214 ("subscription claude -p
serialises"). #214's measurement was taken during a DEGRADED subscription
window, where one worker's rate-limit aborts the whole batch — that is a
fragility result, not a throughput ceiling. Re-measured in a clean window,
fan-out scales roughly linearly.

`phase2_run_to_completion.py` also pops `ANTHROPIC_API_KEY` from the child env,
so the cap applies there too. Lift it with the opt-in escape hatch:

```sh
EXTRACT_ALLOW_SUBSCRIPTION_FANOUT=1 EXTRACT_WORKERS=3 ...
```

### Measured numbers (A Life Engineered corpus, 2026-08-14)

| Config | s/chunk | Speedup | Concept density | Errors |
|---|---|---|---|---|
| haiku, 1 worker (**both defaults**) | 75.7 | 1x | 4.7/chunk | 0 |
| sonnet, 1 worker | 17.4 | 4.3x | 3.9/chunk | 0 |
| **sonnet, 3 workers** | **6.7** | **11.3x** | 4.0/chunk | 0 |

Fan-out costs no concept density (3.9 -> 4.0), so this is a free win in a clean
window. Full recommended invocation:

```sh
EXTRACT_SPEAKER=<id> EXTRACT_WORKERS=3 EXTRACT_ALLOW_SUBSCRIPTION_FANOUT=1 \
EXTRACT_MODEL=claude-sonnet-4-6 EXTRACT_DEADLINE_S=<secs> \
  nohup caffeinate -i -s uv run python scripts/phase2_run_to_completion.py &
```

## Verification

Do not trust either default; A/B them on the corpus you are about to spend
hours on. Measure per-chunk time as `elapsed / chunks_processed` from the
`Done. chunks_processed=N concepts_extracted=M` line — NOT elapsed divided by
`--limit`, because `--skip-existing` filters most of the fetch away.

```sh
S=$(date +%s); EXTRACT_MODEL=claude-sonnet-4-6 uv run python \
  scripts/phase2_extract_concepts.py --speaker <id> --skip-existing \
  --workers 1 --prompt-batch 1 --limit 40 > /tmp/ab.out 2>&1; E=$(date +%s)
echo "elapsed=$((E-S))s"; grep -E "^Done|remain" /tmp/ab.out
```

## Example

The trap that invalidates the first A/B attempt:

```
$ ... --limit 5      # after ~1300 chunks are already done
--skip-existing: filtered out 5 of 5 chunks that already have MENTIONS edges; 0 remain.
No new chunks to process; exiting cleanly.        # 8s, measures NOTHING
```

`--limit N` takes the first N rows in LanceDB scan order, which are the
already-done ones. Raise `--limit` well above the done-count so pending chunks
are actually included, and confirm via the `N remain` line before timing.

## Notes

- **Fan-out is more abort-prone when the subscription is flapping**: one
  worker's rate-limit can abort the batch. Only use it under a resume-safe
  driver (`phase2_run_to_completion.py`: bounded cycles, `--skip-existing`,
  hang watchdog, escalating rate-limit backoff). Drop to 1-2 workers if you
  see repeated aborts.
- Hitting the subscription ceiling looks like `cycle: +0 -> N [rate-limit]`
  repeating with escalating waits. That is the driver behaving correctly, not
  a hang; it resumes when quota returns.
- **`TOTAL = 17307` is hardcoded** as the host-backlog completion ceiling, so
  any other speaker shows a nonsense denominator (`1282/17307`). The numerator
  is still a real per-speaker count. Completion for such a run comes from the
  clean-cycle-with-0-produced path (`COMPLETE (driver clean, no new work)`),
  not the ceiling.
- Expect a small genuinely-conceptless remainder (this corpus: 10 of 1,899).
  Chunks logging "first response had no parseable tuples" mostly still resolve
  on the gleaning retry, so do not panic at that line.
- Keep `--prompt-batch 1`: batching to 10 halves concept density (#55).
- Related: [[reproduce-failure-on-the-pending-population-not-the-default-sample]],
  [[batched-prompt-extraction-density-decay]],
  [[council-mcp-over-http-and-ladybug-writer-lock]].
