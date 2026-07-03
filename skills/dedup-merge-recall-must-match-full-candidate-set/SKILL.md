---
name: dedup-merge-recall-must-match-full-candidate-set
description: |
  Bug + invariant for any "recall after canonicalisation/dedup merge" metric that
  compares two sets of items (concept names, entities, labels, retrieved docs) by
  embedding similarity. Use when: (1) you compute a recall/overlap score, then add
  a clustering/merge step to collapse near-duplicate phrasings before scoring;
  (2) the "merged"/"deduped" recall comes out LOWER than the raw (unmerged) recall;
  (3) you are reviewing or writing a benchmark that reports raw vs merged recall;
  (4) an embedding-canonicalisation comparison understates a challenger model. The
  invariant: collapsing duplicates can only HOLD or RAISE recall, never lower it -
  merged < raw is always a bug.
author: Claude Code
version: 1.0.0
date: 2026-06-08
---

# Dedup-merge recall must match the deduped reference against the FULL candidate set

## Problem
You measure how well candidate set B recovers reference set A by embedding both
and counting, for each a in A, whether some b in B has cosine >= threshold
(recall). To avoid penalising B for variant phrasing of the same idea, you add a
canonicalisation-style merge: cluster near-duplicate names (cosine >= merge_thr)
within each side and score on the survivors. The merged recall then comes out
LOWER than the raw recall - which is impossible for a correct dedup and silently
understates the candidate's quality (e.g. tanking a model-quality gate).

## Context / Trigger conditions
- A benchmark/eval reporting both "raw recall" and "merged"/"deduped"/
  "canonicalised" recall, and merged < raw.
- A greedy `merge_by_embedding`-style helper that returns one REPRESENTATIVE
  index per cluster (usually first-seen), and the scorer compares
  reference-reps against CANDIDATE-reps.
- Symptom in a model comparison: "collapsing variant phrasings LOWERED the score"
  or a local-vs-cloud extraction benchmark whose merged number is the worst.

## Root cause
Merging the CANDIDATE side to representatives discards non-representative members.
If the candidate concept that actually matched a reference concept is not its
cluster's representative, it is thrown away and the reference is scored against a
DIFFERENT (non-matching) representative -> a true match becomes a miss. Example:
reference `x`; candidates `[y_rep, y_match]` where `y_match` matches `x`
(cos 0.9) but merges into first-seen `y_rep` (cos to x 0.7 < threshold). Rep-vs-rep
compares `x` only to `y_rep` -> 0% recall, though raw recall is 100%.

## Solution
Dedupe the REFERENCE side only (to remove double-counting of its own duplicates
from the denominator), and match each surviving reference item against the
**FULL candidate set**, never the candidate representatives:

    s_reps = merge_by_embedding(ref_names, ref_vecs, merge_thr)   # reference only
    merged_recall = recall([ref_vecs[i] for i in s_reps], cand_vecs)  # FULL candidates

The cosine >= threshold step already absorbs phrasing variation across sides; the
within-side merge is ONLY to collapse the reference denominator. With this,
merged_recall >= raw_recall always (collapsing reference duplicates can only
remove an item that was already a miss or already counted once).

## Verification
- Assert the invariant in a test: `merged_recall >= raw_recall` on a crafted case
  where the matching candidate is NOT its cluster representative (see below). This
  test FAILS (RED) on the rep-vs-rep implementation and passes after the fix - a
  genuine regression guard, not a tautology.
- Re-run the real benchmark: the merged number should now equal-or-exceed raw.

## Example (regression test)
```python
# x matches y_match (0.9) but y_match merges into first-seen y_rep (x..y_rep=0.7<0.8)
table = {"x":[1,0,0], "y_rep":[0.7,0.714,0], "y_match":[0.9,0.436,0]}
rep = semantic_overlap_report(["x"], ["y_rep","y_match"], FakeEmbedder(table),
                              threshold=0.8, merge_threshold=0.85)
assert rep.raw_recall == 1.0
assert rep.merged_recall == 1.0          # rep-vs-rep bug gives 0.0 here
assert rep.merged_recall >= rep.raw_recall
```

## Notes
- General invariant beyond embeddings: any "after dedup/merge" aggregate that can
  go the WRONG way versus its un-merged baseline is a bug signal - sanity-check the
  monotonic direction first, then trace it.
- Related: `calibrate-embedding-similarity-thresholds` (pick the cosine threshold
  from the embedder's real distribution) and
  `switching-llm-mid-corpus-fragments-concept-graph` (the benchmark this came from:
  comparing a local model's extraction against a cloud model's graph concepts).
- Anchor: qwen3:32b vs Sonnet on 40 chunks measured raw 66% / merged-fixed 57%
  semantic recall @cos>=0.8; the shipped rep-vs-rep metric reported 54% (< raw),
  which is what flagged the bug.
