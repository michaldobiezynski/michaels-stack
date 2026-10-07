---
name: playwright-3d-canvas-click-tests
description: |
  Reliable Playwright tests that click things inside a three.js / React Three Fiber canvas with a moving
  camera (drei CameraControls / camera-controls). Use when: (1) a click at a projected 3D point does
  nothing, or hits the wrong object, right after page load, (2) a projected screen point is off-screen
  (negative or beyond the viewport) and the test still "clicks" it, (3) a test asserting "a drag rotates
  the view without triggering a tap" passes even with the drag guard removed, (4) you need a stable way to
  tap a figure rather than the square under it, (5) probe-driven tap tests pass but a real click on an
  object (a crown, a hat, a prop, an obstacle) acts on the square behind it or sends the player off an edge,
  (6) tests run from a git worktree while another Playwright run is live give results for the wrong code,
  (7) tapping the tile under the player's own figure (a pawn standing on a rune) does nothing, or the hover
  prompt vanishes exactly where the figure stands, because a shared figure component swallows the pointer.
author: Claude Code
version: 1.4.0
date: 2026-09-27
---

# Clicking things in a 3D canvas from Playwright

## Problem
Tests that project a world point to the screen and click it are flaky or vacuous: the camera is still
flying in, the point is off-screen, or the behaviour under test never happens in headless Chrome at all.

## Context / Trigger Conditions
- R3F + drei `CameraControls` (camera-controls), a follow camera or an opening camera move.
- A test hook such as `window.probe.cellToScreen(x, z, height)` returning viewport pixels.

## Solution
1. **Expose "camera at rest" and wait for it.** Listen to camera-controls events:
   `controls.addEventListener('transitionstart', () => probe.cameraStill = false)` and
   `controls.addEventListener('sleep', () => probe.cameraStill = true)`; tests
   `waitForFunction(() => probe.cameraStill)` before projecting. ('rest' fires early in a slow transition;
   'sleep' fires when movement has ended.)
2. **Assert the projected point is on screen** before clicking
   (`x > 0 && x < width && y > 0 && y < height`); a close follow camera easily leaves targets off-screen.
3. **Offer a skip for cinematic intros** (`?intro=0`) and keep one test on the real opening.
4. **Prove drag tests bite.** In Chrome, camera-controls swallows the click after a drag, so a test
   "drag turns the view and does not send the pawn" passes with or without your `e.delta > slop` guard.
   Assert the view actually turned (expose the camera's azimuth angle), and treat the delta guard as a
   safety net for other browsers, documented as such.
5. **Clicking a figure, not its square:** R3F objects with an onClick that always `stopPropagation()` swallow
   taps even when no handler logic runs; give every tappable figure an explicit handler (or none at all),
   and test by clicking the figure's body (`cellToScreen(x, z, 0.7)`), waiting until it stands still.
   Watch for a *shared* figure component (one `Piece` used for the game's pieces, the world's guards and the
   player's own avatar) that attaches `onClick`/`onPointerOver` with `stopPropagation()` whether or not the
   caller passed callbacks: every instance becomes a pointer sink. For the player's avatar the symptom is that
   the tile it stands on can no longer be tapped or hovered (the tile's `onPointerOut` fires as the pointer
   reaches the figure, resetting the hover), so a feature that works "underfoot" (tap the rune you stand on)
   is dead exactly where the player aims. Fix at the call site by passing callbacks that map the figure to its
   tile (`onClick={() => onTap(cell.current)}`, `onHover={(over) => onHover(over ? cell.current : null)}`)
   rather than making the figure pointer-transparent: a ray through a transparent figure's head lands on the
   tile *behind* it and offers the wrong action. Diagnose by sliding the mouse in small steps from a
   neighbouring tile onto the figure's tile and logging the hover probe at each step.
6. **Probe taps hide pass-through bugs.** A test hook that "taps" a cell by calling the app's `onTap(cell)`
   skips R3F's raycast. R3F only hit-tests objects that carry pointer handlers, so anything without them
   (a crown in a glass ward, a hat, obstacles, props) is transparent to the mouse: a real click lands on the
   square behind it, or on an invisible catch-all plane beyond the edge, and the wrong thing happens. Test
   key interactions (and hover prompts) with real mouse clicks on the object's body, and give everything that
   stands on a square handlers that forward to that square (`stopPropagation`), e.g. one helper
   `standsOn(cell, onTap, onHover)` spread onto each object's root group.
   **Hidden is not gone:** three's `Raycaster` ignores `visible`, so a mesh faded out with `visible = false` (a
   ward, a glow, a halo, a crown shrunk after it is taken) inside a group that carries handlers still wins the
   pointer, and silently steals clicks meant for whatever stands behind it (Chess Explosion: the crown's faded
   ward sat between the camera and the door behind it, so the door could only be "clicked" by the test probe).
   Give purely visual meshes `raycast={() => null}`, and test the thing behind with the real mouse.
   A catch-all invisible plane (say, "open air past the board's edge" at the board's height) also wins over
   anything *below* it, such as props on a desk several units lower: mark those props
   `userData.takesPointer = true` and have the plane's handlers `return` without `stopPropagation()` when
   `e.intersections` includes such an object (walking up `.parent`), so the event reaches the prop.
7. **One Playwright run per port.** `webServer.reuseExistingServer` reuses whatever already listens on the
   port, so a second run from a git worktree while another run is live silently tests the first checkout's
   code. Make the port configurable (`const PORT = Number(process.env.E2E_PORT) || 5175` in
   playwright.config.ts, used for both `baseURL` and `webServer.command`) and give each parallel agent's
   worktree its own (`env E2E_PORT=5185 npx playwright test ...`); say so in every agent's brief, and point
   each agent's stills scripts at its own worktree and port too.
8. **Frames:** for a stand-in iframe, wait until its frame has navigated off about:blank and its script ran
   (`expect.poll(() => page.frames().some(f => f.url().includes(path)))`, then `frame.waitForFunction(...)`).

## Verification
- Mutation-check: disable the behaviour under test (remove the guard, the handler, the component) and see
  the test fail; restore and see it pass.

## Example
Chess Explosion e2e/world.spec.ts: `openWorld()` waits for `world.ready` and `cameraStill`; the tap tests
click `cellToScreen` points after asserting they are on screen; the drag test asserts `cameraAngle` changed.
The describe block 'what stands on a square takes the pointer as that square' clicks the crown at its float
height (1.45), the hat, a geode and a summit candlestick with the real mouse; all failed before `standsOn`
(the crown click went through to the square behind or off the summit) while every probe-tap test passed.

## Notes
- Headless Chrome with `channel: 'chrome'` and `--ignore-gpu-blocklist` renders WebGPU on the real GPU at 60 Hz.
- Frame-timing-dependent assertions (per-frame CPU simulations capped at 1/30 s) flake under load; step
  such simulations at a fixed timestep instead of loosening the threshold.
