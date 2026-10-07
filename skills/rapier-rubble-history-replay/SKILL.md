---
name: rapier-rubble-history-replay
description: |
  Record and replay physics debris exactly in a @react-three/rapier scene, for undo, step-back /
  step-forward history, jumps to a past position, or "rebuild the broken object" effects. Use when:
  (1) chunks restored at recorded poses slump or drift a tenth of a unit after a jump, (2) a replayed
  shatter does not land where it did the first time, (3) bodies teleport when a React re-render
  passes a new position array, (4) calling body.sleep() right after setBodyType leaves neighbours
  awake and the heap collapses, (5) you need an assemble / disassemble tween between a whole mesh and
  its fracture chunks, (6) every move makes distant heaps slump, (7) stepping back loses rubble a
  later gust or move shoved, (8) a position left while chunks were still flying comes back frozen
  in mid-air or as a motionless piece-shaped heap, (9) a "nothing stirred after the key" test flakes
  1 run in 10-15 because a chunk still moves on its own. Verified in Chess Explosion (rubble poses within
  0.001 after a jump; replayed piles 0.000 from the recorded frame).
author: Claude Code
version: 1.3.0
date: 2026-09-25
---

# Exact rubble replay with Rapier

## Problem
Physics rubble is not repeatable (the same seeded launch settles differently run to run), so history
navigation has to record where chunks lay and put them back. Naive restores drift: a restored heap
re-simulated under gravity slumps, and chunks touching kinematic neighbours never sleep.

## Solution
1. **Record poses by a stable id** (the rubble record's id, not a mount counter): a registry maps id to
   a function returning each body's translation and rotation. Snapshot every pile when leaving a
   position (before a move or a jump) and keep it with that position.
2. **Create bodies at their pose once.** @react-three/rapier re-applies `position`/`quaternion` when the
   prop values change, so compute the start pose in `useState(() => ...)` (fixed at mount), and keep
   any `position` input used in a `useMemo` keyed on its values, not the array identity.
3. **Hold restored chunks as FIXED bodies** (Rapier body type 1) at the exact pose until the next move
   starts, then switch them to DYNAMIC (0) so moving pieces still shove them. Re-simulating the heap
   (dynamic plus sleep) moved chunks by up to 0.15. Changing a body type wakes its contacts, so never
   rely on `sleep()` straight after `setBodyType` for a whole heap.
4. **Replay a shatter as scripted flights**, not physics: switch each chunk to KINEMATIC_POSITION (2),
   fly it on a quadratic Bezier from its place in the whole object to its recorded pose with
   `setNextKinematicTranslation/Rotation` in `useBeforePhysicsStep` (slerp to the target orientation
   plus a tumble that unwinds to zero), then hold it there until the move finishes and fix it.
   Rebuilding is the same flight in reverse (from `body.translation()` to the chunk's home), then
   unmount the pile and show the object. Result: replayed chunks within 0.01, jumps within 0.001.
5. **Body type numbers, not the enum**, when the app's physics runs on a nested copy of
   `@dimforge/rapier3d-compat` (inside `@react-three/rapier`) of a different version from the
   project's own: Dynamic 0, Fixed 1, KinematicPositionBased 2.
6. **Remount piles on a jump** by keying them `${id}#${jumpCounter}` so each is laid afresh.
7. **Idle piles skip per-step work**: after launch, check "all colliders ready" only until launched,
   and return early from the step callback when nothing is flying or held.

8. **Pin whatever is at rest, all the time**, not only restored chunks, and on each move release
   only the chunks near the moving pieces' paths (point-to-segment distance under about 0.85 of a
   square). Releasing the whole board on every move let distant heaps slump. A chunk counts as at
   rest if FIXED, or launched, settled and slow (|v| < 0.6, |w| < 3); check every 12 steps.
9. **Record rest per chunk, and velocity when it is not.** A frame kept while chunks were still
   flying stores `rest: false` plus linear and angular velocity; restoring it frees those chunks as
   DYNAMIC with that velocity instead of pinning them in mid-air. When the pile later settles, it
   calls back and every kept frame that caught it moving takes the WHOLE pile's settled poses (a
   sleeping chunk can be nudged by a rolling neighbour, so patch the pile, not single chunks).
10. **A pile left before its blow launched has no poses worth keeping**: mark it `unlaunched` and
   drop mode and poses from the frame so returning replays the blow rather than laying a
   piece-shaped heap.
11. **History playback shoves nothing.** While stepping back or replaying a step forward, freeze
   resting chunks and release none; only live moves push rubble. On arrival, fly any pile that no
   longer lies as the target frame had it (a gust, a shove) back with a restore flight
   (`restore: { key, poses }`, a new key starts it). Compare a replay with the frame of the ply being
   replayed, not a later one: a later move may have nudged the pile since.
12. **An external mover owns what it moved**: after a sweep, chunks it froze off the board stay
   frozen; a later restore flight is the only thing that brings them back. When the sweep decides a
   chunk is ALREADY off the board and fixes it where it lies, judge by height and rest, not by
   crossing the edge: a chunk balanced on the rim has its centre just past the edge (seen at
   |x| 4.31 against an edge of 4.3, y 0.08 against a floor at -0.43), and one may be mid-fall. Only
   past the edge AND at rest AND below the board's underside counts; anything else is swept. It
   showed up in 1 of 3 full-suite runs, so pin the exact coordinates from the failure in a unit test.
13. **Scripted flights pass through everything.** A KINEMATIC chunk flown on a scripted arc
   hits DYNAMIC chunks with infinite mass: a swept chunk dropping onto the floor was knocked
   1.2 units back onto the board and then fixed there. Set its colliders' collision groups to
   0 when the flight starts (`body.collider(c).setCollisionGroups(0)` for each of
   `body.numColliders()`) and back to `0xffffffff` wherever it becomes a body again (the drop,
   pinning, freeing). Check no collider in the project uses custom groups first.
14. **Fix a dropped chunk once it is at rest, not on a timer.** Fixed 1.1 s after the drop
   began, a chunk bounced off another could be frozen in mid-air. Count consecutive steps with
   |v| < 0.2 and |w| < 1.5 and fix after 3 (or when asleep), with a cap (1.6 s) so a sweep
   still finishes in time; a stricter test (|v| < 0.12, |w| < 1, 4 steps, 2.5 s cap) often
   hit the cap and pushed the sweep to 3.9 s.

## Verification
- Probe every pile's poses; after End (a jump), compare with the recorded poses at 16 ms, 50 ms and
  650 ms: all within 0.02 and not drifting. After a replayed step, the same.
- Prove the tests discriminate: without the fixed-body hold the worst chunk drifted 0.1-0.3.
- Cover the orderings a review found broken: move then step back (no slump), gust then step back and
  forward (the sweep returns), a step taken while a pile is still flying (no mid-air pins), and
  leaving before the blow launched (the blow replays). Run each spec three times: physics timing varies.
- **Wait for measured stillness, not a settled flag, before a "nothing stirred" sample.** A settled
  counter that marks a chunk done when its flight time is up is not proof of rest: a chunk tipping off
  the board's rim onto the floor still moves 3-4 s after the blow, inside the sampled window (seen as
  0.0147 and 0.106 against a 0.01 limit, 1 in 14 runs). Poll instead:
  `expect.poll(async () => { a = positions(); wait 300 ms; b = positions(); return max |b - a| },
  { intervals: [0], timeout: 15_000 }).toBeLessThan(0.005)`, then take the "before" sample. Keep the
  assertion's threshold; prove it still bites by mutating the product (rebuilding at once failed at 0.138).
  Confirm with `--repeat-each=30`, since a 1-in-14 flake passes 8 runs by luck.

## Notes
- Freezing via `shadow.autoUpdate` or toggling `castShadow` at runtime on WebGPU threw "Destroyed
  texture ShadowDepthTexture" errors: fix shadow casting at creation.
- See also: threejs-gltf-chunks-to-rapier-bodies, r3f-webgpu-playwright-gpu-perf.
