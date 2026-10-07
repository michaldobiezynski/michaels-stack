---
name: playwright-pointer-lock-new-headless
description: |
  Make Pointer Lock (mouse-capture) work in Playwright so E2E tests can drive
  FPS-style / flight / game web apps. Use when: (1) requestPointerLock() in a
  Playwright test throws "WrongDocumentError: The root document of this
  element is not valid for pointer lock" or document.pointerLockElement stays
  null after a click, (2) a pointer-lock app tests fine manually but not
  headlessly, (3) console-error assertions pass headless but fail with a
  favicon.ico 404 after switching channels (or vice versa), (4) an unhandled
  promise rejection from requestPointerLock surfaces as a pageerror. Covers
  channel 'chromium' vs the default headless shell, synthetic movementX under
  lock, and an idle-baseline pixel-diff pattern for asserting motion.
author: Claude Code
version: 1.0.0
date: 2026-08-24
---

# Pointer Lock in Playwright: use new-headless Chromium

## Problem

Playwright's default headless browser (the `chromium_headless_shell` build)
does not implement the Pointer Lock API. Clicking an element that calls
`requestPointerLock()` rejects with `WrongDocumentError: The root document of
this element is not valid for pointer lock`, and `document.pointerLockElement`
stays `null`, so mouse-capture apps (FPS controls, flight sims, canvas games)
cannot be driven end-to-end.

## Context / Trigger Conditions

- Exact error: `WrongDocumentError: The root document of this element is not
  valid for pointer lock.` (arrives as an unhandled rejection / pageerror)
- `await page.evaluate(() => document.pointerLockElement)` returns `null`
  right after a click that should have locked
- The same flow works in headed mode or manual Chrome

## Solution

1. Run the full Chromium binary in new headless mode; its Pointer Lock works:

   ```ts
   // playwright.config.ts
   use: { baseURL: '...', channel: 'chromium' },
   ```

   (Playwright downloads both builds; `channel: 'chromium'` selects the full
   one instead of the headless shell.)

2. Gate the test on lock actually engaging, not on the click:

   ```ts
   await page.locator('canvas').click({ position: { x: 640, y: 360 } })
   await page.waitForFunction(() => document.pointerLockElement !== null)
   ```

3. Under lock, `page.mouse.move(...)` synthesises `movementX/movementY`
   deltas, so mouse-look works. Keys via `page.keyboard.down('KeyW')`.

4. To assert "the world moved" without exposing app internals, pixel-diff
   with an idle baseline so the diff cannot pass vacuously:

   ```ts
   const clip = { x: 200, y: 200, width: 600, height: 400 } // avoid HUD/gui
   const idleA = (await page.screenshot({ clip })).toString('base64')
   const idleB = (await page.screenshot({ clip })).toString('base64')
   expect(idleA).toBe(idleB) // static scene renders identical frames
   await page.keyboard.down('KeyW')
   await page.waitForTimeout(1500)
   const after = (await page.screenshot({ clip })).toString('base64')
   expect(after).not.toBe(idleA)
   ```

## Knock-on differences when switching to channel 'chromium'

- **favicon 404**: full Chromium requests `/favicon.ico`; the headless shell
  never does. A "no console errors" assertion that passed before can start
  failing with `Failed to load resource: ... 404`. Real browsers hit this
  too, so fix the app (inline data-URI icon), not the test:
  `<link rel="icon" href="data:image/svg+xml,<svg ...>...</svg>" />`
- **Unhandled rejection**: `requestPointerLock()` returns a promise that
  rejects (headless shell always; real Chrome when it throttles re-lock
  right after an Esc). Call it as
  `element.requestPointerLock?.()?.catch(() => {})` so the failure mode is
  "stays unlocked", not a pageerror.

## Verification

After the change, `document.pointerLockElement` resolves to the locked
element, no pageerrors are recorded, and the motion pixel-diff flips from
equal to different while a movement key is held.

## Notes

- Verified with Playwright 1.62 / Chromium build 1234 (Aug 2026), Vite dev
  server, Three.js app. jsdom has no pointer lock either - unit-test lock
  gating by defining `document.pointerLockElement` with
  `Object.defineProperty` and dispatching `new Event('pointerlockchange')`,
  and set `movementX/movementY` on `MouseEvent` the same way.
- `Buffer.equals` on screenshots can hit @types/node vs TS lib generic
  mismatches (TS 7); comparing `.toString('base64')` sidesteps it.
