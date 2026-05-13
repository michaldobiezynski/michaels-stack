---
name: tauri-v2-browser-automation-limitation
description: |
  Tauri v2 desktop apps cannot be tested via browser automation (agent-browser,
  Playwright, headless Chromium). Use when: (1) attempting to screenshot or click
  through a Tauri app with agent-browser shows a blank/black page,
  (2) document.getElementById('app') is empty despite tauri dev running,
  (3) need to visually verify Tauri UI changes but browser shows nothing,
  (4) planning automated visual testing for a Tauri v2 app.
  The Vite dev server at localhost:1420 serves the frontend, but without the
  native WebKit webview's window.__TAURI__ IPC bridge, all Tauri API calls
  fail silently and React never mounts.
author: Claude Code
version: 1.0.0
date: 2026-04-09
---

# Tauri v2 Browser Automation Limitation

## Problem
When developing a Tauri v2 app, you cannot use browser automation tools
(agent-browser, Playwright, Puppeteer, headless Chromium) to interact with
or screenshot the running application. Opening the Vite dev server URL
(e.g. localhost:1420) in any browser outside the Tauri webview results in
a blank page because the Tauri IPC runtime is missing.

## Context / Trigger Conditions
- `agent-browser open http://localhost:1420` shows a black/empty page
- `agent-browser snapshot` returns `(no interactive elements)` or just `- generic`
- `document.getElementById('app')?.innerHTML` is empty
- `tauri dev` is running and the native window works fine
- Any Tauri app using `@tauri-apps/api/*` or `@tauri-apps/plugin-*` imports

## Root Cause
Tauri v2 renders the frontend in a native WebKit webview (macOS) or WebView2
(Windows) that provides `window.__TAURI__` and `window.__TAURI_INTERNALS__`.
These objects are the IPC bridge to the Rust backend. When the same URL is
opened in a regular browser:

1. `window.__TAURI__` is `undefined`
2. Every call to `@tauri-apps/api/core` invoke() throws
3. Plugin imports (`@tauri-apps/plugin-fs`, `@tauri-apps/plugin-http`, etc.) fail
4. React's initialization crashes before mounting any components
5. The `#app` div remains empty

## Workarounds

### For visual verification during development:
1. **Ask the user to screenshot** the running Tauri window and share the image
2. **Use `tauri dev` with DevTools** - the native webview has an inspector
   (right-click > Inspect Element in dev builds)
3. **Static code analysis** - trace component logic by reading source code

### For automated testing:
1. **Unit tests** (vitest) - test component logic without rendering
2. **WebDriver/Tauri test driver** - Tauri v2 has experimental WebDriver support
   via `tauri-driver` which connects to the actual webview
3. **Storybook** - isolate components from Tauri runtime for visual testing
4. **Mock Tauri APIs** - create browser-compatible mocks of `window.__TAURI__`
   for limited browser testing (complex, fragile)

### For CI visual regression:
- Use `tauri-driver` with WebDriver protocol in CI pipelines
- Screenshot from within the Tauri webview using the test driver

## Verification
If you encounter a blank page from agent-browser, run:
```bash
agent-browser eval "typeof window.__TAURI__"
```
If it returns `"undefined"`, the Tauri runtime is not available and browser
automation will not work for this app.

## Notes
- This limitation applies to ALL Tauri v2 apps, not just this project
- Even if only one import chain touches a Tauri API, the entire React app
  fails to mount (no partial rendering)
- The Vite dev server itself works fine - the issue is purely the missing
  native runtime in non-Tauri browsers
- `tauri dev` starts both the Vite server AND the native window; the Vite
  server alone is not sufficient for the app to function
