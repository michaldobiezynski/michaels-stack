---
name: threejs-additive-edges-wash-out-under-bloom
description: |
  Diagnose a dense three.js graph/point-cloud whose centre renders as a white blob after
  recolouring points, even though the new colours look fine elsewhere. Use when: (1) points
  are drawn correctly with edges hidden but the core goes white when edges are on,
  (2) darkening or desaturating the point palette and lowering UnrealBloomPass strength do
  not clear it, (3) edges use AdditiveBlending with low per-edge opacity. Root cause: tens of
  thousands of additive edge segments sum to white over dense regions regardless of point
  colour; bloom then amplifies it. Fix: damp edge alpha (e.g. 0.25x) in the colour mode where
  regions must be distinguishable, or switch edges to normal blending; treat palette and bloom
  as secondary levers. Also: pastel palettes designed for light backgrounds need an HSL
  lightness/saturation remap for a dark theme, compressed (not capped) so pairs that differ
  only in paleness stay distinct.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Additive-blended edges wash out dense graph regions under bloom

## Problem
A 13k-node three.js viewer switched from colour-by-source to colour-by-course (pastel
palette) and the centre of the cloud became a featureless white mass. Darkening the palette
and reducing bloom strength barely helped.

## Context / Trigger Conditions
- One `LineSegments` with `AdditiveBlending`, opacity 0.1-0.3, tens of thousands of segments.
- `UnrealBloomPass` in the composer.
- Symptom test: hide all edges; if points render in distinct regions, the edges are the cause.

## Solution
1. Confirm with the edge-hiding test above before touching colours.
2. In the mode that must show regions, multiply edge alpha by ~0.25 (or use
   `NormalBlending` for edges); keep points additive if desired.
3. Then, secondarily: derive a dark-theme palette from the published one: convert to HSL,
   keep hue, lift saturation into ~0.65-0.85, COMPRESS lightness into ~0.26-0.60 (a hard cap
   collapses courses that differ only in paleness), leave deliberately neutral entries
   unsaturated; and scale bloom strength to ~0.6x in that mode.
4. Re-check the swatch legend uses the same derived colours as the points.

## Verification
Screenshot at the default framing: individual regions distinguishable, no white core; the
status line (visible node/edge counts) unchanged between colour modes.

## Notes
- Hues that are ~50 RGB apart in a pastel palette can end up ~10 apart after the
  saturation lift; fix those in the source palette, not in the remap.
- Points under bloom bloom less than lines because their screen coverage is smaller;
  the lines are where the energy accumulates.
