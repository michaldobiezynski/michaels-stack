---
name: pytorch-mps-training-allocator-paging-slowdown
description: |
  Diagnose and fix a progressive ~10x training slowdown on PyTorch MPS (Apple
  Silicon) caused by the caching allocator hoarding variable-shape buffers until
  macOS pages the GPU working set. Use when: (1) MPS training starts fast then
  decays to a stable ~10x-slower plateau within the first 5-15 steps, (2) batches
  have variable shapes (variable-length audio/text) and the machine has unified
  memory, (3) you need to tell memory pressure from thermal throttling on a Mac,
  (4) PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True is set but has no effect.
  Fix: torch.mps.empty_cache() after each optimizer step. Diagnose by logging
  torch.mps.driver_allocated_memory() vs current_allocated_memory().
author: Claude Code
version: 1.0.0
date: 2026-08-27
---

# PyTorch MPS Training: Allocator Hoarding Causes Paging Slowdown

## Problem
Training on Apple Silicon via MPS degrades from healthy throughput to ~10x slower
within the first handful of steps, then plateaus there. Loss and gradients stay
healthy; only speed collapses. With variable-length batches, the MPS caching
allocator keeps a cached buffer set per encountered shape and never returns freed
blocks to the OS, so Metal driver memory grows far past physical RAM and macOS
starts compressing/paging the GPU-shared working set.

## Context / Trigger Conditions
- First 2-3 steps run at full speed; by step ~10 throughput has stabilised ~10x lower
- Batches vary in shape step to step (padded audio/text of varying lengths)
- Observed on an M5 Pro 64 GB, torch 2.13, 316M-param model: live tensors flat at
  6.7 GB while driver-allocated grew 27 -> 48 -> 67 -> 72 GB in five steps, step
  time tracking the growth exactly
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (the CUDA fix for the same
  fragmentation problem) silently does nothing on MPS
- Larger micro-batches make it worse, not better

## Solution
1. **Diagnose first** (distinguishes from thermal throttling): log both counters
   each step:
   ```python
   drv = torch.mps.driver_allocated_memory() / 2**30   # what Metal holds
   cur = torch.mps.current_allocated_memory() / 2**30  # live tensors
   ```
   Paging failure mode: `drv` >> `cur` and climbing while it/s decays. Thermal:
   both flat, speed decays over minutes not steps (check `pmset -g therm`).
2. **Fix**: release the cache after each optimizer step:
   ```python
   optimizer.step()
   if device.type == "mps":
       torch.mps.empty_cache()
   ```
   Per-step cost is unmeasurable (allocation is cheap relative to a training step);
   driver memory stays bounded a few GB above live tensors.

## Verification
Rerun the same short benchmark: sustained it/s should match the first-3-steps rate
with zero decay, and `drv` should hover near `cur` plus model overhead instead of
exceeding physical RAM. Measured recovery: 0.008 -> 0.11 it/s sustained (12x), 25
steps in 3.5 min instead of 31 min.

## Example
kyutai-labs/pocket-tts training on an M5 Pro MacBook (Aug 2026): fix committed as
a per-step `empty_cache()` guarded on `device.type == "mps"`, plus `mps drv/cur`
figures on the step log line so the failure mode is visible in any future run.

## Notes
- A wrapper-launched process (`uv run python ...`) defeats `ps -o rss= -p $!`
  memory sampling: `$!` is the wrapper's PID, not python's. Log memory from inside
  the process instead.
- `PYTORCH_MPS_HIGH_WATERMARK_RATIO` is the env-var alternative if you cannot edit
  the loop, but per-step `empty_cache()` was sufficient and simpler.
- Multi-process training is not an MPS option (NCCL is NVIDIA-only); Apple Silicon
  exposes exactly one GPU device regardless of GPU core count.
