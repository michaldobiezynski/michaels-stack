---
name: bpy-accent-materials-through-union-fracture-webgpu
description: |
  Give parts of a headless-Blender (bpy) figure different materials (gilded trim, gems) and keep
  them through boolean unions, object joins, Cell Fracture and a voxel remesh, then render the
  metal correctly in three.js WebGPU. Use when: (1) after a boolean union or join every face is
  back on slot 0, (2) accents vanish from fractured chunks after a Remesh modifier fallback,
  (3) a newly gilded part "flashes" or flickers in the browser (z-fighting on a face shared with
  the stone), (4) MeshStandardMaterial with metalness 1 renders near-black in a scene lit only by
  directional lights, (5) a bpy part named "Tip" (or any name shared with an Empty) breaks
  bpy.data.objects["Tip"] lookups after the join.
author: Claude Code
version: 1.1.0
date: 2026-09-16
---

# Accent materials through union, fracture and WebGPU

## Problem
A procedurally built figure (many bmesh parts unioned into one solid, joined into one skinned
display body, then Voronoi-fractured) needs some parts in metal and gem materials. Each stage
silently reset or lost the per-face material, and once the accents did arrive in the browser the
metal was dull and the shield border flickered.

## Context / Trigger Conditions
- `bpy.ops.object.join` or the EXACT boolean union leaves every polygon at `material_index` 0.
- The fracture script's voxel `REMESH` + `DECIMATE` fallback produces chunks with no accents.
- In the browser a gilded rim on a stone shield shows as a hatched, flashing panel.
- Gold at `metalness: 1` looks like dark mud under hemisphere + directional lights.
- `KeyError: 'bpy_prop_collection[key]: key "Tip" not found'` after adding a part called Tip.

## Solution
1. **Same slot list on every part, set the index per part.** Before any union or join give each
   part the full material list in a fixed order and set all its faces to the part's slot:
   ```python
   SLOT_MATERIALS = (STONE, STONE_INTERIOR, METAL, GEM)   # interior = Cell Fracture material_index=1
   def assign_finish(obj, finish):
       obj.data.materials.clear()
       for spec in SLOT_MATERIALS: obj.data.materials.append(make_material(*spec))
       for poly in obj.data.polygons: poly.material_index = FINISH_SLOT[finish]
       obj["finish"] = finish          # custom prop survives obj.copy()
   ```
   Boolean union: `mod.material_mode = "INDEX"` so operand faces keep their index. Object join
   merges identical material datablocks in order. Then remap defensively (`canonical_slots`)
   instead of clearing the slots afterwards.
2. **Bevel before the gems.** Union stone+metal parts, apply the bevel, then union the gem
   parts, and skip the per-part bevel for `obj.get("finish") == "gem"`. Facets on an 8-segment
   rose-cut lathe meet at more than the smooth-by-angle threshold, so they stay flat mirrors.
3. **Reproject material indices after a remesh.** Build a `BVHTree.FromPolygons` of the mesh
   before the Remesh/Decimate apply, keep `[p.material_index for p in polygons]`, and after the
   apply set each new polygon to the slot of `bvh.find_nearest(poly.center)[2]`. Voxel remesh
   keeps the slot list but not the indices.
4. **No shared faces between finishes.** A rim box whose back face is coplanar with the
   shield's back face was invisible while both were stone and z-fights the moment one is metal.
   Make borders as bars that stand 0.01 proud of both faces (or offset the part), never a plate
   flush with the host.
5. **Metal needs something to reflect.** In three.js WebGPU: `new PMREMGenerator(renderer)`
   from `three/webgpu` (after `await renderer.init()`), `fromScene(new RoomEnvironment(), 0.04)`,
   and assign `target.texture` to `material.envMap` of the piece materials only (via a registry
   that also patches materials created earlier). `NodeMaterial.setupEnvironment` wraps any
   `envMap` in `pmremTexture`, which accepts CubeUV textures directly. Per-material envMap keeps
   the board and lights untouched; `envMapIntensity` 0.25 on stone, 1.0 metal, ~1.8 gems, plus a
   small emissive on gems so they read as a dot at 5 px.
6. **Name parts uniquely.** An Empty created later with the same name gets ".001" and the lookup
   by name finds the (now joined away) mesh part. Pick a name no marker uses.

## Verification
- Build RESULT reports `material_slots` in order and `accent_faces > 0`; fracture RESULT reports
  `accent_faces` on chunks even when `remeshed: true`.
- Spotlight stills front and behind in both colours show the trims; the behind view of a shield
  shows a clean border, not a hatched panel.
- Unit test: materials created before `setPieceEnvironment` receive the texture too.

## Example
Chess Explosion (`blender/scripts/designs/common.py`, `figure.py`, `fracture_piece.py`,
`src/pieces/palette.ts`, `src/scene/Environment.tsx`): gold and rubies on ivory pieces, silver
and sapphires on the stained side; gems sized r ≈ 0.05 model units to be ~5 px from the board
camera at 14 units and fov 40.

## Notes
- The glTF exporter drops unused slots (the interior slot is absent from the display body GLB);
  the runtime tints by material *name*, so unused slots do not matter.
- Cell Fracture's `material_index` argument only writes the cut faces; outer faces keep theirs.
- A jump in chunk count after adding thin bars (rook 48 to 119) was NOT more fragments: the
  second-level split ran booleans on Cell Fracture chunks, which have open edges, and got whole
  copies back, stacked as duplicates. Sub-split an oversized chunk through its convex hull
  (`bmesh.ops.convex_hull`, rebuild a fresh mesh from `result["geom"]` faces, reproject slots by
  BVH nearest face). Never voxel-remesh such a chunk: an open mesh remeshes to a hollow shell and
  a ray-parity interior sampler then finds no points. Cap lump size in absolute units, not as a
  share of the body's extent (a raised sword or lance inflates it), exempt slivers (middle axis
  below ~0.08), and dart-throw the seeds with a minimum spacing so cells come out even.

## References
- three.js `src/materials/nodes/NodeMaterial.js` `setupEnvironment`, `src/nodes/pmrem/PMREMNode.js`
- Blender manual, Boolean modifier "Materials: Index Based"
