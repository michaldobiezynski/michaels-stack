---
name: retry-loop-exit-code-hides-real-failure
description: |
  A resume/retry loop that classifies a child process ONLY by exit code (rc)
  will mislabel distinct failures that all exit 1 - most dangerously, an
  LLM-pipeline CIRCUIT BREAKER aborting on unparseable model output looks
  identical at the rc level to a subscription RATE LIMIT, so the loop naps
  and "resumes" forever while making zero progress and reporting the wrong
  cause. Use when: (1) an overnight/batch LLM job is "stuck" and the loop
  blames quota/rate-limits, (2) a job's progress counter is frozen at an
  EXACT number for hours (a true rate-limit lets it creep up in open
  windows; a frozen-exact count means every attempt fails identically),
  (3) the code's own error text says "treating as a LIKELY rate-limit" or
  similar heuristic guess, (4) you are about to conclude "quota exhausted,
  wait/pay" without having read the child's stderr or reproduced one call.
  Fix: capture+classify child stderr (breaker vs rate-limit vs other), and
  ALWAYS reproduce the exact failing call by hand and print the RAW model
  output before believing any second-hand stall label.
author: Claude Code
version: 1.0.0
date: 2026-06-13
---

# A Retry Loop's Stall Reason Is a Guess Until You Read stderr

## Problem

Long-running LLM batch pipelines wrap a worker process in a resume loop:
"non-zero exit -> sleep -> retry with --skip-existing". The loop usually
branches on the exit CODE alone. But several very different failures share
`rc == 1`:

- subscription/API **rate limit** (correct response: wait, resume)
- a **circuit breaker** firing because the model returned unparseable
  output for too many items (a content/model problem - waiting does
  nothing, though a transient may self-clear)
- an ordinary bug/crash

When the worker's own error handling also GUESSES ("exited 1 with no
stderr; treating as a *likely* silent rate-limit"), that guess becomes the
loop's logged reason, and then the operator's mental model. An entire night
can be lost "waiting for quota" while the real issue is the model returning
empty/refusal/wrong-format responses that trip the breaker every window.

## Context / Trigger Conditions

- Progress counter frozen at an EXACT value for hours. A genuine rolling
  rate-limit lets progress creep up whenever a window opens; an exact
  freeze means every attempt is failing the SAME way (breaker / poisoned
  input / bug), not throttling.
- The loop reports "rate limit / quota" but you never confirmed it.
- You are talking to the same LLM/subscription right now (so it is plainly
  not globally exhausted) yet the batch job claims quota death - a strong
  tell that the failure is per-call content, not the pool.
- The worker's error message contains hedging words: "likely", "treating
  as", "probably".

## Solution

1. **Reproduce the exact failing call by hand.** Rebuild the worker's
   precise invocation (same model, same system prompt, same flags) on ONE
   item and run it. Exit 0 with a normal result => the resource is fine;
   the failure is downstream (parsing / breaker / a specific input).
2. **Print the RAW model output**, then run it through the real parser
   separately. This instantly localises model-fine-vs-parser-fine-vs-
   actual-empty. (Here: model returned perfect tuples, parser parsed them,
   live path returned concepts - proving the overnight failure was a
   transient empty/garbage-response window, not quota and not a code bug.)
3. **Read the child's stderr**, not just its rc. The breaker traceback
   ("gleaning retry rate N/N >= threshold") was in stderr the whole time;
   the loop just never surfaced it.
4. **Fix the loop's error taxonomy**: capture stderr and classify -
   breaker-abort (content/model; surface loudly, retry may still recover a
   transient) vs rate-limit (nap) vs other (alert). Never collapse all
   rc=1 into one reason. Give the worker distinct exit codes if you can.
5. **Trust ground truth over self-report**: a monitoring loop's stall
   label is a hypothesis; verify against stderr / a manual probe / the
   durable progress counter before acting (especially before concluding
   "pay money" or "wait days").

## Verification

After fixing classification, a restart should either log productive
windows (count climbs past the frozen value) or log the TRUE failure
(e.g. "BREAKER: model returned unparseable output"), never a generic
"quota trip". Confirm sustained progress, not just one good call.

## Example

council-of-thinkers #191 host extraction: count frozen at exactly 10,378
for ~11 h; loop logged "quota trip (rc=1); sleeping 30 min" every cycle.
User pointed out the subscription was obviously alive (we were chatting on
it). Manual reproduction of the exact `claude -p --model sonnet` call:
exit 0, clean result. Raw output: perfect concept tuples; parser parsed
them; live extract returned 4 concepts. Captured stderr: "no parseable
tuples ... gleaning retry rate 47/50 = 94% >= threshold 50%" - the circuit
breaker, not a rate-limit. The transient (undetermined-cause empty
responses) had since cleared. Fix: orchestrator now captures+classifies
stderr (breaker / rate-limit / other) so the disguise can't recur.

## Notes

- Pairs with adaptive-backoff-diagnoses-stall-cause (distinguish
  sleep-bound from resource-bound) and pipe-masks-exit-code-in-gated-chains
  (rc visibility). This skill is the layer above: even a CORRECT rc can
  carry the WRONG meaning.
- A content circuit breaker is right to abort (don't burn spend on garbage)
  but the surrounding loop must report WHY, and a transient should be
  visibly retried, not silently mislabelled.
