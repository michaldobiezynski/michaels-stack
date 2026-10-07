---
name: threejs-gltf-chunks-to-rapier-bodies
description: |
  Turn a pre-fractured GLB (one node per chunk, e.g. from Blender Cell Fracture) into
  one Rapier rigid body per chunk in three.js / React Three Fiber and launch them
  deterministically. Use when: (1) the runtime counts MORE chunks than the GLB has nodes
  (36 nodes but 69 meshes) because GLTFLoader splits a multi-material node into a Group
  with one Mesh per primitive, (2) chunk meshes are invisible although physics runs, dust
  renders and no error is logged (a material ARRAY on a geometry with no groups draws
  nothing on both WebGL and WebGPU), (3) a seeded shatter lands differently between
  runs (@react-three/rapier colliders mount one commit after their bodies), (4) fading
  chunks via material.transparent/opacity flipped at runtime has no visible effect on
  WebGPURenderer, (5) a kinematic piece must shove settled debris aside. Covers
  mergeGeometries(useGroups), centroid pivots, setLinvel vs impulses, kinematicPosition
  pushers and StrictMode double-mount.
author: Claude Code
version: 1.0.0
date: 2026-09-10
---

# GLB fracture chunks to Rapier rigid bodies (three.js / R3F)

## Problem
A Blender-fractured pawn exported as a GLB with 36 chunk nodes produced 69 rigid bodies
at runtime and, in the same run, no chunk was visible even though the physics clearly
ran (dust spawned, phases advanced, frame rate fine). Both symptoms were silent.

## Context / Trigger Conditions
- `renderer` shows dust or other effects but the fractured meshes never appear; no console error.
- A probe or debug count of "chunks" is roughly double the GLB node count.
- GLB nodes carry two materials (exterior + interior fracture faces), so each mesh has
  two glTF primitives.
- Seeded shatters drift by centimetres between runs.
- Fading debris stays fully opaque under `three/webgpu` (`WebGPURenderer`, WebGL2 fallback included).

## Solution

### 1. One chunk per node, not per primitive
`GLTFLoader` turns a node whose mesh has N primitives into a `Group` named after the node
with child meshes named `<node>_1 ... _N`. Traversing for `isMesh` therefore finds the
primitives, not the chunks. Merge them back:

```ts
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

root.traverse((obj) => {
  if (!obj.name.startsWith(prefix)) return
  if (obj.parent?.name.startsWith(prefix)) return   // primitive inside a chunk group
  const mesh = obj as Mesh
  if (mesh.isMesh) { geometry = mesh.geometry; materials = [mesh.material].flat() }
  else {
    const parts = obj.children.filter((c): c is Mesh => (c as Mesh).isMesh)
    geometry = mergeGeometries(parts.map((p) => p.geometry), true)   // useGroups = true
    materials = parts.flatMap((p) => [p.material].flat())
  }
  obj.matrixWorld.decompose(p, q, s)   // pivot = chunk centroid if Blender used use_recenter
})
```
`GLTFLoader` also sanitises names (`Pawn_cell.001` becomes `Pawn_cell001`); match on the prefix.
Cache the extraction per loaded scene (a `WeakMap<Object3D, Chunk[]>`): `mergeGeometries`
allocates new geometries and nothing disposes them otherwise.

### 2. Never give a material array to a geometry without groups
Both `WebGLRenderer` and `WebGPURenderer` iterate `geometry.groups` when `mesh.material`
is an array. A single-primitive chunk wrapped as `[material]` renders nothing, silently.

```tsx
<mesh geometry={g} material={materials.length === 1 ? materials[0] : materials} />
```

### 3. Launch only once colliders exist
`@react-three/rapier` creates the body in one effect flush and mounts auto-colliders
(`colliders="hull"`) one commit later. Setting velocity on a collider-less body skips
gravity for a step. Gate the launch:

```ts
const ready = bodies.every((b) => b && b.numColliders() > 0)
```
Use `setLinvel`/`setAngvel` for the launch; `applyImpulse` would need scaling by each
chunk's (tiny) mass to give a consistent speed.

### 4. Transparent fades need a rebuild on the node pipeline
`NodeMaterial` bakes `isOpaque()` into the shader at build time and `material.transparent`
is a plain field that does not bump `material.version`. Flipping it later without
`material.needsUpdate = true` changes the blend state but the fragment shader still writes
alpha 1. Clone chunk materials with `transparent: true` up front, or set `needsUpdate`.

### 5. Pushing debris aside
Give the moving piece a `kinematicPosition` RigidBody with a cylinder collider and drive
it with `setNextKinematicTranslation`/`setNextKinematicRotation` in `useFrame`. Do not
also set the group's position; rapier owns that transform. Moving kinematic bodies wake
and shove sleeping dynamic chunks (verified visually: rubble bunches ahead of the piece).
Advance the piece's clock inside `useBeforePhysicsStep((world) => { t += world.timestep })`
rather than from the render `dt`: with a fixed `timeStep` the render loop and the physics
loop drift apart, so a render-clocked kinematic sweep contacts the rubble on different
steps each run and a seeded shatter stops being reproducible.

### 6. Misc
- Skip `<StrictMode>` in the entry: its simulated double mount creates and destroys bodies twice in dev.
- Do not use the same `key` (e.g. the seed) on sibling effect components; React may omit one.
- Sibling GLB-loaded components should all call `useGLTF(url)` inside the same Suspense
  boundary at startup, otherwise the first capture suspends and blanks the live scene.

## Verification
- Count chunks in the GLB independently (parse the 12-byte GLB header + JSON chunk with
  Node, count nodes with `mesh` and the name prefix) and assert the runtime count equals it.
- Screenshot ~0.4 s after launch: chunks and dust both visible.
- Same `?seed=` twice: identical rest positions.

## Example
Wizard-chess capture in `~/development/projects/chess-explosion`: `src/fx/shatter/chunks.ts`
(`extractChunks`, `chunksForScene`), `src/fx/shatter/ShatteredPawn.tsx`, `src/pieces/Attacker.tsx`
(kinematic pusher), `scripts/inspect-glb.mjs` (GLB node counter shared with the e2e test).
36 hull bodies at 120 fps on an M5 Pro under WebGPU.

## Notes
- Rapier is deterministic for the same build and inputs; variety comes from a seeded RNG
  (mulberry32) whose call order per chunk is fixed.
- Hull colliders on 8-vertex chunks are fine; convex decomposition was not needed.

## References
- three.js GLTFLoader docs (multi-primitive meshes become Groups): https://threejs.org/docs/#examples/en/loaders/GLTFLoader
- @react-three/rapier README (RigidBody, colliders, kinematic types): https://github.com/pmndrs/react-three-rapier
- three.js BufferGeometryUtils.mergeGeometries: https://threejs.org/docs/#examples/en/utils/BufferGeometryUtils
- Related: [[blender-cell-fracture-headless]], [[r3f-webgpu-playwright-gpu-perf]], [[threejs-3d-chess-patterns]]
