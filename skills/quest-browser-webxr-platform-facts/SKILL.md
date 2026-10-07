---
name: quest-browser-webxr-platform-facts
description: |
  What a WebXR page can and cannot do on Meta Quest Browser (Quest 3/3S, Meta VR Glasses) as of
  October 2026, and the IWSDK vs React Three Fiber choice. Use when: (1) planning or scoping a
  WebXR / Immersive Web SDK (IWSDK) app or competition entry for Quest, (2) designing hand-tracking
  UI (menus, pinch, poke, palm gestures) for WebXR, (3) a palm-up or left-palm pinch unexpectedly
  opens the system menu or exits the immersive session, (4) adding voice input
  (webkitSpeechRecognition is undefined) or microphone capture to a WebXR app, (5) wanting
  passthrough camera access, persistent anchors, table/wall detection, depth hit tests or
  microgestures from the browser, (6) deciding whether IWSDK can be combined with R3F /
  @react-three/xr or three's WebGPURenderer, (7) making a tracked hand mesh both occlude virtual
  content and cast shadows in mixed reality.
author: Claude Code
version: 1.0.0
date: 2026-10-03
---

# Quest Browser WebXR platform facts (Oct 2026)

## Problem
Quest Browser's WebXR surface differs from native Meta SDKs and moves fast. Plans built on
assumptions (voice works, the camera is readable, IWSDK slots into R3F, palm menus are fine)
fail late. These facts came from a multi-source research sweep (docs, specs, source, release
notes) on 03/10/2026. **Nothing here was device-tested**: run the checklist below on a headset
before committing to a design.

## Capability matrix
| Feature | Status | Confidence | Note |
|---|---|---|---|
| Hand input (25 joints) | Yes | High | Pinch, poke, ray, grab |
| Palm-up pinch | **System-reserved** | High | **Left palm pinch exits WebXR.** Never use for app menus |
| Microgestures (thumb tap, 4 swipes) | Yes | High | Hand gamepad buttons 5-9 (Browser 38.1+); for paging, not selection |
| Plane / mesh detection | Yes | High/Moderate | Needs Space Setup; labels vary ('desk' vs 'table'), match both |
| Anchors, persistent anchors | Yes | High | ~8 persistent per site (older doc); none in private mode |
| Depth sensing (GPU) / depth hit test | Yes on Quest 3/3S | Moderate | Good for occlusion and detecting objects on a table |
| Raw camera / passthrough camera | No / unreliable | Moderate | getUserMedia may only expose a selfie camera |
| `SpeechRecognition` | No | Moderate | Use mic + hosted STT (below) |
| Microphone in session | Yes | Moderate | Permission prompt cannot show inside immersive mode |
| WebGPU inside WebXR | Behind flags | High | Judges and users cannot flip flags |
| Eye gaze | Glasses / Quest Pro only | High | Quest 3/3S fall back to rays |

## Solution: design rules that follow from it
1. **Hands**: one core gesture; hands low and relaxed; no reflex or timed challenges (fingertip
   error ~1.7 cm best case, latency up to ~220 ms); avoid overlapping hands (tracking degrades,
   design one-handed shapes); poke targets >= 22 mm with 12 mm spacing; menus as wrist buttons
   poked by the other index finger or a tray, never a palm-up pinch.
2. **Voice**: call `getUserMedia({audio:true})` on the 2D page **before** `requestSession`, resume
   the `AudioContext` on a gesture, stream PCM to a hosted STT behind your own proxy (Meta Voice
   Transcribe: `wss://api.meta.ai/v1/asr/realtime`, ~$0.18/h). Voice must stay optional.
3. **Stack**: IWSDK 1.0.x (plain three.js + elics ECS, Havok physics in a worker, UIKitML,
   gaze-and-pinch, scene understanding, depth occlusion, IWER emulator) **cannot be combined with
   React Three Fiber**: it creates its own WebGLRenderer and loop and pins `super-three` 0.181.
   @react-three/xr 6.x covers hands, planes, meshes, hit test and layers but has no persistent
   anchors and open Quest 3 plane/mesh bugs. three r186 WebGPURenderer does WebXR only via its
   WebGL2 backend.
4. **Meta VR Glasses** (spring 2027): ~58 x 54 deg perceived FOV vs Quest 3 110 x 96; keep primary
   UI central; gaze targets >= 3 deg (~5 cm at 1 m); no hover-reveal. IWER ships a Glasses device
   config (per eye 37 deg left/right, 25 up, 43 down) for desktop previews.
5. **Performance**: browser defaults to 72 Hz (raise via `updateTargetFrameRate`); post-processing
   or mid-frame render-target switches **disable fixed foveation and MSAA**; avoid point-light
   shadows (six maps) and transparent overdraw. Native budget guide: <200 draw calls, 1.5M tris;
   aim for half in the browser.
6. **Hosting for judges/testers**: a Vercel preview URL can return 401 (Deployment Protection);
   share the production URL and confirm HTTP 200 from a logged-out device.

## MR hand occluder that also casts shadows (verified in three source)
three's `WebGLShadowMap.js` (r186, lines ~520-558) renders an object into the shadow map when
`object.visible`, `castShadow`, frustum and `material.visible` pass, using a separate depth
material; `colorWrite` is never consulted. So one tracked hand mesh with
`material.colorWrite = false; material.depthWrite = true; mesh.castShadow = true` is invisible,
hides virtual content behind the real hand, and casts a real-time shadow onto a
`ShadowMaterial` receiver (e.g. a detected wall plane). Render the occluder first (`renderOrder`).

## Verification (week-1 device checklist)
1. Log `session.enabledFeatures`; wait 3 s; dump planes and mesh labels; repeat in a room with
   Space Setup cleared and fall back to depth hit test, then manual placement.
2. Save a persistent anchor, reload, doff/don, restore; note drift.
3. Probe `'webkitSpeechRecognition' in window`, `navigator.mediaDevices.enumerateDevices()`,
   `XRGPUBinding`; every action must also work by poke or ray.
4. Stress scene at 72 and 90 Hz, foveation 0.5 and 1.0, depth occlusion on and off.
5. Pinch-test palm-facing poses to confirm nothing app-critical collides with system gestures.

## Notes
- Fast-moving platform: re-check Quest Browser release notes before relying on a row above.
- Related: [[hand-tracking-rate-control-cursor-centre-hygiene]] (desktop hand-tracking control
  laws), r3f-webgpu-playwright-gpu-perf (R3F on WebGPURenderer).

## References
- https://developers.meta.com/horizon/documentation/web/webxr-hands/
- https://developers.meta.com/horizon/documentation/web/webxr-mixed-reality/
- https://developers.meta.com/horizon/documentation/web/webxr-ffr/
- https://developers.meta.com/horizon/documentation/web/webxr-perf-bp/
- https://developers.meta.com/horizon/design/hands-limitations-mitigations/
- https://developers.meta.com/horizon/design/eyes-best-practices/
- https://developers.meta.com/vr/essentials/field-of-view/
- https://github.com/facebook/immersive-web-sdk (CHANGELOG, docs/guides 06, 11, 13, 15)
- https://github.com/immersive-web/webxr-input-profiles/blob/main/packages/registry/profiles/oculus/oculus-hand.json
- https://github.com/pmndrs/xr/issues/447
- https://dev.meta.ai/docs/speech-to-text/
- https://pubmed.ncbi.nlm.nih.gov/40053653/
