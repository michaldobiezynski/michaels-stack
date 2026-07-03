---
name: audit-cheap-output-before-expensive-downstream-step
description: |
  In a multi-stage pipeline where a cheap/reversible stage feeds an
  expensive/irreversible one, validate the cheap stage's OUTPUT QUALITY before
  spending on the downstream stage — even when the cheap stage "ran
  successfully". Use when: (1) an ML/heuristic stage (diarisation, OCR,
  classification, extraction) produces output that a later stage consumes at
  real cost (LLM calls, paid embeddings, long compute, data you'll act on);
  (2) you have a sanity-check or human-audit available but it feels like a
  formality to run "after everything's done"; (3) you're tempted to run the
  full pipeline end-to-end and check accuracy at the end. The trap: "the stage
  completed + the data is internally consistent" is NOT "the stage is
  accurate". Running the expensive downstream step on low-accuracy upstream
  output wastes the spend and you redo it. Cost the audit gate FIRST.
author: Claude Code
version: 1.0.0
date: 2026-05-29
---

# Audit the cheap, reversible output before the expensive downstream step

## Problem

A pipeline looks like: `cheap+reversible stage  →  expensive/irreversible stage`.
For example:
- diarisation (local, re-runnable) → concept-graph re-extraction (paid LLM, ~$60)
- OCR/classification (cheap) → bulk DB writes / downstream analytics you act on
- a heuristic relabel (free) → re-embedding + index rebuild (paid + slow)

The cheap stage runs, exits 0, and its output is **internally consistent**
(counts line up, the schema validates, the graph matches the table). It is
tempting to treat "it ran cleanly" as "it's correct" and immediately spend on
the downstream stage — then audit accuracy at the very end.

That's the trap. "Ran cleanly + self-consistent" ≠ "accurate". When the audit
finally runs and the upstream accuracy is poor (e.g. a diariser scoring 3/8 on
hand-checked cases), the expensive downstream work was done on bad input and
must be redone. The spend is wasted.

Real instance: a diarisation rebuild produced a self-consistent corpus, so the
concept graph was re-extracted (~$60 of LLM calls) — and only *then* was the
attribution audited, scoring 3/8. The graph had been built on wrong
attribution; it had to be patched/rebuilt. Auditing the (free, reversible)
attribution first would have caught it before any spend.

## Context / trigger conditions

- A stage's output feeds something that costs real money, time, or is hard to
  undo (paid API calls, embeddings, deploys, irreversible writes, acting on it).
- The upstream stage is ML/heuristic, so "it ran" says nothing about accuracy.
- A validation exists (a hand-audit set, a golden sample, a spot-check script)
  but it's slotted "for the end".

## Solution

Sequence the gate before the spend:

1. Run the cheap/reversible stage.
2. **Run the accuracy audit on its output now** — the hand-audited sample, the
   golden set, the spot-check. Cost it as a required gate, not a postscript.
3. Only if it clears the bar, run the expensive downstream stage.
4. Keep the upstream output reversible until the audit passes (snapshot/backup),
   so a failed audit means "re-tune and re-run upstream", not "redo the spend".

If the audit fails, you've spent ~nothing and you iterate on the cheap stage
(tune thresholds, re-run) until it passes — *then* pay for downstream once.

Corollary: when the downstream step IS needed and upstream later improves, diff
old-vs-new upstream output and do the **minimal** downstream update (e.g. only
re-process changed items via skip-existing + patch), not a full re-spend.

## Verification

After adopting this ordering: the expensive stage runs exactly once on
validated input. If you find yourself re-running a paid stage because the input
was wrong, the gate was in the wrong place.

## Notes

- "Internally consistent" checks (row counts match, schema validates, graph ↔
  table agree) are necessary but NOT sufficient — they verify plumbing, not
  correctness. An accuracy audit needs ground truth (listening, reading,
  labelled samples), not just consistency.
- This is the pipeline-ordering case of "verify before you act, and make the
  verification cheap and early".
- Related: keeping a backup of the upstream output makes the whole loop safe to
  iterate (re-tune → re-apply → re-audit) without re-paying downstream.
