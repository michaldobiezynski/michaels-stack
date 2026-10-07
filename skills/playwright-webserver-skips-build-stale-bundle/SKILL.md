---
name: playwright-webserver-skips-build-stale-bundle
description: |
  Playwright e2e suites that silently pass against a stale build. Use when: (1) a
  playwright.config.ts has `webServer.command` containing a build step, e.g.
  `npm run build && npm run preview`, (2) `reuseExistingServer: !process.env.CI` is set and
  the project has no CI, (3) e2e tests pass but you cannot explain why a source change had
  no effect, (4) you edited a component and the e2e suite's assertions did not budge,
  (5) you want to prove an e2e suite can actually detect a source change. Root cause:
  Playwright probes the URL BEFORE running webServer.command, so any process already
  listening on the port makes it skip the entire command, build included, and the suite runs
  against whatever dist/ happens to be on disk. Includes a canary technique for proving a
  suite is not blind.
author: Claude Code
version: 1.0.0
date: 2026-08-03
---

# Playwright webServer can skip your build and test a stale bundle

## Problem

A `playwright.config.ts` that looks completely reasonable:

```ts
webServer: {
  command: 'npm run build && npm run preview -- --port 4173',
  url: 'http://localhost:4173',
  reuseExistingServer: !process.env.CI,
},
```

If anything is already listening on port 4173, Playwright **skips the whole command**. Not
just the `preview` half: the `build` half too. The suite then runs against whatever is
already in `dist/`, which may be minutes or commits old. Every test passes, and the passes
mean nothing.

This is worse than a flaky test, because it fails *open*: you get green ticks and a false
sense that the change is verified.

## Context / Trigger Conditions

All of these together:

- `webServer.command` bundles a build (or any other prerequisite) with the server start.
- `reuseExistingServer` is truthy. The common idiom `!process.env.CI` is truthy on every
  local run in a repo with no CI, so this is the default state, not an edge case.
- Something is on the port. Sources are easy to miss:
  - a `vite preview` you started by hand to poke at the app,
  - a previous Playwright run whose server outlived it,
  - **an unrelated project's dev server**, because the availability check only looks for an
    HTTP response on that URL, not for *your* app.

Symptoms:

- Source edits have no effect on e2e results.
- A test you expect to fail passes.
- Conversely, the same suite behaves differently after a reboot or after killing a server.

## Solution

Two changes, both needed.

**1. Move the build out of `webServer` and into the script.** `webServer` should only ever
start a server.

```json
// package.json
"scripts": {
  "test:e2e": "npm run build && playwright test"
}
```

**2. Do not reuse, and do not let the port drift.**

```ts
// playwright.config.ts
webServer: {
  command: 'npm run preview -- --port 4173 --strictPort',
  url: 'http://localhost:4173',
  reuseExistingServer: false,
  timeout: 120_000,
},
```

`reuseExistingServer: false` makes Playwright throw if the port is occupied rather than
quietly testing someone else's app. `--strictPort` stops Vite drifting to 4174 and leaving
the `url` check pointing at a different process.

If you genuinely want fast local reuse, keep `reuseExistingServer: !process.env.CI` but
**only** after the build has been moved into the script. The stale-bundle class of bug comes
from the build being inside the command, not from reuse itself.

## Verification

Do not take it on trust. Run a canary: break the source and confirm the suite notices.

```bash
cp src/data/seed.ts /tmp/seed.bak
perl -0pi -e "s/title: 'Signal'/title: 'STALE BUNDLE CANARY'/" src/data/seed.ts
npm run test:e2e            # MUST fail on any test asserting the old value
cp /tmp/seed.bak src/data/seed.ts
```

Observed on a real project, before and after the fix:

| | Result |
| --- | --- |
| Before, with a server on the port | 8 passed. The mutation was invisible. |
| After the fix | Build ran, 2 tests correctly failed. |

Also confirm the build actually ran by looking for the bundler's own line in the output,
e.g. `✓ 39 modules transformed`. Its absence is the tell.

## Example

Full working config:

```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  use: { baseURL: 'http://localhost:4173', trace: 'on-first-retry' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // The build lives in the `test:e2e` script. Playwright probes the URL before running
  // this command, so a bundled build would be skipped whenever the port is occupied.
  webServer: {
    command: 'npm run preview -- --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
```

## Notes

- The mechanism is in Playwright's runner: `_startProcess()` calls the availability callback
  before it ever touches `this._options.command`, and returns early on success.
- The availability check accepts a broad range of responses as "server is up", so a totally
  unrelated service on the port satisfies it.
- The generalisation is worth remembering: **any prerequisite hidden inside
  `webServer.command` is conditional on the port being free.** Migrations, fixture seeding
  and codegen have the same exposure. Put prerequisites in the script.
- A related trap in the same family: agents or scripts that start a preview server for
  profiling and leave it running will poison subsequent e2e runs in the same session.
- If several agents or terminals share one working tree, prefer running verification in a
  clean `git clone` at the exact SHA, so probe files and stray servers cannot influence the
  result.

## References

- [Playwright: Web server](https://playwright.dev/docs/test-webserver) — documents that
  `reuseExistingServer` "will re-use an existing server on the port or url when available"
  and that with `false` it "will throw if an existing process is listening". The docs do not
  call out the consequence for a compound command, which is what makes this trap easy to hit.
- [Playwright: TestConfig.webServer](https://playwright.dev/docs/api/class-testconfig#test-config-web-server)
