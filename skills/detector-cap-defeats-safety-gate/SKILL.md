---
name: detector-cap-defeats-safety-gate
description: |
  Constraining an upstream detector's output space to the expected answer
  silently disables downstream validation gates that exist to catch
  violations of that expectation. Use when: (1) passing max_speakers /
  max_clusters / num_classes / top_k = <expected count> into a model whose
  output feeds a validator, (2) a gate's rejection branches are tested but
  seem unreachable in production, (3) reviewing "elimination" or
  "by-exclusion" logic (the leftover cluster/class IS X) for soundness.
  The fix is to leave the detector unconstrained and let the gate reject.
author: Claude Code
version: 1.0.0
date: 2026-07-16
---

# Detector cap defeats safety gate

## Problem

A k-known speaker-elimination gate (council-of-thinkers PR #275) validated:
"exactly k+1 diarisation clusters, k resolve to expected speakers, top-(k+1)
must cover >=90% of speech" — with tests proving it rejects extra voices.
The wiring then called the diariser with `max_speakers = k+1`. The pipeline
merges any real extra voice (ad read, in-episode clip, cameo) into one of
the k+1 clusters, so the gate's coverage/extra-cluster rejections became
mathematically unreachable: cluster count could never exceed k+1, coverage
was always 1.0. "The leftover cluster is the guest BY ELIMINATION" degraded
from verified accounting into an unchecked assumption — and a contaminated
cluster would be auto-enrolled as a voice identity.

## Rule

When a downstream gate's job is to detect violations of an expectation,
the upstream model must NOT be constrained by that same expectation.
Capping fails silent (violations get merged/absorbed into valid-looking
output); an uncapped detector + gate fails safe (violation surfaces, gate
rejects, exception logged). Grep for the pattern: any `max_*=len(expected)`
or `top_k=expected_n` feeding a validator.

## Verification

1. Arithmetic reachability: for each gate rejection branch, ask "can the
   upstream output ever trigger this in production?" If a branch is only
   reachable in unit tests (which stub the detector), the wiring defeats it.
2. Add a source-level tripwire test: assert the capping expression does not
   exist in the wiring (e.g. `assert "len(expected) + 1" not in src`), plus
   one end-to-end test where the stubbed detector returns an extra item and
   the gate must reject.

## Notes

- Caught by an adversarial review pass, not by the author or the (green,
  thorough) gate unit tests — unit tests of the gate cannot see the wiring.
- The legitimate use of such caps is accuracy/perf tuning where no
  downstream validation depends on seeing the overflow; document which case
  you are in at the call site.
