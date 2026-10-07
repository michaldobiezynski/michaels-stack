---
name: e2e-animation-teleport-probe
description: |
  Catch and fix animations that "teleport" (a creature, piece or character jumps to its next spot instead
  of moving there) in three.js / React Three Fiber or any frame-loop game, with a per-frame displacement probe
  asserted in an e2e test. Use when: (1) a user reports that something "teleports instead of actually
  jumping/walking", (2) motion looks right in isolation but skips ahead after a rest, idle or wait state,
  (3) you want an e2e assertion of motion continuity ("never more than X units in one frame"), (4) a new
  e2e test for an animation fix passes against the old code too (the probe is only written by the fix).
  Covers the common cause: a segment clock (`t += dt`) advanced at the top of the frame loop, before a
  resting branch returns early.
author: Claude Code
version: 1.0.0
date: 2026-09-27
---

# Catching teleporting animations with a per-frame displacement probe

## Problem
An animated object appears to jump from place to place. Stills rarely show it (each frame looks fine), and
a test that checks only where the object ends up passes.

## Context / Trigger Conditions
- A frame loop (`useFrame`, `requestAnimationFrame`, a physics step) drives segments: hop, rest, hop.
- The segment's clock is shared: `st.t += dt` runs every frame, and a `resting` branch returns early.
- The next segment is set up (`t = 0`, new from/to) at the end of the previous one, before the rest.

## Solution
1. **Find the clock that runs through the pause.** If `t` advances while resting, the next segment starts
   `REST / DURATION` of the way through (rest 0.35 s, hop 0.42 s: the hop opens 83% done, which reads as a
   teleport). Advance the segment's clock only while the segment runs (after the rest check), or reset it
   when the rest ends; check every phase that shares the clock (a final dive, a return leg).
2. **Measure first, then fix.** Add a probe: the largest single-frame move since the action began.
   ```ts
   // on start: object.position.set(start...); drawn.current = null; probe.leap = 0
   // each frame, before this frame's update:
   const p = obj.position
   if (drawn.current) probe.leap = Math.max(probe.leap, Math.hypot(p.x - drawn.current[0], p.y - drawn.current[1], p.z - drawn.current[2]))
   drawn.current = [p.x, p.y, p.z]
   ```
   Set the object to its start pose when the action begins, so the first measured frame is not a jump from
   a stale position (the last place it was hidden at).
3. **Run the test red against the old animation.** Commit the probe on its own before the fix: a probe that
   only the fixed code writes stays 0 on the old code, and the test passes vacuously (seen: the first run
   "passed" at 0; with the probe alone it read 1.29 units; after the fix, under 0.5).
4. **Pick the threshold from the motion.** Expected step = distance / (duration x fps); a 1.4-unit diagonal
   hop over 0.42 s is about 0.06 per frame at 60 fps. With `dt` capped at 0.1 s one slow frame moves a quarter
   of the segment, so set the bar a few times the slow-frame step and well under the bug's jump (0.5 here).
5. **Look at it.** A burst of six screenshots about 70 ms apart, cropped and laid out in a contact sheet,
   shows the arc (airborne, shadow apart; landing; sitting).

## Verification
- The e2e test (trigger the action, wait for it to finish, assert `probe.leap < threshold`) fails on the old
  clock and passes on the fixed one; the contact sheet shows intermediate positions.

## Example
Chess Explosion, 27/09/2026: the wizard's rabbit (`src/world/Wizardry.tsx`) hopped between squares with a
0.35 s rest; `st.t += dt` sat above the `resting` early return, so each hop and the final dive into the hat
opened most of the way done. Probe `world.rabbitLeap`; test "the rabbit hops from square to square in arcs,
never most of a square in one frame" (red 1.29, green < 0.5).

## Notes
- The same shape breaks any sequence with waits between tweens: patrols, gliders, lift doors, cutscenes.
- Record-time slow motion (`dt / factor`) and capped `dt` both change the per-frame step; derive the bar from
  the same `dt` the loop uses.
- Related: `playwright-3d-canvas-click-tests` (probes and stills for canvas tests).
