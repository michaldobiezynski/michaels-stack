---
name: r3f-rapier-carry-kinematic-body-between-frames
description: |
  Move a React Three Fiber component that drives its own @react-three/rapier kinematic body
  (setNextKinematicTranslation in useBeforePhysicsStep) to arbitrary places and heights in a larger
  world, and switch it between local frames mid-animation without a jump. Use when: (1) wrapping such a
  component in a moved <group> does nothing (the body stays near the origin), (2) a piece built for an
  8x8 board must walk terraces, strike neighbours or be reused in another scene, (3) a frame change made
  in useLayoutEffect still shows the object at the wrong place for one physics step, (4) a state machine
  driven from useBeforePhysicsStep wedges after orders arrive while it is busy (an exception thrown inside
  the step, a phase that never ends).
author: Claude Code
version: 1.0.0
date: 2026-09-27
---

# Carrying a kinematic R3F + Rapier body between frames

## Problem
A component (a chess piece, say) computes its position in its own frame (board squares) and applies it
with `rb.setNextKinematicTranslation(...)` every physics step. Rapier positions are world positions, so a
parent `<group position>` does not move it. Reusing it in a bigger world, at any height, and letting it
act in a neighbour's frame (strike the next square) needs a different mechanism.

## Context / Trigger Conditions
- `useBeforePhysicsStep` + `RigidBody type="kinematicPosition"` + `setNextKinematicTranslation`.
- The component's motion maths is in a local frame you do not want to rewrite (attack timelines, glides).
- Symptoms: the object ignores its parent group; or after switching frames it flashes one step at the
  target's place; or orders given while it is busy are later carried out from the wrong place.

## Solution
1. **Opt-in anchor prop.** Give the component an optional `anchor?: { current: { offset: Vec3; yaw: number | null } }`
   (a mutable ref object, not state). In the physics step, add `offset` to every local point before
   `setNextKinematicTranslation`, and use `anchor.yaw` as the rest heading. Without the prop, nothing
   changes, so the original scene is untouched. Also add the offset to the RigidBody's initial `position`
   and to any positional audio.
2. **Movers write the anchor, not React state.** A walker/glider updates `anchor.current.offset` inside its
   own `useBeforePhysicsStep` (offset = worldPoint - localHome), so movement costs no re-render.
3. **Keep global registries out.** If the component registers itself in board-wide systems (who stands
   where, who must make way), skip that when an anchor is given, or local square names collide.
4. **Re-base atomically with the motion.** To run a motion in another frame (strike from square A into
   B's frame), do not move the anchor in `useLayoutEffect`: @react-three/rapier's `useBeforePhysicsStep`
   stores the callback via `useMutableCallback`, which updates its ref in a *passive* `useEffect`, so a
   physics step can run with the new anchor but the old (null) motion prop. Instead put
   `rebase: { motion: id, offset }` on the anchor when you set the motion, and have the component apply
   it in the same physics step that starts that motion id.
5. **Busy state machines: re-plan at every exit.** If orders (go there, strike that) can arrive while the
   object is busy (striking, flying, rebuilding), store them, mark the route stale, and at every busy exit
   run one `proceed()` that acts only on targets adjacent to where it now stands and otherwise re-plans.
   Compute anything that can throw (frame conversions) before changing any state, because an exception
   inside `useBeforePhysicsStep` after `setPhase('busy')` wedges the machine for good.

## Verification
- An e2e test that taps a far target while the object is mid-action, then waits for it to reach and act on
  that target (it wedged before the fix).
- Stills through the camera across the frame switch: no one-step jump.
- The original scene's own test suite passes unchanged (the prop is opt-in).

## Example
Chess Explosion's world page (src/world/Avatar.tsx, src/pieces/Piece.tsx): the game's `Piece` gained
`anchor` (+ `rebase`); the visitor's pawn, wanderers, duellers and exhibits all reuse the game's strike and
shatter unchanged. A strike runs in the victim's frame (`from = localSquare(target, pawnCell)`, `to = HOME`)
so the attacker ends on the victim's square exactly as a capture does.

## Notes
- Parking: to hide a body without unmounting (while its rubble is shown), move its anchor far below the
  scene, or its capsule collider shoves the rubble.
- Physics-step time (world.timestep) is the right clock for these timers: it follows slow motion.
- A fresh-context code review found the busy-order wedge; the happy-path e2e tests never reached it,
  because they always waited for 'idle' before the next tap.

## References
- node_modules/@react-three/rapier/dist/react-three-rapier.esm.js: `useMutableCallback` (useRef +
  useEffect) and `useBeforePhysicsStep`.
