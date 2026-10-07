---
name: vite-dev-only-tooling-page
description: |
  Build a dev-only tool page for a Vite app (a lab, debug bench, level/map editor) that provably never ships,
  drives the running app through hook points, and can write files back into the source. Use when: (1) a
  developer tool must be hidden from users and absent from production builds, (2) a tool must set module-level
  state before the app's modules evaluate (a draft config the app builds itself from as it loads), (3) a Vite
  dev-server endpoint must write a source file safely (DNS rebinding, cross-site POSTs, LAN exposure), (4) you
  need a test that fails if any dev hook leaks into the bundle, (5) a URL-kept scenario must survive reloads.
  Covers the separate HTML entry, import.meta.env.DEV guards, a production-build marker test (strings and
  property names survive minification), boot-module ordering, the endpoint's checks, and `in` versus
  Object.hasOwn in URL parsing.
author: Claude Code
version: 1.0.0
date: 2026-09-30
---

# A dev-only tool page for a Vite app, kept out of every build

## Solution
1. **Its own HTML entry, outside the build's inputs.** Vite's dev server serves any `lab.html` at the project
   root, but `build.rollupOptions/rolldownOptions.input` lists only the real pages, so no build carries it.
   Guard its boot anyway: `if (!import.meta.env.DEV) throw new Error('dev server only')`.
2. **Hook points in the app, behind `import.meta.env.DEV`** (and only when the tool opened the app, for example a
   `worldDev.active` flag the tool's boot sets), so the app's own page in dev behaves exactly as in production:
   - a registry module the app reads (`dev.ts`) with no side effects at module level;
   - handles registered in effects that start `if (!import.meta.env.DEV || !dev.active || !ready) return` (gate on
     the app being ready, or early clicks half-apply against unmounted parts);
   - components that wrap things only in the tool: `export const Layer = import.meta.env.DEV ? DevLayer : Pass`.
3. **A production-build test** that builds (`npx vite build --outDir tmp`, NODE_ENV=production; rolldown takes
   about 1 s) and greps every .html/.js/.css for markers:
   - string literals only the tool uses (test ids, the endpoint path, a group name like `lab-layer`);
   - **property names** only the hooks use (`layerShown`, `standAt`, `readyDraught`). Minifiers rename locals,
     never property keys, so these catch a leaked registry that has no string literals.

   Mutation-check it: take a DEV guard off, put the page in the inputs, ship the dev component, and see the
   test go red each time.
4. **State the app reads while it loads** (a draft config the app builds a module-level constant from): the
   tool's entry imports a tiny `boot.ts` first, and boot's own imports must not touch the modules that build that
   state. ES modules evaluate imports in order, depth first, so boot sets `dev.map = readDraft()` before
   `layout.ts` runs `export const WORLD = buildWorld(import.meta.env.DEV && dev.map ? dev.map : MAP)`. A
   validator that imports the layout, anywhere in boot's graph, evaluates it too early.
5. **The write endpoint** (a plugin with `apply: 'serve'` and `configureServer` middleware), refusing everything
   but the tool on this machine:
   - POST only;
   - the peer is loopback (`127.0.0.1`, `::1`, `::ffff:127.0.0.1`);
   - `Origin === http://${Host}` **and** the Host's hostname is a loopback name (`localhost`, `*.localhost`,
     `127.0.0.1`, `[::1]`). Without that last check, DNS rebinding sends a matching origin and host from
     loopback; Vite's own host check (`allowedHosts`) happens to run first today, but `allowedHosts: true` or a
     tunnel hostname removes it;
   - `Content-Type: application/json` (so a cross-site form cannot send it);
   - a size cap while reading the body; validate the payload part by part and copy only what was checked;
   - write one fixed path, temp file then rename, and only when the content differs (compare against the
     current module via `server.ssrLoadModule`, so an unchanged save leaves the file alone);
   - `handleHotUpdate` for that file: `server.ws.send({ type: 'full-reload' })` and `return []`, when the app
     builds itself from it at load.

   Keep the handler a pure function over `{method, origin, host, contentType, remoteAddress, body}` so unit tests
   can cover the cases a browser cannot send (a foreign host from loopback).
6. **A scenario in the URL** (`history.replaceState` on a timer, applied once the app is ready):
   - parse membership with `Object.hasOwn(TABLE, v)`, never `v in TABLE`: `?x=__proto__` passes `in`, and here it
     reached React as an object child and blanked the page;
   - a reset must navigate to an address without the scenario, or the reload sets it all up again;
   - restore order matters: stand things in place first, then set toggles that standing may flip.

## Verification
The build test is green, and red under each mutation. The tool's e2e suite runs on the dev server. The app's
own page shows none of the tool in dev (an e2e asserting the tool's root test id is absent).

## Example
Chess Explosion, 30/09/2026 (PR #60): the world lab at `/lab.html`. The review caught five things, all fixed:
- reset reloading the URL's scenario;
- a registry without markers;
- the Host header trusted for same-origin;
- `wonders=__proto__` crashing the page;
- buttons waking before the world was ready.

## Notes
- Put the console handle (`window.__tool = registry`) in the tool's boot, not the app's hooks: gated on ready,
  it would appear late.
- Related: `vite-worktree-reloads-open-pages` (anchoring `server.watch.ignored`),
  `playwright-webserver-skips-build-stale-bundle`.
