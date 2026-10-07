---
name: webgpu-tsl-compute-storage-buffer-limit
description: |
  three.js WebGPURenderer / TSL compute kernel silently does nothing, and an e2e test of the effect passes
  anyway. Use when: (1) the console shows "THREE.WebGPURenderer: Uncaptured WebGPU GPUValidationError: The
  number of storage buffers (9) in the Compute stage exceeds the maximum per-stage limit (8)" or "Compute
  pipeline creation failed (computePipeline_compute): [Invalid BindGroupLayout (unlabeled)] is invalid due to
  a previous error", (2) a particle system built from several instancedArray / storage buffers shows nothing
  while CPU-side probes say it ran, (3) you are writing Playwright tests for GPU effects and need them to fail
  on GPU errors. Covers the 8-buffer default limit, packing into vec4 buffers, and failing tests on GPU
  console errors.
author: Claude Code
version: 1.0.0
date: 2026-09-28
---

# WebGPU compute: the storage-buffer limit and silent failures

## Problem
Every `instancedArray(...)` (or `storage(...)`) a TSL compute kernel reads or writes is one storage-buffer
binding. WebGPU's default `maxStorageBuffersPerShaderStage` is 8. A kernel that binds 9 fails pipeline
creation. three.js only logs it; the frame loop keeps going, CPU-side bookkeeping (probes, counters) still
advances, and the effect is simply absent. An e2e test that checks a probe ("a burst was emitted") passes.

## Context / Trigger Conditions
- TSL compute particles with many per-particle attributes (position, velocity, colour, life, size, seed, ...)
  each in its own `instancedArray`.
- Console, as seen in headless Chrome on an M-series Mac:
  `The number of storage buffers (9) in the Compute stage exceeds the maximum per-stage limit (8). This
  adapter supports a higher maxStorageBuffersPerShaderStage of 10, which can be specified in requiredLimits`
  followed by cascades: `Invalid BindGroupLayout`, `Invalid ComputePipeline "computePipeline_compute"`,
  `Invalid CommandBuffer from CommandEncoder "computeGroup_..."`.

## Solution
1. **Pack attributes into vec4 buffers.** Put position + life in one vec4, velocity + size in another,
   colour + seed in a third, and so on, and keep each kernel at 8 bindings or fewer. Kernels that bind fewer
   arrays (a clear kernel) are fine; the limit is per kernel (per stage).
2. **Or raise the limit deliberately**, only if the adapter allows it:
   `new WebGPURenderer({ requiredLimits: { maxStorageBuffersPerShaderStage: n } })`. It is not portable (the
   default device, and other GPUs, may only offer 8), so prefer packing.
3. **Make the tests fail on any error the page reports**, or they pass vacuously. A filter on GPU validation
   text alone is not enough: TSL build errors are logged as `THREE.TSL: …`, and uncaught exceptions arrive as
   Playwright's `pageerror`, not as console messages.
   ```ts
   const errors: string[] = []
   page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
   page.on('pageerror', (e) => errors.push(String(e)))
   // ... drive the effect ...
   expect(errors).toEqual([])
   ```
   Put it in a shared fixture for every spec that exercises GPU effects. It still cannot see a kernel that
   builds and runs but computes nothing useful: pair it with stills, or a pixel sample at the effect's spot.
4. Keep the usual TSL compute hygiene: create kernels and materials once per app or canvas and warm them at
   load (three.js caches a pipeline per ComputeNode instance, mrdoob/three.js#32735). Never read the GPU back
   in production code; test through probes of what was emitted, plus stills.

## Verification
With the console check in place, the test goes red with the limit error. After packing, it goes green, and
the effect is visible in stills.

## Example
Chess Explosion, 28/09/2026 (`src/fx/CaptureSparks.tsx`): the capture sparks' throw kernel bound 9
instancedArrays. The first e2e run was green, but no sparks were drawn. The fork made the spec fail on GPU
console errors, saw it red for that reason, packed the state into 7 vec4 buffers, and got 5/5 green with
sparks in the stills.

## Notes
- Other per-stage limits worth knowing: `maxStorageBuffersPerShaderStage` (8), `maxSampledTexturesPerShaderStage`
  (16), `maxComputeInvocationsPerWorkgroup` (256), `maxComputeWorkgroupSizeX` (256). Query
  `renderer.backend.device.limits` in the browser.
- The WebGL2 fallback runs compute through transform feedback, with its own limits; test it separately, or
  skip the effect there.
- Related: `r3f-webgpu-playwright-gpu-perf` (frame-time tests), `vite-worktree-reloads-open-pages`.

## References
- WebGPU spec, limits: https://www.w3.org/TR/webgpu/#limits
- three.js issue on per-ComputeNode pipeline caching: https://github.com/mrdoob/three.js/issues/32735
