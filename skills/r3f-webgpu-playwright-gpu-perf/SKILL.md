---
name: r3f-webgpu-playwright-gpu-perf
description: |
  Set up React Three Fiber v9 on three's WebGPURenderer (with WebGL2 fallback) and verify
  frame rate in a REAL GPU browser from Playwright. Use when: (1) `npm install` refuses
  react 19.3 because @react-three/fiber 9.x pins `react >=19 <19.3`, (2) you need the
  async `gl` prop pattern for WebGPURenderer and TypeScript rejects
  `renderer.backend.isWebGPUBackend`, (3) R3F logs "PCFSoftShadowMap has been removed"
  under WebGPU, (4) an e2e test must measure fps or take screenshots of GPU rendering
  (Playwright's bundled headless shell falls back to a software rasteriser; installed
  Chrome's headless mode gets the real GPU but runs at 60 Hz), (5) a
  Playwright spec needs to import a plain .mjs helper or fetch a static asset for
  assertions, (6) the canvas silently freezes on one frame while state, fps and
  raycast clicks keep working (a useFrame subscriber with a positive priority turned
  off automatic rendering), (7) Playwright's recordVideo/screencast produces a video
  of a WebGPU canvas that never changes (capture with a screenshot loop instead), (8) a frame of
  14 ms or more each time a component with its own TSL node material mounts (share one graph and
  read per-object values with uniform().onObjectUpdate), (9) a panel of drei <Html> labels over a
  WebGPU canvas drops one or two frames (33 to 50 ms) when it appears, intermittently, and no warm-up
  cures it (draw the labels in the scene as CanvasTexture sprites instead).
  Includes the window probe pattern for fps/phase readouts and a pixel-luminance guard.
author: Claude Code
version: 1.6.0
date: 2026-09-25
---

# R3F v9 + WebGPURenderer + Playwright GPU verification

## Problem
A greenfield R3F project on WebGPU needs (a) a dependency set that actually installs,
(b) the renderer wired without type errors, and (c) an automated "runs at 60 fps" check
that is not a lie.

## Context / Trigger Conditions
- Registry state on 10/09/2026: three 0.186.0, @react-three/fiber 9.7.0 (peer `react >=19 <19.3`),
  @react-three/drei 10.7.8, @react-three/rapier 2.2.0 (peer fiber ^9.0.4), react 19.3.0 latest.
- Type error: `Property 'isWebGPUBackend' does not exist on type 'Backend'` (@types/three 0.185).
- Console warning each shadow render: `THREE.WebGPURenderer: PCFSoftShadowMap has been removed`.
- Perf assertions passing with absurd or tiny fps in headless mode.

## Solution

### Dependencies
Pin `react`/`react-dom` to the latest 19.2.x (`npm view react@19.2 version`) until fiber
lifts its cap. TypeScript 7.0.2 and Vite 8.3 work with the standard `moduleResolution: bundler`
tsconfig; Vitest 5 wants a separate `vitest.config.ts` importing from `vitest/config`.

### Renderer
```tsx
import { WebGPURenderer } from 'three/webgpu'
<Canvas shadows="percentage" dpr={[1, 2]}
  gl={async (props) => {
    const r = new WebGPURenderer(props as ConstructorParameters<typeof WebGPURenderer>[0])
    await r.init()
    probe.backend = (r.backend as { isWebGPUBackend?: boolean }).isWebGPUBackend ? 'webgpu' : 'webgl2'
    return r
  }}>
```
`shadows="percentage"` selects PCFShadowMap and silences the warning; plain `shadows`
picks the removed PCFSoft type. Classic `MeshStandardMaterial`, `InstancedMesh` with
`setColorAt`, drei `OrbitControls`/`useGLTF` and @react-three/rapier all work unchanged
on the WebGPU backend. Skip `<StrictMode>` when physics bodies are involved.

### Probe for tests
Expose a plain object on `window` and record frames from `useFrame`:
```ts
export const probe = { ready: false, phase: 'idle', backend: 'unknown', fps(windowMs = 2000) {...} }
window.__chessExplosion = probe   // guard typeof window for Vitest
```
`fps()` counts timestamps in the last window: `(n - 1) / (span / 1000)`.

### Playwright with a real GPU
```ts
use: { channel: 'chrome', headless: process.env.E2E_HEADED !== '1',
       launchOptions: { args: ['--ignore-gpu-blocklist'] } }
webServer: { command: 'npx vite --port 5175 --strictPort', url: 'http://localhost:5175', reuseExistingServer: true }
```
Use installed Chrome (`channel: 'chrome'`), not Playwright's bundled headless shell, which
falls back to SwiftShader and reports the WebGL2 backend at a fraction of the rate. Measured
23/09/2026 on an Apple Silicon Mac: installed Chrome's headless mode gets WebGPU on the same
Apple Metal 3 adapter as a window (`navigator.gpu.requestAdapter()` then `adapter.info`:
vendor 'apple', architecture 'metal-3'), renders identical frames, and runs at a fixed 60 Hz
where a window follows the 120 Hz display. So default to headless (windows popping up
interrupt the user) and keep `E2E_HEADED=1` for watching or display-rate perf work.
- Make frame checks independent of the rate: compare fps with the idle fps measured first
  (`fps > idle * 0.75`), and judge stalls against the median frame interval
  (`max(25, 2.2 * median)` ms), since one late frame at 60 Hz is already 33 ms.
- Do not uncap headless (`--disable-gpu-vsync --disable-frame-rate-limit`): it ran at 769 fps,
  no closer to real play than 60, with the GPU flat out.

### Spec conveniences
- `page.evaluate` with a serialised arrow: `page.evaluate((src) => new Function('p', \`return (\${src})(p)\`)(window.__chessExplosion), fn.toString())`.
- Fetch a static asset for assertions: `await page.request.get('/models/x.glb')` then `.body()`.
- Import a repo `.mjs` helper into a `.ts` spec with `// @ts-expect-error plain ESM helper`.
- Collect `pageerror`, console `error` and `response.status() >= 400` into one array and assert it is empty at the end; the favicon 404 is avoided with `<link rel="icon" href="data:,">`.
- A standalone diagnostic script that imports `@playwright/test` must live inside the project tree (ESM resolves relative to the file), not in a temp directory.

### Two silent failure modes (both verified 11/09/2026)
- **A positive `useFrame` priority stops automatic rendering.** `useFrame(cb, 1)` means
  "I take over rendering"; R3F stops calling `gl.render`, the canvas keeps its last frame
  (here the Suspense fallback), yet `useFrame` still ticks (fps probe reads 120), state
  updates flow and R3F raycasting still hits the invisible meshes, so click-driven e2e
  tests pass. Ordering after another subscriber is done by mount order at the same
  priority (drei's controls run at -1, so priority 0 already runs after them).
- **Guard with pixels, not state.** Add one screenshot-based assertion: project a square
  to screen (`camera.project`), `page.screenshot({ clip })`, decode with `pngjs`, and
  compare mean luminance (a pale piece on a dark square > 110, a dark piece on a light
  square < 90). It is the only check that catches "nothing is drawn".
- **Playwright cannot video-record a WebGPU canvas.** `recordVideo` / CDP screencast only
  emits frames on compositor changes and never sees WebGPU presents, so the file shows the
  first frame forever (a DOM heartbeat element does not help). `page.screenshot` does
  capture it, at ~45-55 fps for 1280x720 JPEG on an M5 Pro. Recipe: run the app with a
  `?record=N` slowdown that scales the R3F clock and every real-time timer by N, loop
  screenshots to disk with timestamps, then `ffmpeg -f concat` with per-frame durations
  divided by N and `-vf fps=30`. N=4 yields ~180 source fps and smooth 30 fps video.

### Instanced soft particles that work on both backends
`three/webgpu` sprites instance natively: `const s = new Sprite(new SpriteNodeMaterial({ transparent: true, depthWrite: false })); s.count = N`
with `material.positionNode = instancedBufferAttribute(posAttr)` (InstancedBufferAttribute, 3),
`scaleNode = instancedBufferAttribute(scaleAttr)` and
`opacityNode = texture(softCanvasTexture, uv()).a.mul(instancedBufferAttribute(alphaAttr))`.
Do not wrap the attribute node in `float()` (TypeScript rejects the overload). Update the
arrays on the CPU each frame and set `needsUpdate`. One draw call, per-puff fade, renders on
WebGPU and the WebGL2 fallback alike; classic `PointsMaterial` cannot fade per point.

### Layering procedural rotation on a scrubbed AnimationMixer clip
`PropertyMixer.apply` writes a bone only when the sampled value differs from the previous
frame. A clip held on one time (paused action, `mixer.update(0)`) therefore stops resetting
the bone, and any per-frame `bone.rotateOnAxis` / `rotation.x +=` you add on top ACCUMULATES
(16 degrees per frame turned a sword from forward to straight up in six frames, and read as
"spinning arms"). Keep a `base` quaternion per bone: copy `base` into the bone before
`mixer.update`, copy the bone back into `base` after, then apply the additive rotation.
Also measure, do not assume, which local axis of a glTF joint swings it sagittally: pick the
local axis most aligned with the figure's lateral world axis and nudge it to learn the sign.

### Stale models in an open tab
drei's `useGLTF` caches each URL for the life of the page, and Vite HMR swaps JS without
reloading them, so a user iterating in an open tab keeps seeing OLD GLBs after an asset
rebuild while running NEW code. Their screenshots then show poses that no longer exist.
Write a `manifest.json` with `builtAt` in the asset build, poll it with `cache: 'no-store'`,
and show "models built HH:MM" plus a reload button when it changes. Screenshot filenames
from `toISOString()` are UTC: compare against local commit times carefully.

### Screenshot download from a WebGPU canvas
`gl.render(scene, camera); gl.domElement.toBlob(cb, 'image/png')` in the same task gives a
valid PNG of the current frame (no preserveDrawingBuffer needed); trigger an `<a download>`
click with an object URL. Playwright verifies it with `page.waitForEvent('download')` and the
PNG magic bytes. Pause content (physics `paused`, mixer/dust early-return via a shared store)
rather than zeroing the R3F clock, so camera controls keep working while frozen.

## Verification
`npx playwright test` prints `renderer backend: webgpu` and the fps; screenshots taken with
`page.screenshot` show the WebGPU frame. `npm run build` (tsc + vite) passes; expect one
~4 MB chunk (three/webgpu plus inline Rapier WASM) until code-splitting is added.

## Example
`~/development/projects/chess-explosion`: `src/App.tsx`, `src/debug/probe.ts`,
`playwright.config.ts`, `e2e/shatter.spec.ts`.

## Notes
- The fps figure is the display refresh when the app is not GPU-bound; it proves "no dropped
  frames", not headroom. Compare against `screen` refresh or run with more load for headroom.
- `useGLTF.preload` only starts the fetch; a component that suspends later inside the live
  Suspense boundary blanks the scene. Call `useGLTF(url)` for every model at startup.

## References
- R3F Canvas `gl` prop and WebGPU example: https://r3f.docs.pmnd.rs/api/canvas
- @react-three/rapier v2 (fiber v9 / React 19): https://github.com/pmndrs/react-three-rapier
- Playwright browsers and channels: https://playwright.dev/docs/browsers
- Related: [[threejs-gltf-chunks-to-rapier-bodies]], [[blender-cell-fracture-headless]]

## Clicks that never reach the canvas (added 2026-09-11)
When some board/scene clicks stop working while others still do, check `document.elementFromPoint(x, y)` at the projected 3D point before suspecting the raycaster. A fixed, transparent HUD (`position: fixed; display: flex`) stretches its children to the widest row, so short text rows (a move list) become wide invisible strips over the canvas that grow with the game. R3F only raycasts objects with handlers, so rubble/particles never block picks; DOM overlays do. Fix: `align-items: flex-start`, content-sized lists, `pointer-events: none` on the overlay with `auto` on its controls; add a spec that asserts every projected square resolves to `CANVAS`.

## First-use stalls: warm up what a big moment draws for the first time (added 2026-09-22)
Symptom: "a small lag right at the impact", only on the FIRST capture of a session. Average fps
hides it; record every requestAnimationFrame timestamp in an init script and report the worst gap
in a window around each event (here 41.8 ms against an 8.3 ms median, on capture 1 only; later
captures, even in the other colour, were clean). Bisect by switching parts off (the dust burst made
no difference). Cause: the rubble chunks were plain meshes while every visible piece was a skinned
mesh, so the first chunk needed a new shader variant and every type's chunk geometry its first
buffer upload, all on the hit frame. Fix: at load, mount every chunk of every type with the exact
materials the effect uses (both colours), castShadow on, frustumCulled off, placed under the floor
but inside the shadow camera's range so the shadow pass compiles too, for 3 frames, then unmount.
Worst impact frame 41.8 ms -> ~9 ms. Guard it with a spec that fails over 25 ms. Separately check
for DELIBERATE slow-downs (slow-mo envelopes, hit-stop constants) before telling a user the lag is gone.

## First-hover stall from skinned-mesh bounds; same-conditions benchmarks (added 2026-09-23)
- Symptom: an intermittent 75-110 ms frame "on a right-click" that was really on the pointer move
  before it. React Three Fiber raycasts interactive objects on pointer move, and three.js
  SkinnedMesh.raycast computes its bounding sphere and box lazily by skinning every vertex (32 pieces,
  about 7k vertices each). Find it by timing handlers (they took 0.3-5 ms) and logging when the long
  rAF gap happens relative to the click (-153 ms: the hover). Fix: after building each rig,
  `scene.updateMatrixWorld(true)` then `computeBoundingBox()` and `computeBoundingSphere()` on every
  SkinnedMesh. Worst frame across the first click went from 75 ms to 10 ms.
- A stress-test fps "regression" (96 to 67) turned out to be the machine: master itself read 73 later
  the same day on mains power with no thermal warning. Compare branches under the same conditions:
  `git worktree add $TMPDIR/bisect-<sha> <sha>`, symlink node_modules (and any untracked generated
  assets such as public/engine), run the same spec in each, then `git worktree remove --force`.

## Per-object values in ONE shared TSL graph, not a graph per material (added 2026-09-23)
- Symptom: every time a component with its own node material mounts, a frame of 14 ms or more; many
  at once (jumping back through a game that remounts pieces) gave a 91.8 ms frame. Each piece built
  `m.colorNode = mix(..., uniform(x), ...)` itself, and a `uniform()` node's cache key includes its
  id, so every material had a distinct graph and the WebGPU backend compiled a pipeline for each.
- Fix: build the graph ONCE at module scope and give it to every material. Keep the per-piece
  values as plain properties on the material (`m.stainStrength = new Vector3()`) and read them with
  `uniform(defaultValue).onObjectUpdate(({ material }) => material.stainStrength ?? FALLBACK)`.
  The fallback matters: the shadow pass draws with its own depth material, which lacks the property.
  Worst frame at Home went from 91.8 ms to 33.4 ms, with the stains still drawn per piece.
- Also release a material a component made for itself when it unmounts (`material.dispose()` and
  drop it from any set that keeps it following the environment map), or the sets grow each remount.

## Overlays that must read equally on light and dark materials (added 2026-09-24)
A TSL `mix(materialColor, stainColour, amount)` is done in linear light, and the display's
gamma stretches dark values: the same amount of pale dust on dark stone looked about twice as
heavy as dark dust on pale stone (a 1-kill mark changed 7.2% of a black piece's screen box
against 1.0% of a white one). Blend in display gamma instead:
`pow(mix(pow(base, vec3(1/2.2)), pow(overlay, vec3(1/2.2)), amount), vec3(2.2))`. Then tune
one strength for both. When a pixel metric is meant to tell two looks apart (say sprayed
versus painted), run it on the old and the new code before trusting it: a metric relative to
each mark's own strongest pixels scored the old painted marks as softer than the new ones.

## Warm-ups defeated by a prop, root-level missed clicks, and async test actions (added 2026-09-24)
- **A warm-up only covers what exists when it runs.** A promotion chooser warmed its four models
  at mount, but it was built for `colour={turn}`, so every move rebuilt the models (and disposed the
  old materials) for the other side, and the first draw after a move stalled the click by 100 ms.
  Build every variant the prop can take once (here both colours), warm them all, and switch which
  set is shown. Measure the stall in a test that plays a move first, not only on a fresh page.
- **Adding or removing a light recompiles every material** (WebGPU; the light count is part of the
  program key): a hover light mounted only while hovering stalls each hover. Keep one mounted at
  intensity 0 and move it.
- **Clicks that hit nothing interactive:** `onPointerMissed` is part of R3F's root state, so a
  component inside the Canvas can install it while it needs it:
  `const set = useThree((s) => s.set); useEffect(() => { set({ onPointerMissed: cancel }); return () => set({ onPointerMissed: undefined }) }, ...)`.
  Safer than `onPointerMissed` on a group, whose "missed" can include clicks on its own children.
- **An e2e wait that passes before the action starts:** after `page.evaluate(() => api.play('Kb7'))`,
  `waitForFunction(() => sequence === null)` resolved 11 ms later, before the move had begun, and the
  next clicks landed mid-move and were ignored. Wait for the action's effect instead
  (`history.length === 1 && sequence === null`).

## DOM labels over in-world UI (drei Html) (added 2026-09-24)
- drei `<Html>` mounts its content inside the element R3F listens on, so pointer events on a label
  bubble into R3F: a click on a label raycasts, hits nothing, and fires the root `onPointerMissed`
  (a "click elsewhere cancels" handler would cancel). Stop `pointerdown`, `pointerup`,
  `pointermove` and `click` on the label itself (its own React root dispatches at the label's
  element, before R3F's listener further up). Verified that labels click through correctly with
  this in place; the failure without it follows from the event path and was not reproduced.
- Make DOM labels on in-world items clickable if anything behind them cancels on a missed click.
- Labels fixed in pixels over items spaced in world units collide when the camera is far: measure
  pixels per world unit at the item each frame (project two points one unit apart) and spread the
  items to `max(usual spacing, labelPx / pxPerUnit)`. Keep the items' own size.

## DOM labels over a WebGPU canvas drop frames: draw them in the scene (added 2026-09-25)
- **Symptom.** A small set of drei `<Html>` labels (four promotion plaques) put on screen over the
  WebGPU canvas made that frame take 33 ms, sometimes 50 ms, instead of 16.8.
  - It was intermittent: it failed a frame-stall test in 2 of 5 runs, on master and on the branch
    alike.
  - A Chrome trace of the long frame showed about 20 ms of nothing on the renderer main thread,
    inside `BeginMainFrame`, before input dispatch. No thread in the trace was busy.
- **Not the fix.** Every one of these missed the cause:
  - pre-mounting the labels hidden;
  - painting them unseen at load (opacity 0 or 0.01, behind the canvas, or just off screen);
  - waiting longer after load.
- **Proof by elimination.** Build a reproducer that fails often (here: the labels spec run first,
  then the stall test), then remove only the labels: 5 of 5 runs came back at 16.8 ms.
- **Fix.** Draw each label onto a `CanvasTexture` at 3x its size, with the same font, ground, border
  and lit variant. Show it as a `Sprite` with a `SpriteNodeMaterial`:
  - `depthTest: false`, a high `renderOrder`, `toneMapped = false`;
  - scaled each frame to `labelPx / pxPerUnit`, so it keeps its pixel size.
- **Hover and click.** Put the handlers on the plain sprite and draw the lit sprite over it only
  while pointed at. Handlers on sprites that toggle visibility can trade enter and leave events.
- **Warm-up.** Warm them at load like other new materials: drawn with `opacity 0` for 3 frames, then
  opacity 1 and shown only when needed.
- **Colour.** The scene blends in linear light, so a translucent dark ground comes out greyer than
  the same CSS rgba. Raise its alpha (0.8 to 0.9) to match.
- **Tests.** Tests lose the DOM (`getByTestId`, `toHaveText`, `.click()`). Expose the labels
  through the probe (text, lit, projected centre, size), click by coordinates, and add a pixel check
  that each plaque's box holds its dark ground and pale lettering.
- **Measurement lesson.** Frame-stall rates of 20 to 60% make 2-run comparisons meaningless. An
  earlier "fix" looked clean in 2 of 2 runs and failed 3 of 5 later. Compare variants over at least
  5 runs of a reproducer, and tighten the stall test to allow no dropped frame
  (`max(20, 1.6 x median gap)`) once the cause is gone.

## Frame-gap tests under GPU contention (added 2026-09-27)
Worst-frame assertions (`max(gaps) < budget`) fail when other headless Chromes render WebGL on the same
GPU at the same time, for example research agents capturing demos: one promotion-chooser test read a
33.3 ms worst frame under contention and 16.8 ms twice in isolation. Before blaming a change, rerun the
failing test alone; schedule full suites when no capture browsers are running.
