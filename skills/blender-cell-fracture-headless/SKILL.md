---
name: blender-cell-fracture-headless
description: |
  Voronoi-fracture a mesh into rigid-body-ready chunks with Blender's Cell Fracture
  extension from a headless `blender --background` script and export the chunks as a GLB.
  Use when: (1) Blender 4.2+/5.x has no Cell Fracture (it moved to extensions.blender.org
  and is not bundled), (2) you need to install/enable an extension with no GUI
  (`--online-mode`, `bpy.ops.extensions.package_install`, `bl_ext.blender_org.<id>`),
  (3) `hasattr(bpy.ops.object, 'add_fracture_cell_objects')` says True but the operator
  is not installed (bpy.ops attributes are lazy), (4) the fracture must be deterministic
  and re-runnable (VERT_CHILD source with seeded points instead of a particle system),
  (5) chunk pivots must sit at each chunk's centre for physics (use_recenter), (6) the rubble
  looks like a heap of bare cut-face (interior material) blocks, chunks poke outside the
  figure, the rubble's bounds sit ~0.05 past the figure's on every side, a gem/trim material
  vanishes from the rubble, or rubble volume exceeds the figure's: Cell Fracture left cells
  UNCUT because the body is a non-manifold union of overlapping parts. Includes the exact
  operator kwargs, the temp_override needed, a GLB validation step, and a per-chunk
  stray-cell gate with a remesh fallback.
author: Claude Code
version: 1.1.0
date: 2026-09-24
---

# Cell Fracture, headless and seeded (Blender 5.2 LTS)

## Problem
Pre-fracturing a chess piece for runtime physics needs to run from a script in the repo,
produce the same chunks every time, and export one GLB node per chunk with the pivot at the
chunk centre. Cell Fracture is no longer bundled and its docs assume the GUI.

## Context / Trigger Conditions
- `addon_utils.modules()` lists nothing matching "fract"; `bpy.ops.object.add_fracture_cell_objects()`
  raises "could not be found" or "context is incorrect".
- Blender's "Allow Online Access" preference is off (default), so extension installs fail silently.
- `hasattr(bpy.ops.object, 'add_fracture_cell_objects')` returns True even when uninstalled.
  Check with `bpy.ops.object.add_fracture_cell_objects.get_rna_type()` instead (raises if absent).

## Solution

### 1. One-off install (network, no GUI)
```bash
blender -b --online-mode --python-expr "
import bpy
bpy.ops.extensions.repo_sync_all()
bpy.ops.extensions.package_install(repo_index=0, pkg_id='cell_fracture')
bpy.ops.preferences.addon_enable(module='bl_ext.blender_org.cell_fracture')
bpy.ops.wm.save_userpref()
print('RESULT', bpy.ops.object.add_fracture_cell_objects.get_rna_type().identifier)"
```
`--online-mode` overrides the preference for that run only. Files land in
`~/Library/Application Support/Blender/<ver>/extensions/blender_org/cell_fracture`.

### 2. Enable inside every pipeline script
Under `--factory-startup` the saved preference is ignored, but the package is on disk, so:
```python
bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.cell_fracture")
bpy.ops.object.add_fracture_cell_objects.get_rna_type()   # fail fast if missing
```

### 3. Deterministic cell centres
Do not rely on a particle system (depsgraph evaluation in background mode). Build a helper
mesh whose vertices are seeded random points inside the volume, parent it to the target,
and use the `VERT_CHILD` source:
```python
rng = random.Random(seed)
mesh = bpy.data.meshes.new("FracturePoints"); mesh.from_pydata(points, [], [])
helper = bpy.data.objects.new("FracturePoints", mesh)
scene.collection.objects.link(helper); helper.parent = target
```

### 4. The operator call
```python
with bpy.context.temp_override(object=target, active_object=target,
                               selected_objects=[target], selected_editable_objects=[target]):
    bpy.ops.object.add_fracture_cell_objects(
        source={"VERT_CHILD"}, source_limit=cells, source_noise=0.0, recursion=0,
        use_smooth_faces=False, use_sharp_edges=True, use_sharp_edges_apply=True,
        use_data_match=True, use_island_split=True, margin=0.0015,
        material_index=1,            # interior faces get material slot 1 (append it first)
        use_interior_vgroup=False, use_recenter=True, use_remove_original=True,
        collection_name="Chunks", use_debug_points=False,
        use_debug_redraw=False,      # True calls wm.redraw_timer, which has no UI headless
        use_debug_bool=False)
```
The operator iterates `context.selected_editable_objects`, hence the override. Chunks are
named `<Target>_cell`, `<Target>_cell.001`, ... with origins at their centres.

### 5. Clean up and export
Remove the helper and (if not already) the original via `bpy.data.objects.remove`, set
`scale = (1,1,1)` on every chunk, then
`bpy.ops.export_scene.gltf(filepath=..., export_format="GLB", export_apply=True, export_animations=False, export_yup=True)`.
A two-material chunk exports as one node with two primitives; see
[[threejs-gltf-chunks-to-rapier-bodies]] for what that does to GLTFLoader.

### 6. Gate against uncut cells (verified 24/09/2026)
When the body is a union of overlapping, non-manifold parts (a helm of battlements, thin
flattened panels, a joined weapon), the cell booleans can fail PER CELL and hand back the
whole convex cell, padded by Cell Fracture's ~0.05 cell margin, with only interior-material
faces. There is no error. A check for "one chunk is nearly the whole body" never fires,
because each stray is cell-sized. Seen: a rook going from 48 chunks to 156, 132 of them bare
cut faces, with its gem lost. A queen built weeks earlier also carried uncut cells in
place of her plinth, and nobody noticed until a render.

Check every chunk against the figure as it stood BEFORE any remesh (body + weapon):
```python
RAY = Vector((0.13, 0.27, 0.95)).normalized()   # oblique: avoids axis-aligned faces

def winding(bvh, p):
    """+1 leaving a surface, -1 entering: positive inside overlapping closed parts,
    where ray parity reads a point inside two parts as outside."""
    o, total = Vector(p), 0
    for _ in range(128):
        hit, normal, _i, _d = bvh.ray_cast(o, RAY)
        if hit is None: break
        total += 1 if normal.dot(RAY) > 0 else -1
        o = hit + RAY * 1e-4
    return total

def figure_bvh(*parts):   # world space, offset each part's indices
    coords, polys = [], []
    for part in parts:
        m, base = part.matrix_world, len(coords)
        coords += [m @ v.co for v in part.data.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in part.data.polygons]
    return BVHTree.FromPolygons(coords, polys)

def stray_chunks(chunks, bvh, tol=0.1, share=0.25):
    out = []
    for c in chunks:
        pts = [c.matrix_world @ v.co for v in c.data.vertices]
        off = sum(1 for p in pts if bvh.find_nearest(p)[3] > tol and winding(bvh, p) <= 0)
        if off > share * len(pts): out.append(c)
    return out
```
Build the BVH before remeshing. Built from a voxel-remeshed and decimated shell, it flags
sound chunks along the edges. If any strays turn up, re-run the fracture on a voxel-remeshed
body (`REMESH` voxel ≈ max dimension / 140, then `DECIMATE` 0.2, reprojecting material slots
by nearest face), and `SystemExit` if strays survive that. Tolerance calibration from real
data: a fragment split from a convex hull bulges up to ~0.09 past the figure where the hull
filled a hollow (between crenels). Uncut cells reach 0.13 to 0.5. At 0.02 the gate caught
the harmless hull bulges, and 0.1 separated the two. Remeshed rubble GLBs come out ~3-5x
larger (1.2-1.8 MB for a 50-chunk figure).

## Verification
- RESULT line with chunk count and min/max vertex counts (36 cells from 36 points, 8 to 128 verts each, ~1.5 s total).
- Parse the GLB header in Node and count nodes with the chunk prefix; fail the build below a minimum.
- Render an exploded preview (`obj.location += (obj.location - centre) * 0.5`, EEVEE, 16 samples)
  and look at it; Cell Fracture can leave gaps or slivers that only a picture reveals.
- Render the rubble ASSEMBLED too (Workbench, `color_type='MATERIAL'`, interior slot orange,
  the rest grey, orthographic three-quarter view) next to the previous build. Uncut cells
  stand out as orange blocks beside or over the figure. The exploded view hides them.
- Volume sanity check in Node (signed-tetrahedron sum per mesh, abs per chunk, summed): a correct
  cut holds at most the figure's volume, and master pieces read 0.59-0.96. A ratio above 1 is
  impossible, so it proves uncut cells. Below 1 proves nothing (a bishop with two stray cells
  read 0.87), so it is a smoke test, not the gate.
- Chunks made only of interior faces are NOT a failure signal: a cell wholly inside a solid
  figure is all cut face (a sound queen had 26% of them).

## Example
`~/development/projects/chess-explosion/blender/scripts/fracture_pawn.py` plus
`scripts/build-assets.sh`, `scripts/setup-blender.sh`, `scripts/inspect-glb.mjs`,
`blender/scripts/preview_render.py`.

## Notes
- **`use_island_split=True` crashes headless** with `AttributeError: 'NoneType' object has no
  attribute 'select_set'` (fracture_cell_setup.py, `for ob in view_layer.objects`) whenever a
  cell's intersection with the body is empty: the cell object is removed and the stale view
  layer yields None. Pass `use_island_split=False`; empty cells then simply drop out.
- **Seed points must be inside the mesh.** For unioned bodies sample the bounding box and keep
  points that pass a ray-parity test against `BVHTree.FromPolygons`; profile-based sampling
  only works for lathes. Then drop chunks with fewer than 4 faces (hull colliders need solids).
- **Exact boolean unions leave an empty material slot 0** when operands have no materials, so
  Cell Fracture's `material_index=1` lands on the wrong slot and the exterior exports with no
  material. Call `mesh.materials.clear()` and reset polygon `material_index` before appending
  stone (0) and interior (1). Also never let a unioned part's face sit exactly coplanar with
  the base (seat bottom on plinth top): the exact solver drops geometry; overlap by a margin.
- **Not deterministic run to run**, despite seeded VERT_CHILD points: the same .blend, cells
  and seed gave 54 and then 57 chunks, with different split sets. The seeds repeat; the
  boolean and split results do not. Do not diff rubble GLBs between builds as a regression check.
- **The blender-run wrapper echoes only the RESULT line**, so diagnostic `print`s vanish.
  Write diagnostics to a file, or into the RESULT JSON.
- macOS bash 3.2 has no `declare -A`; use a `case` function for per-type cell counts in the
  runner script.
- Cell Fracture is "offered as-is with limited support"; geometry-nodes fracture is the
  maintained alternative if artefacts appear.
- `bpy.ops.object.shade_smooth_by_angle` and `modifier_apply` also need the temp_override.
- Apply scale before fracturing; unapplied scale corrupts both the sim and the export.

## Rigging figures headlessly (verified 11/09/2026, Blender 5.2.1)
- `bpy.ops.object.mode_set(mode='EDIT')` works in background once the armature is the active
  object; add bones through `armature.edit_bones.new`, then `mode_set(mode='OBJECT')`.
- Rigid skinning for stone figures: one vertex group per part named after its bone (weight 1),
  `bpy.ops.object.join` under a `temp_override` with `selected_editable_objects`, then an
  Armature modifier plus `parent = armature`. Keep a boolean-unioned copy of the parts (made
  BEFORE joining) as the fracture source; the skinned mesh is not manifold.
- Export clips with `export_animation_mode="NLA_TRACKS"`: stash each action in its own NLA
  track and clear the active action first; `export_extras=True` carries custom properties on
  the armature object (beat timings) into `object.userData` for GLTFLoader.
- Bone axes are not what you guess: probe them by rendering single-bone rotations from the
  side (`pose_probe.py` pattern). For a bone pointing down with roll 0, +X swings the tail
  forward; for a hand bone pointing forward, +X pitches its held weapon BACKWARD; pose-bone
  location is (X sideways, Y along the bone, Z towards the front).
- A child bone inherits its parent's rotation, so with rigid parts an elbow keeps its rest
  right angle unless keyed: "arm back" with the forearm unkeyed lifts the hand in FRONT.
  Reaching, hanging, lifting overhead and thrusting all need the forearm unfolded (negative
  local X here); fold it only to tuck a blade behind the head. A bone lying along -Y has
  local X = world -X, so child-chain signs do not follow the parent's; probe each.
- Keep every joint of a limb in one sagittal plane (same x for shoulder, elbow, hand). Bones
  built with a slight outward tilt have swing axes that are not parallel, so a 150-degree
  raise carries the held weapon out of the plane and through the head. With coplanar
  bones the blade stays beside the body at any angle.
- Prove clearance instead of eyeballing it: for each clip frame, pose the non-limb parts
  rigidly (pose_bone.matrix @ bone.matrix_local.inverted()), build a BVHTree, and ray-cast
  the hand-to-tip segment (start a little past the wrist). Validate the detector with a
  deliberately crossing pose first; a blade at x = shoulder x can legitimately miss a
  0.25-half-width torso, so "no hits" needs a positive control.
- Author strike keys as hand targets (forward, up from the shoulder) plus a blade direction
  and solve shoulder/elbow/wrist by grid search over pose-bone X rotations (a 12-degree grid
  refined to 2 degrees, ~3 s per figure headless). Hand-tuned angle sums were wrong three
  times running because each bone's local X flips with its rest direction.
- Solve poses numerically instead of by hand: set a candidate rotation, `view_layer.update()`,
  read `pose_bone.head/tail` (armature space) and pick the angle whose bone direction matches
  the target (standing legs with planted feet, a throne placed at the midpoint of both hands).
- Read three-quarter pose renders with the camera position in mind: the preview camera sits
  front-right, so the figure's front is screen-left-and-down, not screen-right.
- Bone-parented marker placement: set `parent`, `parent_type='BONE'`, `parent_bone`, call
  `view_layer.update()`, THEN assign `matrix_world`; assigning a `matrix_parent_inverse`
  afterwards moves the object (the marker exported beside the shoulder instead of the blade
  tip). Verify with `(obj.matrix_world.translation - target).length` in the RESULT line.
- An Empty parented with `parent_type='BONE'` exports as a child of that joint; name it
  uniquely (a mesh part also called "Tip" stole the name and broke `bpy.data.objects["Tip"]`).
- three.js side: `SkeletonUtils.clone` per instance, `AnimationMixer` on the clone, scrub a
  clip deterministically with `action.play(); action.paused = true; action.time = t;
  mixer.update(0)`; measure reach by posing the clone at the impact time once at load.

## References
- Cell Fracture on the Blender extensions platform: https://extensions.blender.org/add-ons/cell-fracture/
- Blender extensions from the command line (`--online-mode`, `bpy.ops.extensions`): https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
- Headless Blender basics on this machine: the `blender` skill (`~/.claude/skills/blender`).

## Whole-copy chunks (added 2026-09-11)
If a fractured piece's "chunks" are all copies of the entire body (every chunk's max dimension equals the body's, vertex counts near the body's), the per-cell boolean intersection failed because the source mesh is not a clean solid (overlapping part union, self-intersections). Cell Fracture silently returns the whole body for such cells. Detect it by comparing the largest chunk extent with the body extent (ratio > 0.75) and fall back to a voxel Remesh (voxel ≈ extent/140) plus Decimate on the body before fracturing; the shell is then manifold and every cell cuts. Keep an eye on chunk vertex totals afterwards (remeshed pieces are 4-5x heavier).
