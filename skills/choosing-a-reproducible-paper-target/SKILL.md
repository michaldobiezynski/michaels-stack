---
name: choosing-a-reproducible-paper-target
description: |
  Pick a TRACTABLE paper/experiment to reproduce on the hardware you actually have, before
  sinking hours into it. Use when: (1) choosing which ICML-2026-agent-repro paper (or any
  paper) to reproduce from a large list, (2) deciding if a repo that "runs on my machine" can
  actually reproduce its headline results, (3) a candidate's code runs on CPU but you are
  unsure the numbers are reachable without a GPU, (4) triaging Apple-Silicon feasibility for a
  sparse-graph / GNN model. Core lesson: "the code runs on CPU" does NOT mean "the claims are
  CPU-reproducible" — screen by the CLAIMS' compute needs, and fetch the challenge's registry
  claims before committing.
author: Claude Code
version: 1.0.0
date: 2026-07-22
---

# Choosing a reproducible paper target (screen by claim compute, not code)

## The trap
A repository can install, import, and train one step on your CPU — and still be impossible to
*reproduce* there, because its headline numbers require GPU-scale training the code merely
*supports*. Selecting on "does the code run?" wastes hours. Select on "do the CLAIMS' compute
requirements fit my hardware?"

**Worked counterexample (verified 22/07/2026):**
- **GCIB** (multi-behavior recsys GNN): code ran fine on CPU (`--device cpu`), datasets bundled,
  small model — looked GREEN. But its registry claims are *train 7 algorithms × 4 datasets to
  convergence*, and the per-batch full-graph sparse recompute is **~8 min/epoch on CPU vs 30 s
  on GPU (~16×)**. Full reproduction = tens of CPU-hours. Effectively GPU-bound. REJECTED.
- **eNMF** (nonnegative matrix factorization): pure numpy/scipy, matrices ≤500×400, every
  experiment runs in **seconds** on CPU, and even its *timing* claim is a relative CPU-vs-CPU
  comparison (faithful on any hardware). Claims match the compute. SELECTED.

Same "GREEN code" surface; opposite claim-level feasibility.

## Screening method (in order; stop at the first hard blocker)
1. **Fetch the paper's registry/claim list FIRST**, not your own idea of the claims. For the
   ICML challenge that is `claims_anchored.json` keyed by orid (see
   [[icml2026-agent-repro-logbook-submission]]). Read every claim and label its compute:
   - *audit / synthetic-demo* (mechanism, algorithm-block, math identity) → CPU-trivial, $0.
   - *small numerical experiment* (matrix factorization, small-graph node-classification on
     Cora-scale, tabular, bandits, convergence curves) → CPU-feasible.
   - *train a model to convergence* → estimate epochs × per-epoch time on YOUR hardware.
   - *train a 7B+/multimodal/diffusion model, or generate data with a paid API* → GPU/$ — not a
     local CPU job.
2. **Public code + bundled/small data** is the make-or-break. No official repo (only an
   anonymous double-blind snapshot, or nothing) → RED, skip. Bundled standard datasets → good.
3. **Measure, don't guess, the per-epoch/per-run time** with a 2-epoch (or single-run) smoke on
   the real hardware. Multiply by realistic convergence epochs × number of runs the claims need
   (datasets × ablations × sweeps). If that is tens of hours, it is GPU-bound regardless of what
   one epoch costs.
4. **Prefer papers whose compute is inherently small**: optimization/numerical-method papers
   (NMF, convex solvers), classical ML, theory-with-small-experiments, small-graph GNNs on
   Cora/Citeseer/Pubmed, recommender/CF on small datasets. These reproduce cleanly and cheaply.

## Apple-Silicon specifics
- **MPS has no sparse-matmul kernel.** Any model whose core is `torch.sparse.mm` (LightGCN-style
  GCF, multi-behavior GNNs, most graph-CF) **cannot use the Mac GPU** — with
  `PYTORCH_ENABLE_MPS_FALLBACK=1` the sparse ops silently run on CPU and then mix with MPS
  tensors → `RuntimeError: expected all tensors on the same device, mps:0 and cpu`. Even if you
  patch the device coercion, the expensive sparse part still runs on CPU, so there is no real
  speedup. Such models are CPU-bound on a Mac; the only true GPU path is a CUDA machine / HF Job.
- Dense small models (MLPs, small transformers, matrix ops) DO benefit from MPS.

## Fast candidate filter over a large registry
Score title+abstract: reject on heavy keywords (`llm`, `large language model`, `multimodal`,
`diffusion`, `text-to-image/video`, `3d`, `nerf`, `7b/13b/70b`, `gpt-4`, `foundation model`,
`world model`); favour light ones (`nmf`, `matrix`, `bandit`, `regret`, `convex`, `convergence`,
`graph neural`+small benchmarks, `tabular`, `kernel`, `theorem`, `recommend`). Then fan out one
scout per top candidate to verify **public code + bundled data + a measured smoke run**, and
return a GREEN/YELLOW/RED verdict with an effort estimate. Rank GREEN-with-verified-run first.

## Verification that you picked right
- Registry claims read and each labelled by compute tier.
- Public code cloned + pinned; a smoke run *measured* on your hardware (not estimated).
- At least the majority of claims land in CPU-trivial / CPU-feasible tiers.
- No claim's compute silently assumes a GPU you don't have.

## References
- Challenge submission mechanics + registry claims: [[icml2026-agent-repro-logbook-submission]]
- SELFRec-family CPU patches (a recsys example): [[selfrec-recsys-reproduction-cpu-patches]]
