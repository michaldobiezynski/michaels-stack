---
name: bpy-carved-figure-remesh-boolean
description: |
  Build a smooth "carved" figurine (ivory, stone, wood) procedurally in headless Blender 5.x:
  fuse primitive parts into one organic block with a voxel Remesh, cut relief (folds, strands,
  incised lines, panels) with per-primitive MANIFOLD booleans, add dark inserts for drilled
  details, and render with a Cycles material that stains the crevices via ambient occlusion.
  Use when: (1) box-and-sphere bpy models look like toys and you need one organic mass,
  (2) a Boolean DIFFERENCE returns a near-empty mesh (a few dozen faces), (3) a material
  vanishes after a boolean (everything renders default white), (4) `enum "FAST" not found`
  on a boolean solver, (5) large ellipsoids show facets after remeshing.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Carved figurine from primitives: remesh fuse + boolean grooves

## Problem
Procedural bpy figures assembled from boxes, cylinders and icospheres read as toys: every
join is visible and detail cannot be carved into them. Reference objects (Lewis chessmen,
carved ivory, stone statues) are single masses with incised relief and staining in the grooves.

## Context / Trigger Conditions
- Headless `blender -b --python` (Blender 5.2 LTS verified), no sculpting by hand.
- Symptoms: visible part seams; a boolean that "eats" the mesh (RESULT faces ~41);
  `TypeError: enum "FAST" not found in ('FLOAT', 'EXACT', 'MANIFOLD')`; renders pure white
  after a boolean; faceted blobs after Remesh.

## Solution
1. **Build positive forms only** (blobs = scaled icospheres, tapered cones, boxes, lathes).
   Use `subdivisions=4` for any blob larger than ~10% of the figure; level 3 leaves facets that
   the remesh preserves.
2. **Fuse**: `join` everything into one object, add a `REMESH` modifier (`mode="VOXEL"`,
   `voxel_size` ≈ 0.003 of the figure height, `use_smooth_shade=True`) then a `SMOOTH`
   modifier (factor ~0.55, 2 iterations), apply both under `temp_override`. Overlapping
   shells union automatically; no boolean needed for joins.
3. **Carve grooves as cutters** (thin tapered cylinders along the surface, thin boxes,
   `bpy.ops.mesh.primitive_torus_add` for ring lines). Apply ONE Boolean modifier per cutter
   with `solver="MANIFOLD"` (Blender 5 solvers: FLOAT / EXACT / MANIFOLD). A single joined,
   self-intersecting cutter breaks EXACT and returns a near-empty mesh; EXACT works only with
   `use_self=True` and `use_hole_tolerant=True` (6x slower). ~35 cuts on 350k faces: ~10 s.
4. **Fix material slots after booleans**: the result gets an empty slot 0 that every face
   indexes. `mesh.materials.clear()`, append your material, set `poly.material_index = 0`.
5. **Dark inserts** (drilled pupils, mouth slot): separate small objects with a dark material,
   never fused.
6. **Crevice stain material** (Cycles): `ShaderNodeAmbientOcclusion` (distance ~5% of height,
   `only_local=True`) → `ShaderNodeValToRGB` (ochre at ~0.55, ivory at ~0.95) → optional
   `ShaderNodeMix` (RGBA, indices 6/7 in, 2 out) with a Noise for mottling → Base Color;
   Roughness ~0.55, Specular IOR Level ~0.35, a little Subsurface, fine Noise → Bump.
7. **Framing**: `sensor_fit` AUTO maps the 36 mm sensor to the LARGER render dimension, so a
   portrait render needs the camera further back than a landscape one for the same subject.
8. Scale a sub-assembly (e.g. the head) about a pivot by transforming its parts AND its
   cutters with the same matrix before fusing; keep ring cutters' z and radius in step.

## Verification
- RESULT face count stays in the hundreds of thousands after carving (not tens).
- Renders show the body colour, not default white; grooves darker than flats.
- View every render; judge silhouette, then face, then relief.

## Example
`chess-explosion/blender/scripts/lewis/king_hifi.py`: Lewis king, ~350k faces, four Cycles
views at 128 samples in ~2 min on an M5 Pro CPU.

## Notes
- Six iterations got a convincing stylised piece; museum-grade needs sculpted drapery and
  incised ornament, which this pipeline cannot fake with blobs.
- Related: `blender`, `bpy-solved-strike-poses`, `blender-cell-fracture-headless`.
