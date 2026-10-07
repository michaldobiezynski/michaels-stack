---
name: hand-tracking-rate-control-cursor-centre-hygiene
description: |
  Design rules for a joystick (rate-control) cursor mode driven by a tracked
  hand, learned from Pawvis's first hands-on report "unusable, the normal
  gesture stuff gets in the way". Use when: (1) building or reviewing a
  velocity-from-offset cursor law on top of a hand-tracking engine that also
  has pose gestures (clicks, scroll pose, parks, an open-hand arm trigger),
  (2) the cursor creeps or runs to the screen edge with the hand held still,
  (3) steering stalls in one direction, (4) a second hand or a dropped frame
  sends the cursor flying. The failures all come from a centre that nothing
  keeps honest; the rules below say when to capture, move and clear it.
author: Claude Code
version: 1.0.0
date: 2026-09-03
---

# Rate-control cursor on a hand tracker: keep the centre honest

## Problem

Rate control turns the hand's offset from a centre into cursor velocity. Every
other gesture in the engine (arm/disarm, scroll pose, parks, primary-hand
handover, engine resets) moves the hand or the state without moving the
centre, so a "still" hand ends up with a sustained offset and the cursor
runs away. Position control hides these because its cursor is a bounded
function of the hand; rate control integrates the error for as long as it lasts.

## Context / Trigger Conditions

- Cursor drifts after arming even though the hand feels still: the centre was
  captured while the hand was still travelling into position.
- After a scroll (palm travel by design) the cursor bolts when the pose opens.
- A bystander hand, or a one-frame Vision dropout beside one, sends the cursor
  to the edge at full speed (the inheriting hand steers from the old centre).
- Steering down stalls: pushing the hand down tips fingertips toward the camera
  and trips a "pointed hand" park meant for position control.
- A camera swap / look-away / unlock warps the cursor to the screen middle.

## Solution

1. **Settle, then capture.** After arming, take the centre only once the pointer
   has moved less than ~0.012 (screen-normalised) per frame for ~3 frames;
   steer nothing until then.
2. **The centre follows the hand through parks.** While scroll/grab/wave parks
   the stick, set centre = pointer every frame, so unparking starts neutral.
3. **Recentre at rest.** When deflection is 0 (inside the dead zone) and the
   hand is still, ease the centre toward the pointer (lerp ~0.08/frame). Drift
   from the hand or from an adaptive mapping box can then never accumulate.
4. **The centre belongs to the hand, not the slot.** Clear it whenever the
   primary hand's slot changes (past-grace inheritance, `.anyHand` immediate
   reassignment), on disarm, on tracking loss past grace, and on mode change.
5. **Do not let position-control parks stall the stick.** Exempt the pointed-hand
   park from steering (keep it for buttons); a drumming pointed hand stays inside
   the dead zone anyway. Also make sure the emission branch honours the exemption,
   not just the integrator (the first attempt integrated but never emitted).
6. **Freeze adaptive mapping only while pushing** (deflection > 0), not whenever
   a centre exists, or `.anyHand` mode never re-fits the box.
7. **Resets keep the steered position**, and the app seeds it with the real
   pointer after each reset (AppKit `NSEvent.mouseLocation` → CG space by
   flipping with the main display height → normalise by the projector rect).
   A mode switch clears the stale steered position so steering resumes from
   wherever position control left the cursor.
8. **Cap the integration step** (e.g. 150 ms): a late frame inside the
   tracking-loss grace integrates nothing rather than leaping.

## Verification

Deterministic engine tests with synthetic hands (no smoothing, identity box):
a hand sliding into position emits no moves; scroll travel then a still open
hand emits no moves; a bystander held still for 1.5 s emits no moves; a
pointed hand pushed sideways moves the cursor; `reset()` followed by a still
hand emits exactly one move at the previous position. All green (765-test
suite) on 03/09/2026.

## Notes

- Position control (trackpad-style relative with a fist clutch) is the better
  default for pointing precision; rate control earns its place for small range
  of motion. Offer both rather than tuning one to do the other's job.
- Defaults that felt reasonable on paper (dead zone 0.04, throw 0.25, top 1.2
  screens/s, curve 2) are unvalidated against real clips; the project's own
  method is to record a clip and run its gesture eval harness with `--verbose`.
