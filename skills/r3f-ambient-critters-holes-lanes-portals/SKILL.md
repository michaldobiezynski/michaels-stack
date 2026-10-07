---
name: r3f-ambient-critters-holes-lanes-portals
description: |
  Add small, infrequent ambient life (rats, bats, spiders, cobwebs) to a three.js / React Three
  Fiber scene with a fixed or semi-fixed camera, so creatures come out of the environment and
  never clip through it. Use when: (1) a user says creatures "appear randomly" or "walk through
  objects", (2) ambient animals should emerge from holes, grates, doors, rubble or windows and
  vanish the same way, (3) ground runners must route around pillars and props and keep off a
  playing surface, (4) flyers should enter and exit out of view or through openings, (5) dangling
  or wall details are invisible because they sit above the band a downward camera can see,
  (6) you want procedural animation of a Blender-built GLB without a rig, driven by part names,
  with HUD sliders for amount and frequency and a probe hook so Playwright can force a visit.
author: Claude Code
version: 1.6.0
date: 2026-09-21
---

# Ambient critters that belong to their environment

## Problem
The first cut spawned rats at random spots on straight lines and bats at arbitrary wall points;
they ran through barrels and pillars, appeared from nowhere, and the spider and webs were placed
where the game camera could not see them. The fix is a small amount of routing geometry, not
physics.

## Solution
1. **Model creatures as bodies with named, pivoted child parts** in headless Blender (bmesh
   primitives fused per part, `child.parent = body`, child origin at the joint, `export_apply=False`
   so the hierarchy survives). At runtime `node.clone(true)` then `getObjectByName('RatLegFL')`
   and set `rotation.x` from a phase accumulator. No rig, no clips, one GLB for all of them.
2. **Runners: holes + obstacles + a lane graph.** Declare `HOLES` (grate tiles, the gap under a
   door, rubble piles, under crates/barrels) and `OBSTACLES` as circles in world x/z. Lay a ring
   of lane points between the playing surface and the props (step ~1.6 units). Build edges
   between neighbouring lane points and from each hole to its three nearest lane points, keeping
   only segments that neither cross the keep-out rectangle (Liang-Barsky clip) nor come within an
   obstacle's radius, ignoring an obstacle that contains an endpoint (that is the hole itself).
   Precompute every hole-to-hole shortest path (Dijkstra) at module load; pick a run at random.
   Unit-test that every hole has a way out and that samples along every path stay outside all
   obstacles and the keep-out.
3. **Surface and dive.** Start the runner ~0.28 units below the floor at the hole and raise it over
   ~0.45 s while it sniffs; sink it over the last stretch of the final segment. Because holes are
   inside props or wall gaps, the mesh is hidden while it is under the floor. Smooth the heading
   with a shortest-turn lerp so corners do not snap.
4. **Flyers: portals + a bowed curve.** Portals are the openings (windows) and the open air above
   each wall top, each with an inward direction. A route is portal A to a different portal B via a
   random control point over the room: a quadratic Bezier with a small flutter that fades to zero at
   both ends. Face the tangent; bank a little; a second bat trails by half a second, offset sideways.
5. **Put details in the camera's band.** With a camera at height H pitched θ down and vertical fov f,
   the top edge of the frame is at θ − f/2 below horizontal and meets a wall at distance d at
   height H − d·tan(θ − f/2). Anything above that on the far wall is invisible from the seat, so
   webs go at door feet and window sills, and a spider must drop far enough to enter the band.
6. **Webs are alpha-textured quads, never modelled strands.** Tube strands read as white scribbles
   pasted on the wall. Draw the web with PIL at 4x and shrink (anti-aliased 1-2 px strands): an
   uneven fan from the corner, sagging arcs with gaps, a couple of hanging threads, a Gaussian
   haze of dust near the corner; several seeds for variants. In Blender put each texture on a unit
   corner quad (UV 0..1, `img.pack()`, Base Color + Alpha into a BLENDED Principled material,
   backface culling off); the glTF exporter embeds it. At runtime: `transparent`, `depthWrite=false`,
   `side=DoubleSide`, opacity ~0.9, a faint emissive so a shadowed corner does not turn the web
   black. Blender's bundled Python has no PIL, so draw the textures with the system Python in the
   asset script before the Blender step.
6b. **Spiders live on webs, and webs must differ.** Build several web variants with a seeded RNG
   (uneven fan of 4-6 strands, ragged reach per strand, arcs at random radii with sag and gaps,
   one or two loose threads) and give each spot a variant, a size and a mirror. A spider visit
   starts in the web's corner, crawls to two random points on the web (local `(r cos a, 0.03,
   -r sin a)` mapped through an `Object3D` carrying the web's transform), pauses, sometimes lets go
   and hangs on a thread below the web (upright, thread from the web point), climbs back, and
   returns to the corner. Its "up" is the web's normal, so `spider.quaternion` = the web's
   rotation as a quaternion. Only webs inside the camera band are homes; report the home index
   and position through the probe and let the spec assert the spider is within reach of it, and
   accept a `spiderWish` probe field so a capture can pick the web the camera sees. Props can
   occlude a web from one seat (a barrel in front of a window sill), so keep homes on both ends.

6c. **Three web shapes, placed where webs really hang.** Corner quarter webs for concave corners
   (door feet, window sills, arch bases, prop-to-wall corners); orb webs (centred quad, anchor
   threads drawn out to the edge) strung *between* two things: the crossed swords under a wall
   shield, a barrel or crate top and the wall behind, the gap between a column top and the walls;
   half-moon webs (quad hanging from its top edge) under torch brackets and from door and window
   lintels. Vary size and mirroring per spot. Tone the strands (colour ~0xd9d3c7, small emissive)
   so they read as old silk in the room's light rather than white lines on top of it. Give a
   handful of webs a resident spider parked at a fixed seat (deterministic pseudo-random from the
   spot index, up = web normal), with an occasional leg stir, and keep the roaming spider to webs
   inside the camera band. Add a `gameLookAt` probe hook on the game camera so a capture script
   can frame each detail close up; judging webs from the seat alone hides most of the problems.

6d. **When decals still look pasted on, author each web in Blender against the real anchors.** A
   runtime table of positions and rotations cannot fit a web to geometry; a build script can. For
   every web list the exact points it is strung between (door face and floor, sword tips, barrel rim
   and wall, column face and wall, bracket underside), build a gridded quad between them with a
   gravity sag (`-sag·sin(πu)·sin(πv)` on world -z), bake it into a local frame whose x runs along
   the anchored edge so the runtime can rock it, map the weathered alpha texture, and add loose-edge
   threads from the rim to each anchor (export with `use_mesh_edges=True`; three.js loads them as
   LineSegments). Export spider seats as empties with `tenant`/`home` custom properties
   (`export_extras=True` puts them in `userData`); make the empty's local +Z the web normal, which
   the exporter turns into glTF +Y, so the runtime can use the node quaternion as the spider's up.
   The runtime then only tints, sets `transparent/depthWrite/DoubleSide`, restyles the thread lines,
   sways each web about its local x, and seats spiders. Weather the textures first: thin the alpha
   with low-frequency noise and dot the crossings with dust clumps; uniform crisp strands are what
   make a web read as a sticker, along with self-lighting and lying flat on a single surface.

6e. **Know when to stop with cobwebs.** In a flat-shaded, palette-textured kit, every web
   approach tried here (thick modelled strands, weathered alpha decals on quads, hand-fitted quads
   with anchor threads) was rejected as pasted-on by the user; the fine-strand look fights the
   chunky style and thin geometry has no room to read at board scale. If the kit has no cobweb
   asset of its own, expect to drop webs rather than iterate, and say so early. A dangling spider
   on a thread was rejected for the same reason.
6f. **Rats that read as rats.** Give holes a `mouth` and an `inside` point so the run starts hidden
   inside the wall or below the drain and the rat appears through the hole (cut visible holes:
   a black arch with a dark broken rim on the wall foot). Drive the run as a state machine:
   creep to the mouth, look about (yaw wobble, ears up), then bursts of 1-4 units at 70-100% top
   speed with acceleration and braking, stops of 0.2-1.6 s, a slight weave, and a straight
   final dash into the hole. Keep a registry of rats that are out; a rat with a senior rat within
   half a unit ahead brakes to zero and steps sideways off the lane until it is clear, and new
   runs avoid holes in use. Drop runs shorter than a few units. Log positions through the probe
   and film a summoned rat close up to check the emergence and the stops.

6g. **Openings must really be open.** A bat cannot fly through a barred window and a rat cannot
   climb out through a drain grate, however convenient the positions are. Use the kit's open
   variants for the openings the creatures use (one open window per wall is enough), cut visible
   holes for the rest, and do not list barred things as holes at all. Put an acceptance test on the
   built GLB (see `gltf-artefact-acceptance-tests`) so the table and the model cannot drift, add
   static colliders for walls, columns and props so physics debris cannot fly into them either,
   and film each new entrance close up through the game camera before reporting it. When the
   user asks "did you use ATDD and confirm visually?", the honest answer must be yes for the
   exact case they saw.

7. **Schedule on the scene clock** (`useFrame` dt) so visits slow with slow motion and freeze with
   pause. Waits are random bands divided by a rate slider; an amount slider caps concurrent
   creatures and 0 disables spawning. A `probe.spawnCritter(kind)` hook zeroes the wait so a spec
   can summon each kind, count visits, and check the setting persists across reload.

## Verification
- Unit tests over the route geometry (see step 2) and the bat portals (never same in and out;
  samples stay inside the room and between floor and sky).
- A Playwright spec summons each creature, sees its counter rise, plays a game move meanwhile,
  then sets amount to 0 and confirms nothing can be summoned.
- Close-crop screenshots of the far wall band, the grate, and a mid-visit frame.

## Example
Chess Explosion (`src/scene/critterRoutes.ts`, `src/scene/Critters.tsx`, `src/scene/lifePrefs.ts`,
`blender/scripts/build_critters.py`): 10 holes, 10 obstacles, a 32-point lane ring, 8 portals,
6 spider anchors, 12 web spots; 106 fps with the hall and full rubble.

## Notes
- The kit's floor grate tile was a full 4x4 tile, so it simply replaced two floor tiles; check the
  footprint before assuming an overlay.
- macOS bash 3.2 with `set -u` errors on `"${arr[@]}"` when the array is empty; write
  `${arr[@]+"${arr[@]}"}` in asset scripts that take an optional type list.
