---
name: adaptive-backoff-diagnoses-stall-cause
description: |
  A resumable long-running job that stalls on a FIXED sleep (e.g. "rate
  limited -> sleep 30 min -> retry") hides whether the sleep is too long or
  the resource is genuinely exhausted - you cannot tell from a fixed-interval
  log because the interval was never varied. Replace the fixed sleep with
  ADAPTIVE backoff (short initial sleep, exponential to a cap, RESET to
  minimum whenever a retry was productive) and the timing of the first
  productive retry becomes the empirically-measured refill/recovery interval.
  Use when: (1) an overnight/quota-gated extraction or API loop shows a
  suspiciously regular "N minutes of work then a long nap" cadence,
  (2) someone says "the break is too long, speed it up" about a retry loop,
  (3) you are tempted to just lower a fixed sleep (which only helps if the
  resource refills fast - adaptive finds out WITHOUT committing), (4) you
  need to distinguish a sleep-bound stall (tunable, free win) from a
  resource-exhausted stall (only money/cheaper-unit/waiting helps). No-regret:
  matches the fixed sleep when the resource is truly dry, multiplies
  throughput when it was not.
author: Claude Code
version: 1.0.0
date: 2026-06-13
---

# Adaptive Backoff Both Speeds Up AND Diagnoses a Stalled Retry Loop

## Problem

A resumable job hits a transient/quota error and sleeps a fixed interval
before retrying. The cadence looks like "5 min of work, 30 min idle,
repeat, all night". Two very different causes produce the IDENTICAL log:

1. **Sleep too long** - the resource (quota/lock/window) actually recovered
   minutes ago and the loop is idling for nothing. Free 5-10x win available.
2. **Resource exhausted** - the resource genuinely needs ~that long (or
   longer) to refill; the sleep is correct and throughput is hard-capped by
   the resource, not the loop.

A fixed-interval loop can never distinguish these because it only ever
samples at one interval. Lowering the fixed sleep is a gamble: it helps in
case 1 and just wastes failed retries in case 2.

## Solution

Make the backoff adaptive and let it MEASURE the recovery interval:

```python
sleep_s = MIN_SLEEP          # e.g. 60s
while not done:
    before = measure_progress()        # cheap count from the store
    rc = run_one_window()
    produced = measure_progress() - before
    if produced >= PRODUCTIVE_FLOOR:   # window did real work
        sleep_s = MIN_SLEEP            # reset: ride the open window hard
    else:                              # dry window
        sleep_s = min(sleep_s * 2, MAX_SLEEP)   # back off, cap (e.g. 30 min)
    time.sleep(sleep_s)
```

- Measure productivity from the durable store (rows/edges written), not the
  process exit code - a quota trip exits non-zero whether it wrote 0 or 500.
- Treat an unmeasurable window (store momentarily locked) as productive so a
  measurement hiccup never triggers a needless back-off.
- The FIRST interval at which `produced > 0` is the empirical recovery time.
  If it is far below the old fixed sleep -> you just sped it up. If retries
  stay dry all the way to the cap -> the resource is genuinely exhausted and
  the loop was never the bottleneck (escalate to a cheaper unit, a paid pool,
  or just waiting - none of which the loop can fix).

## Verification

Read the log after a few cycles: a productive window at a SHORT interval
proves case 1 (sped up); a run of dry windows climbing to the cap proves
case 2 (resource-bound). Either way the loop is now no worse than the fixed
sleep and self-tunes to the true interval.

## Example

council-of-thinkers #191 host extraction: flat 30-min sleep showed "~5 min
work / 30 min idle" all night and "60% done, ~2 days left". Suspected the
30 min was wasted. Swapped to adaptive (60s -> 1800s, reset on a >=20-chunk
window). Probes at 1/2/4/8/16 min ALL produced 0 chunks and the count stayed
frozen -> proved the subscription quota itself was exhausted, not the sleep.
The diagnosis (not a speed-up) was the real value: it turned "tune the loop"
into the correct decision (wait for quota / switch to a cheaper model / pay
for Batch API), surfaced to the operator instead of fruitlessly tuning.

## Notes

- Pairs with audit-cheap-output-before-expensive-downstream-step (gate before
  spend) and the autonomous-loops patterns.
- When the answer is "resource-bound", the levers are: a cheaper unit per
  item (smaller model, fewer tokens) that stretches the same pool, a separate
  paid pool (API/Batch), or waiting - never loop timing.
