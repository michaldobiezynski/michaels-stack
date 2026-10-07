---
name: bpy-solved-strike-poses
description: |
  Author humanlike arm strikes on a procedurally built, rigidly skinned bpy armature by
  SOLVING bone angles from hand targets instead of hand-tuning them. Use when: (1) hand-typed
  bone rotations keep producing windmill arms, blades through the body, or an elbow that
  bends backwards (hyperextends) at impact, (2) you export Idle/Strike actions to glTF and
  scrub them at runtime, (3) a two-bone IK grid search lands on the wrong elbow branch.
  Covers measuring bone axis conventions, bounding the forearm to anatomical flexion,
  a build-time blade-through-body ray-cast, and the runtime PropertyMixer accumulation trap.
author: Claude Code
version: 1.8.0
date: 2026-09-21
---

# Solved strike poses for procedural bpy rigs

## Problem
Typing Euler angles for shoulder/elbow/wrist bones of a home-made armature is guesswork:
the sign and axis of each bone depend on how the edit bone was laid out, and a pose that
looks right from one view puts the blade through the head from another. Iterating through
headless renders costs a minute per attempt and the user sees every uncanny result.

## Context / Trigger Conditions
- bmesh-built figure, armature made in `mode_set('EDIT')`, rigid skinning (one vertex group per part, then `object.join`).
- Symptoms: arm spins ("windmill"), weapon passes through the body, elbow apex pointing up/back at impact, blade pointing the wrong way at the hit frame.
- A grid-search IK returning a pose that reaches the target but on the anatomically wrong branch.

## Solution
1. **Probe conventions, never assume.** Render a probe script that sets one bone's `rotation_euler` (e.g. `--bone ForeArmR --rot 60,0,0`) and look at it. Record facts like "ForeArm +X folds up", "Hand +X pitches the blade back". Bones drawn along -Y have local X = -world X.
2. **Make arm joints sagittal.** Give shoulder, elbow and hand the same x in edit mode so a single-axis (X) rotation per bone swings the arm in the forward plane; this turns the pose problem into 2-D.
3. **Solve, do not tune.** For each key, specify the HAND target (forward, up) relative to the shoulder plus a blade direction. Grid-search upper-arm and forearm X angles (coarse 12 deg, refine 2 deg) on `pose_bone.rotation_euler`, reading joint positions with `pose_bone.head/tail` after `view_layer.update()`. Then sweep the wrist angle to align the measured blade direction.
4. **Bound the elbow.** Measure the flexion sign (rotate the forearm +30 deg; if hand-to-shoulder distance shrinks, + is flexion) and the straight angle (the forearm angle maximising that distance). Sweep only `[straight, straight + 150 deg * flex]`. Without this the search happily picks the hyperextended branch for near-full-reach targets, and the elbow bends backwards on the impact frame.
5. **Assert at build time.** After keying, step every frame, pose the non-arm parts by `pose_bone.matrix @ bone.matrix_local.inverted()` into a BVH, and ray-cast hand-to-tip; report frames where the blade crosses the body. Also report whether every solved elbow stayed within its range. Fail loudly in the RESULT JSON.
6. **Export beats as extras** (frame numbers of windup/impact/hold/end) with `export_extras=True` and `export_animation_mode="NLA_TRACKS"`; put a `Tip` empty on the weapon bone (parent first, `view_layer.update()`, then set `matrix_world`).
7. **Mind the wrist, not just the elbow.** An elbow-down bend makes the forearm point UP relative to the shoulder-to-hand line, so a hand keyed level with the shoulder plus a blade keyed downward produces a 50-60 deg kink at the wrist even though every joint is "in range". Key impact at ~98% reach with the whole arm angled down and the blade only ~15 deg steeper than the arm line, follow through lower on the same arc, and add a recover key that folds the elbow with the blade level before the point comes back up. Measure it: forearm pitch minus blade pitch per key frame; keep it under ~20 deg.
8. **Derive the rest key from the built pose.** The Idle action plays the mesh's build pose (all rotations zero), and the Strike's first key is solved from hand targets; if those targets are typed separately the first strike frame pops. Record each built hand's (forward, up) offset from its shoulder at build time and solve the rest key back to it. That also lets a figure hold a prop in a non-standard rest pose (hand to cheek, hand on an armrest) without any jump. Keep hand-held props short (under ~0.3 units) so they never reach the seat when a two-handed object is hoisted overhead.
9. **Sideways-built weapons need roll-before-pitch.** A blade built along the hand's X axis cannot be pitched by an X rotation; with XYZ Euler the roll (Y) is applied after the pitch, so the solver's pitch sweep does nothing and the blade stays flat. Give hand bones `rotation_mode = "YXZ"` (roll about the forearm first, then pitch) and pass the roll into the solve.
10. **Carried props on a turning body.** Key the prop's bone as tilt-then-yaw with its location solved so the grip meets the hands at EVERY key, and insert keys every ~40 deg of body yaw: Euler interpolation of a 180 deg yaw plus a linearly interpolated location swings the prop through the air between keys. Lift a chair by tipping it about the rail you hold (a pure tilt), never by yawing it 180 deg.
11. **Runtime scrub trap (three.js).** `PropertyMixer` writes a bone only when the sampled value changes, so any additive aim rotation applied after `mixer.update(0)` accumulates on held frames. Restore a stored base quaternion before each update and re-capture it after.

## Weight checklist (from game-animation references, applied 2026-09-11)
Per strike, key these or it reads as a puppet: (1) anticipation = a small whole-body move AWAY from the blow (dip + counter-nod), (2) wind-up = rise, draw the hips back, twist the torso, head counter-turns so the eyes stay on the target, (3) impact = hips drive forward and the body SINKS, torso lean overshoots, (4) hit-stop = freeze the pose 2-4 frames (60 ms) before the follow-through, (5) return = arrive, overshoot past neutral, settle, each swing halving. Light swing 0.2-0.4 s, heavy 0.4-0.8 s. A hip bob of a few centimetres (in a 1.5-unit figure ~0.05) is enough. Sources: slynyrd.com melee attacks, gameanim.com 12 principles, mocaponline sword guide.

## Carried props and whole-body rocks (added 2026-09-21)

- **A prop carried in the hands drifts between keys.** Keying the prop's location so its grip
  meets the hands at each key is not enough: Blender interpolates the arm rotations and the prop's
  location along different curves, so mid-interval the rail leaves the fists (seen as gaps in the
  queen's chair sweep). Fix: after keying, assign the action, `scene.frame_set(f)` for every frame
  of the carry, read the interpolated hand tails and the prop bone's interpolated rotation
  (`(pb.matrix @ rest.inverted()).to_3x3()`), recompute the location that puts the grip at the
  hands, and `keyframe_insert("location", frame=f)`. Per-frame keys make the drift vanish.
- **Rock the whole piece, not the torso.** For a pawn-like block that tips back and lunges, key the
  Root bone (so the plinth goes with it) and add a Root location lift of `base_radius·sin|tilt|`
  so the piece rocks on the edge of its base instead of sinking through the board. Finish with
  halving swings (−7°, +4°, −2°, +1°, 0) on numeric frames between hold and end, and give the
  runtime timeline a short settle beat so the wobble plays in place before the piece moves on.
- **Solve the grip from the hand separation; a single grip point cannot serve two fists.** The
  arms swing in their own sagittal planes, so the two fists stay a shoulder-width apart (2·sx) in
  the torso frame. A grip point that is one feature (the crown of an arch) can be put "inside the
  fists" along the facing axis and still leave each fist hanging beside it sideways, with nothing
  under it: the queen's fists floated 0.09–0.12 off her chair at every frame while the apex-to-fist
  distance looked plausible. Put the grip where the fists actually meet the object: for an arch of
  radius r and fist radius fr, the fists sit on the rim at `half = sx`, `reach = r + fr·(1 − bite)`,
  grip = arch centre + sqrt(reach² − half²) along the chair's up axis (raise SystemExit if
  `sx ≥ reach`); pin the prop to the midpoint of the hand bones' HEADS (the fist centres), not the
  tails plus an offset; derive the grab targets from that same point so the prop never jumps into
  the hands at the grab frame. Check reach: if the arm is 0.60 long, a 0.61 target silently clamps
  and reads as a gap. Move the figure closer rather than lengthening arms.
- **Measure surface clearance, never point distance.** "Apex is 0.28 from each fist" was half the
  hand separation, not a gap. The check that matches what the player sees is fist-surface to
  prop-surface at runtime, through the whole carry at sub-frame steps: see the
  `gltf-artefact-acceptance-tests` skill (runtime skinned clearance) and export the fist radius as
  a glTF extra (`arm["fist_radius"]`) so the probe does not fit it from vertices (a prop held in the
  fist drags a percentile fit down: the horn-holding hand fitted 0.041 against 0.065 for the empty
  one).
- Never name a bmesh part "Tip" (or any name an Empty uses): the later `bpy.data.objects["Tip"]`
  lookup finds the mesh part, not the marker.

## Verification
- Judge MOTION, not stills: capture the live strike at quarter speed (screenshot every 200 ms, clipped to the canvas) and tile the frames into a contact sheet with PIL (ImageMagick `montage` needs fonts that are often missing). Static frames hid three runtime bugs here: a swing scrubbed across a static clip segment (sword parks, then snaps), a follow-through key never played (pop between beats), and an ease-out wind-up that parks the weapon early. Pose keys and beat mapping are separate failure modes; check both.
- `RESULT` shows `blade_through_body_frames: []` and `elbow_within_limits: true` for every piece.
- Render the impact frame from the side (`pose_probe.py --frame N --view side`) and view it: elbow apex must sit below the shoulder-to-hand line.
- Screenshot the live scene from right, left and top at the impact beat and look at all three; a straight arm from above can still be an elbow-up arm from the side.

## Example
Rook chop impact key: hand at (0.55 forward, -0.02 up) from the shoulder, blade (0, -0.85, -0.53). Before bounding, the solver returned forearm -78 deg (past straight); after bounding, a slight natural bend with the elbow low. The build-time checks and the three-angle screenshots confirmed it, and all six pieces rebuilt clean.

## Notes
- The zsh gotcha when scripting probes from a tool shell: `for s in "pawn 20"; do set -- $s` does NOT split in zsh; use `${=s}` or write commands out.
- Keys are interpolated per bone in rotation space, so if every key is inside the elbow range every in-between frame is too.
- Keep amplitudes human: anticipation, one strike, follow-through, never a limb behind the body. Users notice uncanny motion instantly.

## References
- Related skills: `blender` (headless wrapper), `blender-cell-fracture-headless`, `threejs-gltf-chunks-to-rapier-bodies`.
