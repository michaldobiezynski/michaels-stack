---
name: selfrec-recsys-reproduction-cpu-patches
description: |
  Reproduce a SELFRec-based graph-collaborative-filtering / recommender paper (Coder-Yu/
  SELFRec and its forks: geon0325/NT-SSM, LightGCN/SimGCL/NCL variants, SGL, XSimGCL, etc.)
  on a CUDA-less machine (Apple Silicon CPU/MPS). Use when: (1) `python main.py --model_name
  X ...` crashes with a CUDA/device error on a Mac, (2) it raises `NameError: name '<Model>'
  is not defined` from `eval(recommender).execute()` in SELFRec.py, (3) a `torch.sparse.
  FloatTensor` deprecation/warning, (4) an NT-/proposed variant scores BELOW its own baseline
  (e.g. NT-BPR < BPR) despite matching the paper on the other objective. Covers the three
  must-apply clone patches and the per-objective-hyperparameter gotcha, plus how to verify.
author: Claude Code
version: 1.0.0
date: 2026-07-21
---

# Reproducing SELFRec-family recsys papers on Apple Silicon (CPU)

## Problem
SELFRec (Coder-Yu) and its many forks are written for CUDA GPUs and older Python. Running
one on a CUDA-less Mac needs code patches that are NOT in any README, and two of the failures
appear only when you actually run the training loop — static review misses them.

## Context / Trigger conditions
- Repo built on SELFRec: `main.py` + `SELFRec.py` + `base/` + `model/graph/*.py`
  (`LightGCN`, `SimGCL`, `NCL`, and `_NT`/proposed variants), datasets under `dataset/<name>/
  {train,valid,test}.txt`, per-model config via CLI args (no `conf/` in newer forks).
- Symptoms: a `.cuda()` crash; `NameError` from `eval(recommender).execute()`; a
  `torch.sparse.FloatTensor` deprecation; or a proposed variant underperforming its baseline.

## The three clone patches (apply to a pinned checkout, reproducibly)

1. **Hardcoded `.cuda()` everywhere → a device constant.** SELFRec graph models call bare
   `.cuda()` (models, sparse adjacency, noise tensors, faiss centroids). On a CUDA-less box
   they crash. Insert one `_NTSSM_DEVICE = torch.device("cpu")` after the module-level
   `import torch` and replace every `.cuda()` with `.to(_NTSSM_DEVICE)`. Run **CPU, not MPS**
   — the core op is `torch.sparse.mm`, which is unreliable/slow on MPS; 64 GB unified RAM is
   ample. (`grep -rn "\.cuda()"` to inventory; a LightGCN path is ~4 sites, whole repo ~20.)

2. **`SELFRec.execute()` `exec`+`eval` import → `importlib`.** The upstream does:
   ```python
   exec('from model.'+type+'.'+name+' import '+name)   # exec into function locals
   eval(name+'(self.config,...)').execute()             # eval can't see it
   ```
   Under **Python 3 this NameErrors**: `exec` at function scope writes to a locals dict that
   `eval` does not resolve (function-local namespaces are optimized; works in Py2, not Py3).
   Fix — robust across versions:
   ```python
   import importlib
   module = importlib.import_module('model.' + self.config.model_type + '.' + self.config.model_name)
   getattr(module, self.config.model_name)(self.config, self.training_data,
           self.valid_data, self.test_data, **self.kwargs).execute()
   ```

3. **Deprecated sparse constructor.** `base/torch_interface.py` builds the adjacency with
   `torch.sparse.FloatTensor(i, v, shape)`; modern torch warns/errors. Replace with
   `torch.sparse_coo_tensor(i, v, shape)` (a benign "sparse invariant checks disabled"
   UserWarning remains — ignore it).

## The per-objective hyperparameter gotcha (silent underperformance)

The paper's **appendix hyperparameter table** (e.g. NT-SSM's Table 5) lists **different
optimal coefficients for each objective AND each dataset** — NT-BPR and NT-SSM do not share
alphas, and LastFM differs from ML-1M. A runner that reuses one objective's values for the
other makes that variant underperform *its own baseline* (symptom: NT-BPR < BPR while NT-SSM
matches the paper). Read the appendix table per (objective, dataset); do not copy the value
that happens to be in `run.sh` (which usually pins one dataset/objective only).

**The plain-SSM baseline is the worst case of this** (verified 22/07/2026, NT-SSM clone):
the paper and repo disclose NO temperature for the SSM baseline at all; the shared CLI
default `--tau 0.2` reproduces every NT variant but leaves plain SSM far below its Table 1
row (ML-1M NDCG@20 0.202 vs 0.2648, early-stops by epoch ~14). SSM is strongly
tau-sensitive: a small grid on validation NDCG@20 fixes it — **tau = 0.1 reproduces the
ML-1M SSM baseline within tolerance (0.26670 vs 0.2648 ± 0.0024)**; 0.05 overshoots
(0.281), 0.15/0.2 undershoot. On LastFM no tau reaches the band (single seed, smallest
dataset) — report honestly; NT's gain over the paper's printed baseline still matches.

## Rerun / clone-code gotchas (cost real debugging time)

- **`Exists!` guard**: each model refuses to run if `logs/<config_name>.txt` already
  exists — it prints `Exists!` and exits 0 *silently succeeding*. Rerunning any config
  (e.g. for timing) requires changing something in the config name; `--seed <new>` is the
  cheapest (seed is in the filename). Symptom: a "run" that finishes in seconds with no
  epoch rows. Never pipe run output through `grep` without checking the exit code — the
  pipe masks both the crash and the `Exists!` skip.
- **Hardcoded author paths in `_NT` variants**: `SimGCL_NT.py` (and possibly others)
  pickles embeddings to `/data/geon/PT-GCF/embs/...` and crashes with FileNotFoundError
  *after* training completes. The metrics log is already fully written — the run's
  results are usable; parse the log and ignore the crash (or patch the path).
- **Dead code in `LightGCN_NT.ssm_loss`**: lines ~182-188 compute a global-cosine
  positive term that is never used (reassigned before use) — don't let it confuse a
  loss-formula audit; the live path is the four bilinear terms over a shared denominator.

## Verification (this is what catches 1, 2, and the hyperparameters)

- **2-epoch smoke run first.** `python main.py ... --epoch 2`. This surfaces the `.cuda()`
  crash and the `exec/eval` NameError in seconds; a 45-min full run would die at second zero
  on the same errors. It also gives the per-epoch time (LastFM ~4.5 s/epoch, ML-1M ~36 s/
  epoch on an M-series CPU) to size the real run.
- **Full run + ordering check** catches hyperparameter mismatches: compare the proposed
  variant against its baseline (NT-SSM > SSM, NT-BPR > BPR) and against the paper's Table 1
  within `paper_mean ± max(5%, 3·std)`. A variant below its own baseline ⇒ wrong per-objective
  hyperparameters (patch #4 above), not a repro failure.

## Facts worth knowing about SELFRec model selection & logs
- Each backbone early-stops on **best VALIDATION NDCG@20, patience 10**, and the code that
  does this lives in the model file (`LightGCN_NT.py` etc.), NOT the `base/graph_recommender.py`
  `bestPerformance` path (dead code for these models — don't grep only the base class).
- Per-epoch log rows in `logs/<config>.txt`: `epoch,split,'',R@k1,N@k1,R@k2,N@k2,R@k3,N@k3`
  where cutoffs come from `--item_ranking` (default 10,20,40); no header; values are
  `round(x,5)` so trailing zeros are stripped (parse as float, derive column index from
  `--item_ranking`, don't hardcode).
- `main.py` **skips training if `embs/<config>.pkl` already exists** (`exit(0)` "Exists!") —
  clear stale `embs/`/`logs/` (and any shipped reference artifact) before a real run, or it
  silently no-ops.

## Notes
- Python 3.13 has reliable torch/numba wheels; 3.14 is risky — pin the venv to 3.13.
- Datasets are usually bundled (`dataset/<name>/`), 7:1:2 split; no download needed.
- Apply all patches as a reproducible script against the pinned commit, not hand-edits to an
  untracked checkout — the clone is regenerated by setup.

## References
- SELFRec: https://github.com/Coder-Yu/SELFRec  (base framework; the `.cuda()` and exec/eval
  patterns originate here, so these patches apply to the whole fork family)
