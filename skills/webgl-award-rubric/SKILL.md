---
name: webgl-award-rubric
description: |
  A rubric of what wins Three.js Journey-style WebGL/WebGPU challenges, distilled from ~50 captured
  entries (winners and themed entries, 27/09/2026), for auditing an interactive 3D site, game or home page
  and turning the gaps into a ranked backlog. Use when: (1) asked to make a 3D experience "award-worthy",
  "challenge-winning", "polished in every aspect" or "the best version it can be", (2) auditing a three.js /
  React Three Fiber scene's first impression, guidance, visual craft, motion, sound, delight, theme,
  performance or interface, (3) deciding what to build next from research captures. Pairs with
  threejs-journey-challenge-research and webgl-demo-capture.
author: Claude Code
version: 1.0.0
date: 2026-09-27
---

# The challenge-winning rubric

## Problem
"Make it award-worthy" is not actionable. Winners share concrete, checkable traits; auditing against
them turns taste into a backlog you can test and film.

## How to audit
1. Film your own page the way you film entries (`webgl-demo-capture`): cold load, first 10 s, 60 s of play.
2. Score every check below 0-3 (0 missing, 1 present but rough, 2 good, 3 best-in-class), with the still or
   clip that shows it. Score what a judge sees in the first minute, not what the code could do.
3. Rank gaps by **impact on the first minute x how often it is seen / effort**, and build them in that order
   (acceptance test first where behaviour is involved; before/after stills for every visual change).

## The checks (exemplars in brackets)

### A. First impression (0-10 s)
- A themed loading moment with real progress, never a blank canvas (Lumen Vale, Caatinga).
- A cold open or title card that states the premise in one line before or as the world appears
  (Caatinga's three-beat typography, Enchanted Grove's storybook card, Lumen Vale's mission brief).
- An establishing camera move or reveal (board/world assembling, a sweep to the hero).
- The 3D world stays visible behind every menu and overlay (Bottled Battle, Drysland, Darts Game's blur).

### B. Guidance
- A short narrative plus explicit controls, skippable, shown once (Lumen Vale, Coral Shallows).
- Contextual prompts that appear only near/over what can be acted on (Lumen Vale; "Strike the guard").
- An objective tracker and a guide marker to the next goal (Utanomori, Coral Shallows).
- A permanent, unobtrusive control legend or hint line (Castle Color Valley, Detour).
- Hover affordances on interactive things: cursor, ring, outline or icon (Darts Game, My Sheep Farm).

### C. Visual craft
- One coherent palette and material language across everything, backdrop included (Woolen World,
  NamhanSanseong's named pigments).
- Lighting with intent: warm pools against darkness (Cozy Reading Room), a hero light on what matters
  (Darts Game's per-prop spotlights), a light pool under the player for readability (Detour).
- A finishing pass: bloom on emissives, tilt-shift or depth of field, vignette, grain (Lego, AEDENA, Rabbit
  Explorer, Spectral Manor's bokeh push-ins).
- Stylisation that reads as authored: outline/toon (Cleanse the Corrupted Garden, on WebGPU), hatching
  (AEDENA), brush-stroke water (Magical Island).
- Atmosphere in layers: two particle systems of different character, fog, motes in the light (Spectral
  Manor, Lumen Vale's fireflies).
- Hero materials that hold up close: glass, flame, water, crystal (Terrarium's jar, Style Experiments'
  caustics).

### D. Motion and feel
- Every action answered at once: sound, particles, a squash, a camera nudge ("juice").
- Easing everywhere; nothing snaps; arrivals settle (overshoot, squash and stretch).
- Camera moments: follow smoothly, frame the action, fly to a hotspot and back (Stained glass castle).
- Input that never breaks state: no reset to the title under fast drags (six+ entries failed this).

### E. Sound
- Layered ambience plus event sounds (and music where it fits), each with its own switch (Drysland,
  Utanomori, Seeking Eywa).
- Variation on repeated sounds (Caatinga's three footstep samples); nothing clips or grates on repeat.

### F. Delight
- At least one hidden thing that rewards exploring (Floating Island's sleeping cat, Sakura's ghost).
- A toggle that transforms the scene (day/night: Calm Nature, Ash Cozy Room, The Path).
- Something to play with for its own sake (Koinobori's public GUI, Tamagotchi care loops).

### G. Theme and story
- Every element earns its place in the fiction; nothing generic on screen.
- Credits in the fiction or an about panel with context (Castle of Shadows' in-world credits,
  NamhanSanseong's history panel).

### H. Performance and robustness
- 60 fps on a mid laptop; no hitch on the first strike/explosion (warm up shaders and pools while loading).
- Compressed assets (Draco/meshopt geometry, KTX2 textures: Seeking Eywa) and a fast first interaction.
- Graceful fallbacks (no WebGL/WebGPU, reduced motion) and no console errors.
- Watch transparent/emissive overdraw: a simple-looking field of petals and fireflies ran at 26 fps.

### I. Interface polish
- One HUD language: type, colour, corner radius, motion (Lumen Vale's consistent glow HUD).
- Readable over any background (scrims, pills, contrast), aligned to a grid, never covering the action.
- Buttons that feel physical: hover, press, focus rings, keyboard access.
- Clear states: turn, check, score, win/lose, with a moment for each (Bottled Battle's live menus).

## Verification
The audit lists every check with a score and evidence; the backlog cites the check each item raises; each
shipped item has a test (behaviour) or stills (visuals) and a re-score.

## Notes
- Most winners run WebGL2 at 60 fps; WebGPU is rare, so a WebGPU/TSL build is itself distinctive but must
  keep a WebGL2 fallback.
- Winners lean on licensed assets as often as original geometry; originality of the idea and the polish of
  the feel matter more than asset provenance.
- Re-derive the rubric when a new challenge's winners are announced: `threejs-journey-challenge-research`.
