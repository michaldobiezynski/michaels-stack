---
name: threejs-skinned-sweep-footprint
description: |
  Decide which bystanders an animated (skinned) three.js character would actually touch during a
  move or attack, and plan minimal step-aside offsets, instead of a radial "threat radius". Use when:
  (1) a radial avoidance rule moves units that are nowhere near the attacker (e.g. a queen's strike
  shuffling pieces four squares away), (2) the user asks for only pieces "genuinely in the way" to
  move, (3) units planned to dodge still get hit by a fast swing (the clip was sampled too coarsely),
  (4) a weapon still out while the attacker advances hits a neighbour (the put-away pose plays in a
  different place than assumed), (5) you need an e2e ground truth for "touched" or "hit" from posed
  SkinnedMesh vertices. Covers SkeletonUtils.clone + AnimationMixer.setTime sampling,
  SkinnedMesh.getVertexPosition, a lowest-point grid footprint, placing footprints per animation beat,
  a shortest-clearing-step planner with chain pushes, and the Playwright measurement.
author: Claude Code
version: 1.0.0
date: 2026-09-24
---

# Planning step-asides from a skinned mesh's posed sweep

## Problem
A radial rule ("everyone within R of the attacker steps back, fading over F") is cheap, but it moves
far too many units. It also knows nothing about a swung weapon's real shape, height, or timing.

## Context / Trigger Conditions
- Units far from the action shuffle during a strike.
- A tall sweep (a chair raised overhead) moves short units it passes over.
- After switching to a footprint-based planner, planned dodgers are still struck. The cause is either
  sampling or placement (see steps 2 and 3).

## Solution
1. **Footprint, once per type, at load.** Clone the rig with `SkeletonUtils.clone`, give the clone its
   own `AnimationMixer`, and `clipAction(clip).play()`. For each sample:
   - call `mixer.setTime(t)` and `scene.updateMatrixWorld(true)`;
   - for every Nth vertex, compute `mesh.getVertexPosition(i, v).applyMatrix4(mesh.matrixWorld)`, times
     the render scale;
   - write it into a grid (4 cm cells) in the mover's own frame (x right, z forward), keeping the
     **lowest y** per cell;
   - skip points at or near the floor (y ≤ 0.02), which are the mover's own base;
   - record `reach` (the maximum radius plus one cell's diagonal) for culling.

   The piece on the board is never touched.
2. **Sample at the clip's keyframe rate, not a fixed count.** 24 samples over a 5.8 s strike gave the
   10-frame swing only 2 poses. The footprint came out half its true size, and pieces planned clear
   were struck. Use `ceil(duration × 24) + 1`, the clip's own 24 fps. Measured cost: every 4th vertex
   of an 18k-vertex rig with a 5.8 s clip takes 150 ms, once, at load. The idle pose needs only about
   8 samples.
3. **Place each part of the sweep where the timeline plays it.** Read the attack timeline rather than
   assuming. Here:
   - the approach and advance use the idle footprint along the path;
   - the strike from 0 to `hold` sits at the strike point, facing the attack yaw;
   - the put-away from `hold` to `end` sits at the strike point if the style has a settle beat, but
     **along the advance leg at the attack yaw** if it does not. The weapon lowers while it moves.

   Add turn fans (yaw steps of at most 0.15 rad) at the start, at corners, and at arrival: a unit
   turns in place and sweeps its neighbours.
4. **Touch test.** Rotate each bystander's centre into the mover's frame. With
   `yaw = atan2(dx, dz)` (0 faces +z):
   - `lx = dx·cos(yaw) − dz·sin(yaw)`
   - `lz = dx·sin(yaw) + dz·cos(yaw)`

   Then test the circle (radius r) against every cell rectangle whose lowest point is below the
   bystander's height. Cull placements farther than `reach + r` first.
5. **Planner** (pure; unit-test it with synthetic slab footprints):
   - For each touched unit, find the shortest clearing step: 24 directions × 0.03 increments, with
     branch-and-bound on the best step so far.
   - Keep the whole body on the board.
   - Add a bump cost (0.3) for a step into a neighbour.
   - Then run up to 8 chain passes: anyone a stepped unit comes too close to moves straight out from
     it, as far as it must.
   - Publish the offsets keyed by square once, at the start of the move. Withdraw them when the plan
     ends and on unmount.
6. **Display.** Ease the displayed offset from where the unit currently stands towards the target.
   Don't compute `step × progress`: a unit still walking home that gets a new step would jump.

## Verification
Build an e2e ground truth in Playwright:
1. Each `requestAnimationFrame`, sample the attacker's posed vertices (every 3rd) from the live rig.
2. For every bystander, work out:
   - **touched:** a vertex inside its body cylinder at its home square centre, with y in (0.02, height);
   - **hit:** a vertex inside its body where it currently stands (radius − 0.02);
   - **stepped:** it moved outward by more than 0.03;
   - **bumped:** another stepped unit came within the sum of their radii of its home.
3. Assert:
   - nobody is hit;
   - every unit that stepped was touched or bumped;
   - at least one unit is neither, and it stays put.
4. Two measurement traps:
   - Take home from the square's centre, not from the rig's position at start: a unit may still be
     walking back from the previous move.
   - Count only outward movement.

See it fail on the radial rule first.

## Example
In chess-explosion (`src/pieces/dodge.ts`, `sweep.ts`, `Piece.tsx`, `e2e/step-aside.spec.ts`):
- **Qxf7 after e4 e5 Qh5 Nc6:** the radial rule moved 12 to 17 pieces; the planner moves only g7.
- **Nxd5 after Nc3 d5:** it touches nobody, and now nobody moves (19 moved before).
- **Qxd6 with c5, and Nxe6 with e5:** these scenarios caught the undersampling and the put-away
  placement.

## Notes
- The planner runs once per move at the start. It stayed within one 16.7 ms frame for every move
  measured.
- With a skinned rig, bake nothing at build time. Sampling at runtime from the loaded GLB keeps one
  source of truth with what is rendered, including clip edits.
- Idle clips that start at a random phase make pixel-based tests flaky (a corner piece turns a helm
  away). Judge on the best of a few stills taken 0.5 s apart.
- Related: [[threejs-3d-chess-patterns]], [[r3f-webgpu-playwright-gpu-perf]].
