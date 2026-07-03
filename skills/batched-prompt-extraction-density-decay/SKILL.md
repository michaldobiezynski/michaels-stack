---
name: batched-prompt-extraction-density-decay
description: |
  Packing N passages into one LLM extraction call silently REDUCES per-passage
  output density even when format compliance is perfect: measured on real
  Sonnet podcast-transcript concept extraction, 1 passage/call = 4.0
  concepts/chunk, 3/call = 3.0 (75%), 10/call = 2.0 (51%), with ZERO parse
  failures at every size - the model compresses its per-passage effort, it
  does not break format. Use when: (1) designing batched/multi-document
  prompts to amortise a long system prompt across items, (2) a batched
  pipeline "works perfectly" (parses clean) but downstream counts/recall
  look thin, (3) deciding a prompt_batch/batch-size knob for a large corpus
  run, (4) tempted to validate batching by format compliance alone. Always
  run a density-parity probe (same population, per-item control vs batched)
  before committing a corpus; the deficit is sticky when resume logic
  marks items done.
author: Claude Code
version: 1.0.0
date: 2026-06-12
---

# Batched Extraction Trades Per-Item Density for Token Savings - Measure It

## Problem

Bundling N items into one extraction call amortises the (often long,
few-shot) system prompt and looks strictly cheaper. But a single reply
spanning N passages compresses per-passage output: the model finds fewer
concepts/entities/facts per item as N grows. The failure is invisible to
every structural check - blocks parse, delimiters are canonical, zero
fallbacks - because the model is complying perfectly while simply saying
less per item.

## Context / Trigger Conditions

- A batched pipeline passes all format tests and a real-model smoke test,
  yet items extracted in batch mode carry visibly fewer outputs than
  earlier per-item runs.
- You are choosing N for a multi-thousand-item corpus run.
- Resume logic (skip-already-processed) makes under-extraction STICKY:
  thin items are marked done and never revisited without a wipe.

## Solution

1. **Parity probe before the corpus run**: extract one slice per-item
   (control) and one slice batched FROM THE SAME population (same fetch
   region, same speaker/source), then compare mean outputs-per-item from
   the actual store. Population-matched control matters: earlier items in
   a corpus often differ systematically from later ones.
2. **Expect monotonic decay** and pick N from measured parity, not from
   token maths alone. Measured curve (Sonnet 4.6, ~512-token transcript
   chunks, up-to-6-concepts prompt): N=1: 100%; N=3: 75%; N=10: 51%.
3. **Gate, don't eyeball**: encode a parity floor in the run orchestrator
   (e.g. stop with a written verdict below 0.7) so an unattended run
   cannot burn the corpus at low density.
4. **Weigh stickiness vs renewability**: quota/cost is renewable; a
   density deficit baked into a skip-existing corpus is not. For
   high-value corpora prefer per-item; batched N=2-3 suits low-stakes
   bulk where ~75-85% density is acceptable.
5. Wall-clock may be IDENTICAL either way (writes and serialisation
   dominate); batching saves tokens, not time - do not justify it with
   speed.

## Verification

After choosing N, re-measure density on the first few hundred corpus
items and compare against the probe; investigate any further drop
(content drift, truncation, prompt regression).

## Example

council-of-thinkers #191: a 17.3k-chunk host backlog. The 10-passage
batch passed every format test and a live-model gated test, then measured
2.04 mentions/chunk vs 4.00 per-chunk on the same population; an
orchestrator parity gate (floor 0.70) stopped the run after 176 chunks.
A 3-passage probe measured 2.99 (75%). Decision: per-chunk for the full
corpus (sticky deficit beats renewable quota), batched kept for
low-stakes bulk at N<=3.

## Notes

- Strengthening the batch instruction ("be exhaustive per passage") was
  not tested here; it may lift the curve but re-measure, never assume.
- Related: audit-cheap-output-before-expensive-downstream-step (the
  general gate-before-spend principle); llm-content-extraction-density-
  aware-volume (density vs content length within ONE call).
