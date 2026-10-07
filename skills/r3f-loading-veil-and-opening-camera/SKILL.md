---
name: r3f-loading-veil-and-opening-camera
description: |
  Build a React Three Fiber loading veil and a cinematic opening camera that actually wait for the scene.
  Use when: (1) a loading screen keyed to drei's useProgress (`active === false`, `loaded === total`,
  `progress === 100`) lifts before the models are on screen, or the bar reaches 100% and then more
  loads start, (2) an intro camera move (wide establishing shot, then glide to the player/avatar) ends
  aimed at the world origin or the middle of the map instead of the subject, (3) an intro pose set in a
  mount effect never shows because the camera is already at its default view, (4) every e2e test skips
  the intro (`?intro=0`) and a real-visit camera bug ships unseen. R3F 9, drei 10 (CameraControls,
  useProgress), three r18x; applies to WebGL and WebGPU.
author: Claude Code
version: 1.0.0
date: 2026-09-27
---

# Loading veils and opening cameras that wait for the scene (R3F)

## Problem
Two first-impression features break in quiet ways: the veil lifts early, and the opening glide lands on
the wrong spot. Neither shows in tests that skip the intro.

## Context / Trigger Conditions
- drei `useProgress` follows `THREE.DefaultLoadingManager`. Its `onLoad` (so `active: false`) fires every
  time the manager's queue empties, including a lull after the first model finishes and before the rest
  are even requested. A trace of one world load: `0/1, 1/8 ... 8/8, 8/9, 9/18 ... 18/18`: "done" twice.
- An opening camera glides "behind the pawn" but the pawn's position is read when the camera controls
  mount, which is before the avatar's models have loaded (Suspense), so it is still the origin.
- Another mount effect in the same component (for example "start on the overview") runs after the intro
  effect (effects run in declaration order) and silently replaces the intro pose.

## Solution
1. **Signal readiness from inside the Suspense boundary.** Put a tiny component last inside the scene's
   `<Suspense>`; it mounts only when everything in the boundary has loaded:
   ```tsx
   function SceneReady() { useEffect(() => markSceneReady(), []); return null }
   <Suspense fallback={<Board />}><Scene /><SceneReady /></Suspense>
   ```
   `markSceneReady` sets a flag in a small `useSyncExternalStore` store. Key the veil's lift and the
   opening glide to that flag; keep `useProgress` only for the bar (clamp it to only move forward, and
   show it full once the scene is ready).
2. **Read the subject's position when the camera sets off, not when it mounts.** Wait for the subject to
   exist (a `ready` flag the avatar sets in its mount effect) as well as for the hold time, then read its
   position inside the glide function.
3. **Suspend follow logic during the opening.** A per-frame "follow the subject" (`controls.moveTo`) pulls
   the establishing shot about as soon as the subject appears; gate it with a `following` ref turned on
   by the glide.
4. **Make other mount-time camera placement defer to the opening.** Search the component for every
   `setLookAt`/`moveTo` in effects; the first-mount one must skip when an opening is in progress.
5. **Latch readiness, never cancel the glide on a flip.** If you do key anything to `useProgress`, latch
   the first "all in" in state; an effect whose cleanup clears the glide timer when the value flips back
   will cancel it.
6. **Gate the opening to real visits** (for example a bare URL with no query, or `?intro=0` to skip), and
   write one test with the opening ON that asserts the subject ends near the frame's centre
   (`project(subject)` within 30-70% of width and 30-90% of height), plus a phase probe
   (`'wide' | 'gliding' | 'done'`) set at module load so a test can read it before the renderer mounts.

## Verification
- A delayed-asset run (Playwright `page.route('**/*.glb', r => setTimeout(() => r.continue(), 1500))`)
  keeps the veil up until the scene is in.
- The opening test fails before the fix (Chess Explosion: the pawn projected to x = -3353 px) and passes
  after; the phase goes `wide` -> `gliding` -> `done` only after every piece has loaded.

## Example
Chess Explosion (27/09/2026): `src/scene/sceneReady.ts` + `<SceneReady />` in App's Suspense; the game's
veil and `CameraDirector` opening wait for it. The world's `FollowCamera` reads `live.pawn` inside
`behind()`, waits for `live.ready` (set by the Avatar's mount effect), and gates the follow with a ref.

## Notes
- Tests almost always skip cinematic openings for stable clicks; that is exactly why opening bugs ship.
  Keep at least one test on the real path.
- A veil that takes no pointer events and fades in under half a second will not disturb pixel-sampling
  specs that wait ~1.2 s after load.
- Related: `playwright-3d-canvas-click-tests` (wait for camera-controls 'sleep' before clicking).

## References
- drei Progress / useProgress docs: http://drei.docs.pmnd.rs/loaders/progress-use-progress
- pmndrs/drei issue #1094 (100% loaded but the model not on screen yet): https://github.com/pmndrs/drei/issues/1094
