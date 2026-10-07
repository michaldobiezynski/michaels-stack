---
name: threejs-swap-attribute-arrays-for-dataset-toggle
description: |
  Toggle between two datasets (e.g. raw vs collapsed/canonical graph, before/after, two
  layouts) in a three.js Points or LineSegments object without rebuilding geometry or
  dropping frames. Use when: (1) a UI toggle switches which ~10k-100k points/segments are
  drawn, (2) rebuilding BufferGeometry on toggle stalls the frame or leaks, (3) you need
  per-mode attribute arrays (position, colour, alpha) with one draw call. Pattern:
  allocate every attribute at max(sizeA, sizeB), keep both Float32Arrays, assign
  `attribute.array = other` + `needsUpdate = true`, and `geometry.setDrawRange(0, n)`.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Swap BufferAttribute arrays to toggle datasets in three.js

## Problem
A graph viewer needed a 'canonical topics' toggle that replaces ~30k raw edges with
~20k projected edges and hides merged points. Rebuilding `BufferGeometry` on every
toggle re-allocates GPU buffers and briefly drops the frame; managing two meshes doubles
draw calls and picking logic.

## Context / Trigger Conditions
- One `THREE.Points` / `THREE.LineSegments` with custom per-vertex attributes.
- Two (or a few) alternative datasets of different length, switched by UI.
- Symptom of the naive approach: hitch on toggle, or `attribute.array` length mismatch
  errors, or `setDrawRange` ignored because the array was replaced with a shorter one.

## Solution
1. At load, compute both attribute sets as `Float32Array`s sized to
   `max(countA, countB) * itemSize` (pad with zeros).
2. Create each `BufferAttribute` once from set A with `DynamicDrawUsage`.
3. On toggle: `attr.array = setB.array; attr.needsUpdate = true;` for every attribute,
   then `geometry.setDrawRange(0, countB * verticesPerItem)`.
   Because the byte length is unchanged, three.js re-uploads with `bufferSubData`
   instead of re-creating the buffer.
4. Hide members that do not exist in the other mode by writing 0 alpha (and parking them
   off-frustum in the vertex shader), not by removing vertices, so indices stay stable
   for picking and adjacency.

## Verification
Read `geometry.drawRange.count` and `attribute.array.length` after toggling: the array
length must stay constant while `drawRange` changes (observed: length 183,066, draw range
40,540 in canonical mode). Frame rate should not dip on toggle.

## Notes
- Keep index-based lookups (raycast hit -> node) mode-aware: map a hit index through the
  active mode's id table.
- If the two datasets differ wildly in size, padding wastes memory; a 2x gap is fine.
