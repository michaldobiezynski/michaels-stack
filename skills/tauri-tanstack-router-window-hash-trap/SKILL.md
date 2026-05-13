---
name: tauri-tanstack-router-window-hash-trap
description: |
  Diagnose silent UI fallback when spawning a Tauri `WebviewWindow` at a hash
  URL (e.g. `/#/some-route?params`) and the target route never renders.
  Use when: (1) a newly-spawned Tauri window shows the default `/` route
  component (often the app's home or default layout) instead of the requested
  route, (2) no console error or routing warning is thrown, (3) the project
  uses `@tanstack/react-router` with `createRouter({ routeTree })` and no
  explicit `history` option. Classic symptom: a correctly-sized, correctly-
  positioned child window that silently renders the home page. Fix: drop the
  `#/` from the URL, or configure `createHashHistory()` globally.
author: Claude Code
version: 1.0.0
date: 2026-04-22
---

# Tauri + TanStack Router: Hash URL Silent Fallback

## Problem
A second `WebviewWindow` opened with a URL like `/#/mini-live-analysis?foo=bar`
does not route to `/mini-live-analysis`. The window loads the root `/` route
instead, silently. No error, no warning, no log. The target component's render,
effects, and loaders never run, so none of its usual diagnostic signals fire.

## Trigger Conditions (all must hold)
- App is a Tauri 2 desktop app using `@tanstack/react-router`.
- Router is built with `createRouter({ routeTree })` and no `history` option
  (defaults to `createBrowserHistory()`).
- Code spawns a child window with a fragment-prefixed URL, e.g.
  `new WebviewWindow("label", { url: "/#/target?x=1" })`.
- The child window is the right size and focused, but shows the `/` route
  component (often the main app shell or home page), not the target.

## Root Cause
`createBrowserHistory()` reads `window.location.pathname`. For
`/#/mini-live-analysis?foo=bar`, the pathname is `/`. The router happily
matches `/`, renders the root route, and never inspects the fragment. There
is no `404` hook, no "route not found" warning, no exception; the wrong
route is simply a successful match. Developers coming from HashRouter-era
SPA habits tend to reach for `/#/path` by reflex, which makes this trap
especially easy to hit.

## Fix

**Per-call (preferred for isolated cases):** drop the `#/`.
```ts
new WebviewWindow("label", { url: "/mini-live-analysis?foo=bar" });
```

**Global (if the app legitimately needs hash routing, e.g. `file://`
loads):** configure the router once.
```ts
import { createHashHistory, createRouter } from "@tanstack/react-router";

const router = createRouter({
  routeTree,
  history: createHashHistory(),
});
```
Do not mix the two.

## Verification
- Open devtools inside the new window (Tauri spawns separate devtools per
  window) and check `window.location.pathname`. With the fix it is the
  target path; before the fix it is `/`.
- Add a one-line `console.log` inside the target route's component to
  confirm it mounts.

## Notes
- The same trap catches `router.navigate({ to: "/#/..." })`, Tauri deeplink
  arguments, and any ad-hoc URL construction.
- Before reaching for multi-window at all, ask whether the feature could
  resize the main window in place and hide chrome via a state flag. That
  avoids the routing question entirely, removes cross-window event
  coordination, and is much easier to test.
- If you keep multi-window: the target route must exist in
  `routeTree.gen.ts` AND the new window label must appear in the relevant
  capability JSON (`src-tauri/capabilities/*.json`) if you use
  capability-scoped permissions.

## References
- TanStack Router history types: https://tanstack.com/router/latest/docs/framework/react/guide/history-types
- Tauri `WebviewWindow` API: https://tauri.app/v2/api/js/webview-window/
