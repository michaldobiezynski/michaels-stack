---
name: kaykit-modular-kit-headless-assembly
description: |
  Assemble a game environment (dungeon hall, arena, room) from a modular glTF kit such as KayKit
  Dungeon Remastered in headless Blender (bpy) and load it in a three.js / R3F game. Use when:
  (1) Blender crashes in object_transform_apply_exec or join right after bpy.ops.import_scene.gltf
  in --background mode, (2) wall-mounted parts (torches, banners, shields) vanish inside the walls
  or only show inside arch recesses, (3) the environment is invisible in the game camera even
  though the GLB bounds are right, (4) a Blender preview with the game's fov frames far less than
  three.js does, (5) you need one atlas material and a handful of meshes instead of hundreds of
  instances. Verified 20/09/2026 with Blender 5.2, three 0.186 WebGPU.
author: Claude Code
version: 1.3.0
date: 2026-09-20
---

# Modular kit assembly in headless Blender for a three.js game

## Problem
A modular kit gives hundreds of small GLBs. The hall must be laid out around a board in a script,
exported as one GLB with one material, and it has to be visible from the game's fixed cameras.

## Solution
1. **Never use join / transform_apply on freshly imported glTF objects headless.** Blender 5.2
   segfaults in `object_transform_apply_exec` even under `temp_override`. Merge with bmesh instead:
   `m = o.data.copy(); m.transform(o.matrix_world); bm.from_mesh(m)` for each object, `bm.to_mesh`
   into a new mesh. Works for collapsing a part's hierarchy and for joining placed copies by kind.
2. **One material.** Take the first import's material, rename it, and assign it to every part
   (`mesh.materials.clear(); append(shared)`); the atlas image is embedded once in the export.
3. **Place by measured footprints**, not assumptions: read the part's vertex extents to get tile
   size, wall depth and where the origin sits. KayKit walls are 4x1x4 centred in x, y in [-0.5, 0.5],
   z from 0; the floor tile top is at z = 0.05.
4. **Wall fittings hang towards their own -y.** A torch or banner placed on a wall face with the
   yaw that points the wall inward ends up inside the wall (shield banners then only show in arch
   recesses, which is misleading). Turn fittings by +180 and, for banners, push the origin 0.35 into
   the wall so the rod sits on the face.
5. **Fit the hall to the camera, not the other way round.** A 52-degree game camera at 14 units
   sees the floor only out to about nine units past centre; a far wall at 16 is never in frame.
   Either shrink the hall (five 4-unit tiles a side, walls at 10) and lower the pitch to ~42
   degrees, or accept that walls only show in orbit and attack views. Aim attack dollies at chest
   height (y ~1.1) so the backdrop fills the upper third.
   The band rule: with the camera at height H, pitched θ below horizontal, vertical fov f, the
   frame's top edge is θ − f/2 below horizontal and meets a wall at distance d at height
   H − d·tan(θ − f/2). For H 10.4, θ 41.5°, f 40°, d 20.4 that is about 2.2 units: only the lower
   half of a 4-unit wall shows, so doors, shields, webs and spiders must live low, and hanging
   banners near the top are wasted.
6. **Blender previews of the game view need `cam.data.sensor_fit = "VERTICAL"`** before setting
   `angle`; otherwise a wide frame treats the fov as horizontal and frames far less than three.js.
7. **Light markers travel with the model.** Export empties named e.g. TorchLight00 next to the
   flames; the runtime traverses the scene for the prefix and mounts point lights there (warm,
   intensity ~14, distance ~11, decay 2), so lights and torches never drift apart.
8. In the runtime tint the kit's bright atlas (`material.color = 0x9e9285`, roughness 0.9) so the
   playing surface stays the brightest thing, and drop any old floor plane slightly below the tiles
   to avoid z-fighting.

9. **Grate tiles: measure the bar height before touching the pit.** KayKit's `floor_tile_grate`
   and `floor_tile_big_grate` sit over a unit-deep pit, and the bars themselves hang 0.05 to 0.2
   below the rim. Clamping pit vertices to a shallow depth crushes bars, pit floor and any slab
   you add into one plane, which flickers in the game. Clamp only the deep part
   (`v.co.z = max(v.co.z, -0.32)`), add nothing under it, and keep any backstop plane well below
   every recess. Prefer the narrow 4x2 drain turned against the wall over the 4x4 octagonal
   grate, which dominates a floor from above. Verify in the game: a Blender render of the
   exported GLB shows a light recess even when the pit is open to a dark backstop.

## Verification
- RESULT prints mesh names, triangle count and marker count; `inspect-glb.mjs` shows one material.
- Screenshots from both players' overviews and one attack-camera still show walls, banners and
  torches; a stress run with the hall loaded holds the frame-rate budget.

## References
- KayKit Dungeon Remastered (CC0): https://kaylousberg.itch.io/kaykit-dungeon-remastered
