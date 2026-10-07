---
name: threejs-tsl-instanced-positionlocal
description: |
  three.js WebGPURenderer / TSL node materials on InstancedMesh: positionLocal is the
  instance-TRANSFORMED position, not the geometry's. Use when: (1) a TSL colorNode/emissiveNode that
  bands or masks by local height (a gilt edge on the top 15% of a box, a glow near a candle's top) works on
  a Mesh but smears or disappears on an InstancedMesh of scaled unit boxes, (2) you need per-instance
  "unit box" coordinates for shading instanced geometry, (3) you wonder whether instanceColor still tints
  a material whose colorNode you replaced. Also: text for WebGPURenderer scenes (troika / drei <Text> does
  not render; use CanvasTexture planes).
author: Claude Code
version: 1.0.0
date: 2026-09-27
---

# TSL on InstancedMesh: positionLocal vs positionGeometry

## Problem
Shading instanced, scaled unit boxes (terrain slabs, book covers) by their local coordinates gives wrong
results: the band you placed at `positionLocal.y > 0.3` lands in the wrong place for every instance.

## Context / Trigger Conditions
- three r18x with `WebGPURenderer` and `MeshStandardNodeMaterial` / `MeshBasicNodeMaterial`.
- `InstancedMesh` whose instances are unit geometry scaled by the instance matrix.
- A node such as `smoothstep(0.3, 0.34, positionLocal.y)` meant as "top of each box".

## Solution
- Use `positionGeometry` (the raw geometry attribute) for per-instance unit coordinates:
  `const gilt = smoothstep(0.3, 0.34, positionGeometry.y)`.
- Use `positionWorld` for patterns that must stay continuous across instances (wood grain, page lines).
- `instanceColor` still applies: NodeMaterial multiplies `colorNode` by it, so a custom colorNode that
  returns a neutral mottle (`vec3(1).mul(0.92 + noise * 0.14)`) keeps each instance's leather colour.

## Verification
- In three's source: `src/nodes/accessors/Instance.js` assigns `positionLocal.assign(instanceMatrix.mul(positionLocal))`;
  `src/materials/nodes/NodeMaterial.js` does `colorNode = instanceColor.mul(colorNode)` when the object has instanceColor.
- Visually: the band sits at the same fraction of every box whatever its instance scale.

## Example
Chess Explosion's floating board (src/world/study/materials.ts): the walnut slabs are instanced unit boxes
with a gilt band from `positionGeometry.y`; the book covers are one InstancedMesh with per-instance leather
colours and a TSL mottle.

## Notes
- Text in WebGPURenderer scenes: drei `<Text>` (troika) patches GLSL via onBeforeCompile and does not run
  under the node renderer. Draw text to a CanvasTexture on a plane (set `colorSpace = SRGBColorSpace`),
  or use TextGeometry / drei `<Text3D>`. drei `<Html>` works without `occlude`.
- `positionGeometry` is exported from 'three/tsl' in r186.
- Bloom in r186: `RenderPipeline` (PostProcessing is deprecated since r183) with
  `bloom` from 'three/addons/tsl/display/BloomNode.js'; in R3F render it in `useFrame(() => pipeline.render(), 1)`.
  Gate it on the quality tier known only after `renderer.init()` (the WebGL2 fallback), not at first render.

## References
- three.js r186 source: src/nodes/accessors/Instance.js, src/materials/nodes/NodeMaterial.js,
  src/renderers/common/RenderPipeline.js, examples/jsm/tsl/display/BloomNode.js.
- https://threejs.org/manual/en/webgpurenderer.html (onBeforeCompile / ShaderMaterial not supported).
