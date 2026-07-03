---
name: validate-device-equivalence-before-trusting-gpu-bug
description: |
  When a model/library is reputed to "silently corrupt output on GPU/MPS/CUDA"
  (from an issue tracker, a code comment, or a review finding) and you've pinned
  it to CPU as a result, EMPIRICALLY re-validate that claim on your exact stack
  before forgoing the speedup. Such bugs are version-specific and often fixed in
  later releases. Use when: (1) a pipeline pins CPU citing a known GPU bug
  (e.g. pyannote-audio#1337 "MPS corrupts diarisation timestamps"), (2) a CPU
  run is painfully slow (hours) and the machine has a capable GPU/MPS sitting
  idle, (3) a comment says "CPU is non-negotiable / don't optimise to MPS",
  (4) you're about to run a long batch and want a safe speedup. The test: run a
  SHORT input on both the safe (CPU) and fast (GPU/MPS) device, compare the
  outputs numerically; if they match within tolerance, the bug is absent on your
  stack and the fast device is safe. On an Apple M5 Pro with pyannote 4.0.4 +
  torch 2.12 this turned a ~20-40h CPU job into ~2h (8x) with 0.00s deviation.
author: Claude Code
version: 1.0.0
date: 2026-05-29
---

# Validate device equivalence before trusting a "GPU is broken" claim

## Problem

A library has a reputation for silently corrupting output on a GPU backend, so
the codebase pins CPU:

```python
# MPS silently corrupts segment timestamps (pyannote-audio#1337) -> CPU only.
pipe.to(torch.device("cpu"))
```

Then a real batch run is CPU-bound and takes *hours* (e.g. 29.6h of audio at
~0.5x realtime ≈ 20-40h) while a capable GPU/MPS sits idle. The "CPU only" rule
is treated as permanent — but these bugs are **version-specific**. #1337 was a
real corruption on older pyannote/torch; it does not necessarily exist on your
installed versions. Blindly trusting the old claim can cost a multi-day run for
no reason. Blindly trusting MPS can silently poison results. Either extreme is
wrong — the answer is to **measure**.

## Context / trigger conditions

- A pipeline pins CPU and cites a known GPU/MPS/CUDA correctness bug.
- A long batch is CPU-bound and a GPU/MPS is available.
- A review or comment says "device X is non-negotiable; don't optimise to GPU".
- The corruption (if present) is *silent* — no error, just wrong numbers — so
  you can't detect it by "did it crash". You must compare outputs.

## Solution

Run the **same short input** on both devices and compare outputs numerically.
Equal within tolerance ⇒ the bug is absent on your stack ⇒ use the fast device.

```python
import time, torch
def run(device):
    pipe = Pipeline.from_pretrained(MODEL, token=tok).to(torch.device(device))
    t = time.time(); out = pipe(CLIP); return time.time()-t, extract(out)

cdt, cpu = run("cpu")
mdt, mps = run("mps")
# Compare the MEANINGFUL output, not labels (cluster/class labels are unstable
# across runs). For diarisation: segment count, speaker count, total coverage,
# and per-boundary nearest-match deviation.
same_structure = (len(cpu)==len(mps) and nspk(cpu)==nspk(mps)
                  and abs(coverage(cpu)-coverage(mps)) < eps)
max_dev = max(min(abs(b-y) for y in bounds(mps)) for b in bounds(cpu))
print("SAFE" if same_structure and max_dev < 0.5 else "UNSAFE", f"{cdt/mdt:.1f}x")
```

Decision rule:
- **match within tolerance** → fast device is safe; use it (and leave CPU as the
  documented portable default + an opt-in `--device` flag, since the bug may
  still bite a *different* machine/version).
- **diverges** → the bug is live on your stack; stay on CPU.

## Verification

Concrete result (pyannote `speaker-diarization-community-1`, 4.0.4 + torch 2.12,
Apple M5 Pro), 180s clip: CPU 88s vs MPS 11s (**8.1x**); identical 18 segments /
3 speakers / 175.8s coverage; **max boundary deviation 0.00s**. The #1337
corruption was simply not present → the full corpus dropped from ~20-40h to ~2h.

## Notes

- Compare the **semantic output**, not internal labels. Diarisation cluster
  labels (`SPEAKER_00` vs `SPEAKER_01`) are not stable across runs, so diff on
  timestamps/counts/coverage, not on label equality.
- Keep CPU the committed default and gate the fast device behind a flag with a
  comment recording your validation (stack + deviation). Portability: another
  machine or a version bump may reintroduce the bug — the next operator should
  re-run the equivalence check, not inherit your "MPS is fine" conclusion blind.
- This is a specific instance of "verify, don't assume": a documented-as-broken
  path is a hypothesis to test on your stack, not a permanent law.
- Same method applies to CUDA/ROCm "this op is non-deterministic/wrong on GPU"
  claims, and to mixed-precision (fp16/bf16) "loses accuracy" assumptions.
