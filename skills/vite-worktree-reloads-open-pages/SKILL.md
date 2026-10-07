---
name: vite-worktree-reloads-open-pages
description: |
  Random mid-test Playwright failures in a Vite project while parallel agents work in git worktrees inside
  the repo. Use when: (1) e2e tests fail at random with "page.waitForFunction: TypeError: Cannot read
  properties of undefined (reading '<x>')" on a window global the app installs at start-up (the page was
  reloaded under the test), (2) the failures pass in isolation, (3) agents were started with worktree
  isolation (Claude Code puts them in .claude/worktrees/) or someone ran `git worktree add` under the repo
  root during the run, (4) Vite logs no "page reload" line. Creating a worktree inside the project root
  reloads every page the main checkout's dev server is serving; fix with server.watch.ignored.
author: Claude Code
version: 1.1.0
date: 2026-09-28
---

# Vite reloads open pages when a git worktree appears under the project root

## Problem
The main checkout's Vite dev server watches the whole project root. A git worktree created inside it (for
example `.claude/worktrees/agent-*`, a whole checkout appearing at once) makes the server reload the pages it
serves about a second later. A Playwright test polling a window global sees it vanish mid-wait and fails. It
looks random, passes when rerun, and Vite's log shows no reload.

## Context / Trigger Conditions
- An e2e suite runs from the main checkout while parallel agents create worktrees under it.
- Typical error: `TypeError: Cannot read properties of undefined (reading 'world')` inside a
  `page.waitForFunction` on `window.__app.world...`, often inside a shared helper (`openWorld`, `cameraStill`).
- Each failure is a single test; the next test loads a fresh page and passes.

## Solution
1. **Correlate times.** List the worktrees' creation times (macOS `stat -f '%SB' -t '%H:%M:%S'
   .claude/worktrees/*/`; Linux `stat -c %w`). In the Playwright webServer output, find the app's start-up
   console lines (warnings it prints on every load, forwarded as `[WebServer] hh:mm:ss [vite] (client)
   [console.warn] ...`). A reload shows as those lines appearing mid-test, about 1 s after a worktree time.
2. **Reproduce (red), then fix (green)** with a scratch spec (don't keep it: it creates real worktrees):
   ```ts
   test('a new worktree does not reload the open page', async ({ page }) => {
     let loads = 0
     page.on('load', () => loads++)
     await page.goto('/app.html')
     await page.waitForFunction(() => window.__app?.ready)
     const before = loads
     execSync('git worktree add -q --detach .claude/worktrees/zz-probe HEAD')
     try { await page.waitForTimeout(5000) } finally { execSync('git worktree remove --force .claude/worktrees/zz-probe') }
     expect(loads - before).toBe(0)
   })
   ```
3. **Fix** in `vite.config.ts`, anchoring the ignore to the config's own folder:
   ```ts
   import { fileURLToPath } from 'node:url'
   // ...
   server: { watch: { ignored: [fileURLToPath(new URL('./.claude/', import.meta.url)) + '**'] } },
   ```
   **Do not use `'**/.claude/**'`.** Chokidar matches absolute paths, so a dev server started inside a
   worktree (`.../.claude/worktrees/x/`) would match every one of its own files. It stops seeing its own
   edits and serves stale code until restarted: a long-lived server (stills, manual checks) silently goes
   stale, while fresh Playwright webServers per run hide it. The anchored path ignores only the `.claude`
   folder beside the config: the main checkout ignores the worktrees beneath it, and each worktree's server
   still watches itself.

## Verification
The scratch spec goes from 1 extra load (red) to 0 (green); a full suite run with agents starting worktrees
no longer loses tests to reloads. Also check the other direction: start the dev server inside a worktree, load
a page, append a line to a module the page imports, and expect `hmr update <path>` in the server's log (red
with the unanchored `**/.claude/**` pattern, green anchored).

## Example
Chess Explosion, 28/09/2026: two world tests in a 253-test run failed at 11:54 and 11:57 with the error
above. Worktrees had been created at 11:54:36 and 11:57:50; the app's start-up warnings appeared at :37 and
:51. The scratch spec showed 1 reload before the ignore and 0 after (PR #44). #44's `'**/.claude/**'` then
made the agents' own worktree servers ignore their own edits (spotted by an agent whose server served stale
code); anchoring the path fixed both directions (PR #52).

## Notes
- The exact Vite code path was not confirmed: no "page reload" or "changed tsconfig file detected" line was
  logged. Vite does force a full reload on tsconfig.json changes anywhere in the watched tree, and a new
  checkout adds one, so that is the likeliest path. The ignore fixes it whichever path fires.
- Also consider giving each parallel agent its own dev-server port (`E2E_PORT`) so their runs never share a
  server; this issue is about the main checkout's own server seeing their files.
- Related: `playwright-3d-canvas-click-tests` (per-port runs), `r3f-webgpu-playwright-gpu-perf` (other
  headless flakes under contention).
