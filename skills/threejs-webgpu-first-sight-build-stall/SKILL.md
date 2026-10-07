---
name: threejs-webgpu-first-sight-build-stall
description: |
  Find what a three.js WebGPURenderer builds in a stalled frame, and tell a first-sight shader build from the
  feature a frame-gap test is about. Use when: (1) a Playwright frame-gap check ("worst frame < 1.6x median")
  fails on one 33-50 ms frame at a repeatable time after the test teleports a followed subject or moves the
  camera, (2) the stall survives halving the particles/effects the test is about (so it is not fill-rate),
  (3) a camera change (closer, steeper, centred follow view) made an unrelated test start dropping frames,
  (4) tests skip an opening/overview shot (?intro=0 style) that real visits get, (5) several InstancedMeshes
  each compile their own vertex program. Covers: wrapping backend.createNodeBuilder/createProgram/
  createRenderPipeline/createTexture via a page.route-patched module, splitting scenarios to attribute the
  stall, and three's instance-count-in-shader and compileAsync-frustum gotchas.
author: Claude Code
version: 1.0.0
date: 2026-09-28
---

# First-sight build stalls in three.js WebGPU

## Problem
A frame-gap test for effect X ("nightfall drops no frame") fails on a single 33-50 ms frame. Shrinking X
changes nothing. Frustum culling explains it: three builds an object's TSL node material (a few ms of JS
each) and its GPU pipeline the first time the object is inside the camera's frustum, not at load. If the
test teleports the subject and the follow camera glides somewhere it has never looked, a burst of
first-sight builds lands inside the measurement window. X is innocent.

## Solution
1. **Split the scenario before theorising** (run each 4-6 times, headless, one worker):
   - the teleport/camera move alone, with no action;
   - the teleport, wait for the camera to settle, then the action;
   - both at once, as the failing test does.
   If "settled, then the action" is clean and "the move alone" stalls, the stall belongs to the move.
2. **Log what the renderer builds**, with times relative to the move. Expose the renderer without
   touching the repo by patching the module Vite serves:
   ```ts
   await page.route(/\/src\/world\/WorldView\.tsx/, async (route) => {
     const res = await route.fetch()
     const body = (await res.text()).replace('await renderer.init();', 'await renderer.init(); window.__renderer = renderer;')
     await route.fulfill({ response: res, body })
   })
   // in page.evaluate, after the world is ready:
   const b = window.__renderer.backend
   for (const name of ['createNodeBuilder', 'createProgram', 'createRenderPipeline', 'createTexture', 'generateMipmaps']) {
     const orig = b[name].bind(b)
     b[name] = (...a) => { log.push(`${Math.round(performance.now() - t0)}ms ${name} ...`); return orig(...a) }
   }
   ```
   For `createNodeBuilder(object)`, log `object.material.name || type`, the name chain up the parents,
   the world position (`matrixWorld.elements[12..14]`) and the geometry type. Record rAF gaps over 22 ms
   in the same page, on the same clock. A cluster of builds 4-5 ms apart ending at the slow frame is the
   answer. Throw if the patch did not apply, so the experiment cannot silently measure nothing.
3. **Check the real path.** Run the same move after the real opening (no skip flag). If the overview drew
   those objects while it held, real visits are clean and only the tests' shortcut pays.
4. **Fix the right thing.**
   - If only the test's shortcut pays: let the camera settle after the teleport before measuring, at the
     same limit. This is not a loosened check, because it removes a confound. Say so in the commit and the
     test comment, with the measurement.
   - If real play pays, draw the objects once at load (render them for the first frames with
     `frustumCulled = false`), or make equal materials share builds (below).
   - File the rest as an issue with the numbers.

## three.js facts (verified in r186 source)
- **The instance capacity is baked into the vertex shader.** `nodes/accessors/Instance.js`
  `createInstanceMatrixNode` puts the matrices in a uniform buffer when `count * 64` fits the
  uniform-buffer limit (about 1000 matrices). `WGSLNodeBuilder.js` declares it as
  `array<mat4x4<f32>, N>`. InstancedMeshes with different capacities (for example one mesh per chess
  piece type) cannot share a program: each builds its own node material, program and pipeline. The same
  capacity everywhere lets equal materials share them.
- **`renderer.compileAsync(scene, camera)` honours frustum culling** (`_projectObject` tests
  `object.frustumCulled` and `intersectsFrustum`) and skips invisible objects. It pre-builds only what that
  camera sees. With post-processing, its render context must also match the pass's target, or its
  pipelines are not the ones the frame uses.
- The shadow map's camera culls too: moving the shadow with the subject builds ShadowMaterial node
  builders on first sight. These are cheap and usually harmless.

## Verification
The failing check passes at its original limit many times in a row (here 6 of 6, worst frame 16.8 ms
against 26.7). The "move alone" experiment still shows the stall, so the finding is real and filed, not
hidden.

## Example
Chess Explosion, 28/09/2026: `study-motes.spec.ts` "nightfall drops no frame" failed in the batch with a
centred follow camera (PR #57).
- Halving the motes or the rune sparks left the stall in place.
- The teleport alone stalled at 576 ms (50 ms). Master was 0 of 5 and the camera branch 1 of 5.
- Settled first, nightfall was 0 of 4.
- The log showed about 22 builds from 498 to 586 ms: the far end's game boards, 5-6 instanced lathe
  pieces each, plus 6 canvas textures.
- The old camera had seen them at load. The tests skip the opening overview, which builds them for real
  visits (0 of 3 stalls).

Fix: the test waits for `cameraStill` after the teleport. Filed as issue #58, with the instance-capacity
fix.

## Notes
- Delete the scratch experiment specs afterwards, since page.route patches are not for committed tests.
- Related: `r3f-webgpu-playwright-gpu-perf` (GPU contention flakes, and TSL materials per component
  costing a frame), `webgpu-tsl-compute-storage-buffer-limit`, `threejs-tsl-instanced-positionlocal`,
  `r3f-loading-veil-and-opening-camera` (the opening overview that pre-draws the world).
