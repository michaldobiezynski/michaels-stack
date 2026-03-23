---
name: threejs-3d-chess-patterns
description: |
  Common Three.js pitfalls and solutions discovered while building a 3D chess application.
  Use when: (1) arrows/annotations render at wrong Y or point in wrong direction,
  (2) OrbitControls steals right-click events needed for custom interactions,
  (3) board squares invisible due to Z-fighting with arena/floor geometry,
  (4) overlay meshes (highlights) hidden inside board geometry,
  (5) Euler rotation order causes wrong orientation on cylinders/cones.
  Covers Three.js OrbitControls, raycasting, emissive materials, renderOrder,
  and quaternion-based rotation for directional arrows.
author: Claude Code
version: 1.0.0
date: 2026-02-22
---

# Three.js 3D Chess Board Patterns

## Problem 1: OrbitControls Steals Right-Click Events

### Context / Trigger Conditions
- Right-click handlers for custom interactions (arrow drawing, square highlighting) never fire
- OrbitControls is initialised on the same canvas element
- `mousedown` with `button === 2` events are swallowed

### Solution
OrbitControls uses right-click for panning by default. Disable it explicitly:

```js
controls.mouseButtons = {
  LEFT: THREE.MOUSE.ROTATE,
  MIDDLE: THREE.MOUSE.DOLLY,
  RIGHT: null  // Free up right-click for custom use
};
```

Also suppress the context menu on the canvas:
```js
renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());
```

And attach `mouseup` to `window` (not the canvas) so releases outside the canvas are caught:
```js
window.addEventListener('mouseup', e => { if (e.button === 2) onRightMouseUp(e); });
```

---

## Problem 2: Arrow/Annotation Y Position Hardcoded

### Context / Trigger Conditions
- Arrows or annotations are invisible after changing board Y position
- Board was raised (e.g., to clear arena geometry) but arrows still render at old Y
- Arrow shafts appear underground or inside the board

### Solution
Never hardcode Y positions for overlays. Use a configurable value synced with the board:

```js
// In arrows module
let arrowY = 0.15;
export function setArrowY(y) { arrowY = y; }

// In main.js after board creation
Arrows.setArrowY(BOARD_Y + 0.08);
```

For highlights/overlays on the board surface, position them ABOVE the board's top face:
```js
// Board squares are BoxGeometry(1, 0.12, 1) at BOARD_Y
// Top face is at BOARD_Y + 0.06
// Highlights must be ABOVE that:
mesh.position.y = arrowY + 0.01; // Not arrowY - 0.04!
```

Add `depthTest: false` to ensure overlays always render on top:
```js
const mat = new THREE.MeshBasicMaterial({
  color, transparent: true, opacity: 0.6,
  depthTest: false  // Always visible regardless of Z-order
});
```

---

## Problem 3: Euler Rotation Order Breaks Arrow Direction

### Context / Trigger Conditions
- Cylinder or cone arrows point sideways instead of toward the target
- Combining `rotation.z` and `rotation.y` on a CylinderGeometry gives wrong results
- Arrow appears horizontal when it should be vertical

### Solution
Euler rotations are applied in XYZ order by default. Setting `.rotation.z = -PI/2` then `.rotation.y = angle` does NOT compose as expected.

**For arrow shafts**: Use a BoxGeometry instead of CylinderGeometry. A flat box with its length along Z only needs `rotation.y`:
```js
const shaftGeo = new THREE.BoxGeometry(0.12, 0.06, shaftLength);
shaft.rotation.y = Math.atan2(dx, dz); // Simple single-axis rotation
```

**For arrowheads (cones)**: Use quaternion rotation from +Y to target direction:
```js
const up = new THREE.Vector3(0, 1, 0);
const dir = new THREE.Vector3(dx / distance, 0, dz / distance);
head.quaternion.setFromUnitVectors(up, dir);
```

This works correctly for ALL directions — vertical, horizontal, and diagonal.

---

## Problem 4: Board Invisible Under Arena Geometry

### Context / Trigger Conditions
- Chess board disappears when switching arena themes
- Board at Y=0 conflicts with arena floors at similar Y values
- Z-fighting causes board squares to flicker or disappear

### Solution
1. Raise the board well above arena geometry with a visible pedestal:
```js
const BOARD_Y = 1.0;
boardGroup.position.y = BOARD_Y;

// Add pedestal so board doesn't float
const base = new THREE.Mesh(
  new THREE.BoxGeometry(8.6, BOARD_Y, 8.6),
  new THREE.MeshStandardMaterial({ color: 0x1a1208 })
);
base.position.y = -BOARD_Y / 2;
boardGroup.add(base);
```

2. Use emissive materials on board squares so they self-illuminate regardless of arena lighting:
```js
const material = new THREE.MeshStandardMaterial({
  color: squareColor,
  emissive: squareColor,
  emissiveIntensity: 0.35  // Ensures visibility in dark arenas
});
```

3. Set `renderOrder` to ensure board draws on top:
```js
square.renderOrder = 1;
```

## Verification
- Arrows point correctly in all 4 directions (up, down, left, diagonal)
- Right-click on board squares triggers highlight, not camera pan
- Board visible on all arena themes with consistent appearance
- Highlights visible as coloured overlays on board squares

## Notes
- `switchTheme(scene, themeId, camera, controls)` — argument order matters. A common bug is swapping `scene` and `themeId`.
- When pieces are positioned in world space but board squares are in a group, ensure `userData.baseY` is set AFTER the position override, not during model creation.
- Loaded 3D arena models can be massive and block the board — consider using procedural geometry for arenas or positioning models to not overlap the board centre.
