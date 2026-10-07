---
name: vfx-slowed-by-hit-slowmo
description: |
  Impact effects (sparks, flashes, hit particles) appear AFTER the blow instead of with it in a game that has
  hit slow motion or hit-stop driven by a scaled clock. Use when: (1) a user says the sparks/flash "happen after
  the strike", "come late", or "lag the hit", (2) the effect is spawned in the same callback as the impact
  (so the code looks right), (3) the renderer or R3F uses a time-scaled clock (a ScaledClock whose getDelta is
  multiplied by a slow-motion factor, bullet time, hit-stop), (4) a GPU/TSL particle sim steps with the frame's
  delta. The particles are spawned on time but move at the slowed pace, so they sit as a clump and only burst
  when time recovers.
author: Claude Code
version: 1.0.0
date: 2026-09-28
---

# Impact effects slowed by the game's own hit slow motion

## Problem
An impact effect is thrown at exactly the right moment (the same callback that breaks the target), yet
players see it after the strike. The cause is time, not spawn order. The world is slowed for dramatic effect
right after the hit (say a quarter speed for half a second), and the effect's simulation steps with that
slowed delta. Its particles barely move until the slow motion ends, so the visible burst comes a second late.

## Context / Trigger Conditions
- A clock scaled by a slow-motion envelope: for example `ScaledClock.getDelta() = realDelta * scale`, with
  `scale = slowMoScale(now) * userSpeed / recordFactor`, fed to R3F as its clock, so every `useFrame` delta is
  scaled.
- The effect's kernel or update uses that delta for age, gravity and position.
- A probe shows the burst recorded in the same frame as the hit (so spawn timing is fine).

## Solution
1. **Measure the pace, not the spawn.** Accumulate the effect's own time step in a probe (for example
   `sparkClock += step`). Assert that over about 300 ms after the hit it advances at about real time.
   Red: about 0.25 (the slow-motion strength).
2. **Give the flash its own step**, with the automatic slow motion divided back out but the deliberate speed
   controls kept:
   ```ts
   const step = isPaused() ? 0 : Math.min(delta, 1 / 20)                              // the world's pace
   const flashStep = isPaused() ? 0 : Math.min(delta / slowMoScale(performance.now()), 1 / 20)
   u.dt.value = step          // grit and debris: they belong to the rubble, which is slowed
   u.flashDt.value = flashStep // sparks: they flare at the blow
   ```
   In the kernel, use the new uniform only in the sparks' branch.
3. **Keep the user's speed and recording slowdowns.** A 0.1x study mode or a slowed recording should still
   slow the sparks; only the automatic hit slow motion is taken out.
4. **Look at it.** Film at full speed and keep the first few frames after the hit, before and after the fix,
   side by side. Before, a small clump at the contact; after, sparks fanning out by the second frame while the
   debris breaks slowly.

## Verification
The pace probe reads about 1.0 through the slow motion (it read 0.25 before). Frame strips show the flare at
the contact frame, and existing capture and impact specs stay green.

## Example
Chess Explosion, 28/09/2026 (`src/fx/CaptureSparks.tsx`, `src/scene/timeScale.ts`): the user reported "the
sparks from the pieces hitting each other should happen as the Strike happens and not after it". The burst was
recorded in the same frame as `onHit` (0 ms apart), but `triggerSlowMo()` (0.25 for 550 ms, then a ramp)
slowed its TSL kernel. The pace probe read 0.25, and 0.99 after a separate `sparkDt` uniform for the spark
branch (PR #55).

## Notes
- A 16 ms frame-strip at quarter speed also helps: it shows whether the effect lags the visible contact
  (a different bug: the hit callback firing after the blade is already inside the target).
- The same trap catches screen shakes, flashes, sound envelopes and UI pulses driven by the scaled clock.
- Related: `webgpu-tsl-compute-storage-buffer-limit` (GPU effects that silently do nothing),
  `e2e-animation-teleport-probe` (per-frame motion probes).
