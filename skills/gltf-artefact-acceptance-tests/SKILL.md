---
name: gltf-artefact-acceptance-tests
description: |
  Write acceptance tests that decode a built GLB/glTF in vitest or node and assert the geometry
  the runtime relies on is really there, instead of testing a table that merely claims it. Use
  when: (1) a runtime table of positions (holes, portals, spawn points, anchors) is supposed to
  match a Blender-built model and a user finds a place where it does not (a rat walking through
  a closed door, a bat through window bars), (2) you want a red-first ATDD loop for asset
  changes (test fails on the old model, passes after the rebuild), (3) you need to check an
  exported asset for open pits, bars, recesses or the absence of unused geometry. Covers GLB
  header parsing, POSITION accessor decoding with byteStride, Blender-to-glTF axis mapping, and
  how to pick vertex-box thresholds that actually discriminate (bars have vertices at their ends,
  not in the middle). Also the RUNTIME variant for animated rigs: a probe that measures skinned
  surface clearance (a fist to the chair it carries) at sub-frame clip times through three.js,
  swept by a Playwright spec, for "there is still a gap mid-strike" reports that static geometry
  tests cannot see.
author: Claude Code
version: 1.3.0
date: 2026-09-21
---

# Acceptance tests against the built glTF

## Problem
Runtime code carried a table of "holes" and "portals" while the model had no such geometry at
two of them. Unit tests of the table passed; the user saw rats pass through a door and bats
through bars. The only test that catches this reads the artefact the game loads.

## Solution
1. **Decode the GLB in the test.** Header: magic at 0, JSON chunk length at byte 12, JSON at
   20..20+len, binary chunk starts at 20+len+8. Find the node by name with a `mesh`, take each
   primitive's `POSITION` accessor, then `bufferViews[acc.bufferView]`, read `count` float32
   triples at `bin + view.byteOffset + acc.byteOffset + i*(view.byteStride ?? 12)`. Blender's
   exporter with Y-up maps Blender (x, y, z) to glTF (x, z, -y); if the game's z is "-Blender y"
   the glTF x/z are already game x/z.
2. **Assert presence where the runtime needs it**, e.g. for every hole in `RAT_HOLES` some `Holes`
   vertex within 0.3 of the mouth; for every window portal, few wall vertices in the opening box.
3. **Assert absence too**, so the model cannot grow stale decoration: cluster the `Holes` vertices
   and require every cluster to match a runtime hole.
4. **Prove the check discriminates.** A gated window scored 56 wall vertices in a 1.2 x 1.5 box
   around the opening and an open one 16 (its arch frame), but both scored 0 in a tighter core
   box, because bar vertices sit at the bar ends. Measure both classes first with a throwaway
   node script and put the numbers in the assertion (portal < 24, gated > 40) with a comment.
   Likewise a drain pit's vertices are on its rim and bar ends, never at its centre: test the
   footprint, not the centre point.
5. **Run it red first.** Add the table entry and the test, watch it fail on the current model,
   then change the Blender build, rebuild, and watch it pass. Then film the case through the
   game camera; the test proves geometry exists, only the film proves it looks right.

## Runtime skinned clearance (added 2026-09-21)
When the complaint is about an animated rig ("the queen's hands still gap from the chair mid-strike"),
decoding rest-pose vertices proves nothing: the gap lives in the posed, interpolated frames. Measure
it where the player sees it, in the running app:
1. **Probe hook on the rig.** In the component that owns the `AnimationMixer`, install
   `probe.gripGap(timeSec?)`: set `strike.time`, `strike.paused = true`, `mixer.update(0)`,
   `scene.updateMatrixWorld(true)`, then compute. Only install it in the inspect/spotlight view so
   game pieces do not fight over one hook.
2. **Skinned surface, not bone distance.** Find the `SkinnedMesh`; a vertex belongs to the part
   whose bone has its dominant `skinWeight`. Keep the triangles whose three vertices all belong to
   the carried part and their `maxEdge`. Per sample, `mesh.applyBoneTransform(i, v)` (three r151+,
   reads `bones[i].matrixWorld` directly, so no render is needed between samples) then
   `applyMatrix4(mesh.matrixWorld)`; take the hand bone's `getWorldPosition` as the fist centre and
   run `Triangle.closestPointToPoint`, skipping triangles whose nearest vertex is farther than
   `best + maxEdge·scale`. Gap = distance/scale − fist radius, clamped at 0. Divide by the mesh's
   world scale so the number is in model units.
3. **Export the radius; do not fit it.** A tenth-percentile fit of hand-owned vertex distances gave
   0.065 for the empty fist and 0.041 for the one holding a horn (the prop's vertices sit inside the
   sphere), which read as a 1.6 cm gap that was not there. Write `arm["fist_radius"]` as a glTF extra
   on the Rig node and read `userData.fist_radius`; keep the fit only as a fallback.
4. **Sweep sub-frame.** The exported clip is sampled per frame; three.js interpolates the prop's
   translation linearly while the arm chain slerps, so sample from the grab to the set-down at
   quarter-frame steps (`1/24/4`) in one `page.evaluate` loop, and assert every sample is under a
   tolerance that a viewer would not notice (0.01 model units on a 1.3-unit figure). Red first: the
   old rig scored 0.12 on all 249 samples; the fix scored 0.0000.
5. **Then film it.** A quarter-speed run (`?record=4`) through the real attack camera, a frame every
   ~120 ms from the draw to the settle, composed into a contact sheet and viewed; the number proves
   contact, the film proves it reads as a grip.
6. **"Is the environment there at all" is a pixel-band test.** For a view that should show a modelled
   room behind the subject, sample a band of the canvas where the room must be (the top 4–20% of the
   frame from a level camera) and assert its mean luminance AND spread: a bare background is flat
   (mean 4.4, spread 4.3 for 0x14120f, far darker than the hex suggests because of tone mapping, so
   measure it rather than compute it), a torch-lit wall with pillars is bright and varied (41/33).
   Keep the band clear of any HUD panel overlaid on the canvas.
7. **A marker's visibility is a before/after pixel shift, at a spot proven hidden by line of sight.**
   To show an overlay (a legal-move dot) draws through what lies on its square, sample a 3 px patch
   in a still without the marker and one with it and assert the colour distance: hidden = 0, drawn =
   100+. Three things made the first version prove nothing: (a) "a chunk within 0.2 of the centre"
   is not coverage: the centre pixel was clear, so cast a ray from the camera to the point ON THE
   MARKER'S PLANE against the rubble meshes and require the spot and its ±0.02 neighbours all hidden;
   (b) the spot must lie inside the marker's footprint (a 0.13 dot: search offsets within 0.09, never
   the ±0.1 corners at 0.14); (c) the game camera keeps gliding for ~4 s after a capture, so wait
   until a corner square holds still for 2 s and assert it did not move between the two stills.
   Pick the marker colour for contrast (red over ivory rubble shifts 110+, gold barely 20). Verify
   red first by checking out the old component into the tree and running the spec (`git show
   <sha>:path > path`, run, `git checkout -- path`), and never key a commit chain on `grep` after
   the test runner: it masks the exit code (`set -o pipefail`). Probe state published through React
   (selection, targets) lands on the next render: `select()` then wait before reading.

8. **Physics fixtures are not repeatable; a new visual can confound an old pixel test.** Rapier rubble
   from the same replay settled differently between runs (d4 covered in one, clear in the next), so a
   precondition like "some target is hidden under a chunk" passed 3/3 one hour and 1/3 the next with
   no related change. Replay the fixture until the precondition holds (bounded, e.g. 4 attempts) and
   never relax the assertion. When a later feature adds light or colour near the sampled spot (a
   selection sigil with its own point light), re-prove the old spec's red by switching off the
   feature it guards (here the through-rubble layer): the hidden spot then shifted 6 to 14 against a
   bar of 75, so the new light was not what made it pass. For "is this effect loud enough", count
   pixels in a hue gate across the whole region (burning amber: r>200, 110<g<215, b<140) rather than
   sampling fixed points, which foreground pieces and a rotating pattern can hide; score the OLD
   visual with the same metric (-21) before choosing the bar (150 against a new minimum of 406).

## Verification
- `npx vitest run src/scene/hallHoles.test.ts` fails on the old GLB and passes on the rebuilt one.
- `npx playwright test e2e/grip.spec.ts` prints the worst gap and fails on the old queen, passes on the rebuilt one.

## Example
Chess Explosion `src/scene/hallHoles.test.ts` against `public/models/environment.glb`: door and
wall mouse holes, open window portals, gated windows as the negative control. Runtime variant:
`src/pieces/gripGap.ts` + `e2e/grip.spec.ts` (queen's fists on her chair through the carry).
