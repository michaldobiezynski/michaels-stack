---
name: swap-apis-construct-before-destroy
description: |
  Ordering rule for delete-then-add "swap" APIs (replace an entity's rows/
  files/nodes atomically-ish without transactions): build and validate the
  COMPLETE replacement before destroying anything. Use when: (1) writing or
  reviewing any write path shaped like delete(old) -> transform -> add(new)
  over LanceDB, object stores, graph DBs, or files, (2) a bulk migration
  driver wraps such a path in a broad try/except-and-continue, (3) tests stub
  the production mutation path entirely. Trigger symptom of the failure mode:
  entities silently vanish during a batch run and are never retried because
  their absence reclassifies them as "nothing to do".
author: Claude Code
version: 1.0.0
date: 2026-07-03
---

# Swap APIs: construct before destroy

## Problem

A swap API deletes the old rows first, then builds the replacements. Any
failure between the delete and the add (schema-mapping KeyError, embed/API
failure, crash) destroys data it never replaced. Inside a batch driver with
per-item error handling, the loss is SILENT (quarantine-and-continue) and
often PERMANENT: with the rows gone, the next run classifies the item as
"no data -> skip", so nothing ever retries it.

Observed for real (council-of-thinkers PR #267 review, adversarially
reproduced): a shorts reprocess path fed lance rows reshaped with the wrong
column names into `write_chunks_for_episode`, which did
`table.delete(episode)` -> paid embed -> `_row_from_chunk` KeyError -> no
add. Every episode reached would have been wiped; blast radius 1,370.

## Rules

1. In the swap API: build the full replacement (including expensive
   transforms like embedding) and validate it BEFORE the delete. The delete
   and add should be adjacent final steps.
2. In multi-store swaps (e.g. vector store + graph), order the stores so the
   RESUME PREDICATE flips last: do the side-effects whose failure is
   self-healing first, and the write that marks the item "done" last.
3. Tests that monkeypatch the production mutation path prove nothing about
   it. Add ONE roundtrip test that drives real data through the real write
   path against a tmp store (tmp LanceDB dir + stub embedder is cheap).
4. Batch drivers with except-and-continue turn per-item bugs into corpus
   sweeps: check what a failure AFTER the destructive step leaves behind,
   and whether the next run retries or skips the damaged item.

## Verification

Simulate the mid-swap failure in a tmp store: force the transform to raise
after the point where the old code deleted; assert the entity still has its
rows. Then run the happy path and assert replacement + resume-predicate flip.
