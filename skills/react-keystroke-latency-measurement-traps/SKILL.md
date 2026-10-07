---
name: react-keystroke-latency-measurement-traps
description: |
  Measure React per-keystroke / per-interaction latency honestly in a real browser, and
  recognise when your measurement is silently lying. Use when: (1) benchmarking typing lag
  in a React app that re-renders a large tree per keystroke, (2) your timings are suspiciously
  flat as list size grows, e.g. identical at 8 and 300 rows, (3) you dispatched
  `new Event('input')` or used the native value setter and awaited requestAnimationFrame to
  time a render, (4) two people disagree about whether an app has input jank and you need to
  settle it, (5) you are about to refactor state management for performance and want evidence
  first. Root cause: React batches updates from synthetically dispatched events, so
  dispatch-then-rAF times the scheduler, not the commit. Covers the correct CDP + longtask
  method, the flatness tell-tale, and dev-vs-production and machine-load confounds.
author: Claude Code
version: 1.0.0
date: 2026-08-03
---

# Measuring React keystroke latency without fooling yourself

## Problem

You suspect an app has typing lag, so you measure it. The measurement says everything is
fine. The measurement is wrong, and it is wrong in the direction that lets a real problem
ship.

The seductive approach:

```js
// WRONG: times the scheduler, not React's commit
const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
const t0 = performance.now()
setter.call(node, node.value + 'a')
node.dispatchEvent(new Event('input', { bubbles: true }))
await new Promise((r) => requestAnimationFrame(r))
const cost = performance.now() - t0
```

React does not necessarily flush a synthetically dispatched event before the next frame, and
a tight loop of them gets batched into a single render. You end up timing event dispatch plus
one frame of waiting.

## Context / Trigger Conditions

The strongest signal that your measurement is invalid:

- **Latency is flat as the tree grows.** If 8 rows and 300 rows both report the same number,
  you are not measuring reconciliation. Reconciling 300 cards cannot cost the same as 8.
- Every number lands suspiciously close to one frame (8.3ms at 120Hz, 16.7ms at 60Hz). That
  is your `requestAnimationFrame` floor, not the app.
- Removing the `await rAF` makes the number collapse to a fraction of a millisecond. That is
  batching, not speed.

Also suspect any measurement where:

- You benchmarked the **dev server**. React development builds carry extra checks and are
  typically several times slower than production. Dev jank is not shipped jank.
- The machine was **under load**. A long task recorded while a dozen agents or builds are
  saturating the CPU says more about the machine than the app.

## Solution

Drive real, trusted events through CDP and observe actual main-thread blocking.

```js
import { chromium } from '@playwright/test'

const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto('http://localhost:4173/')      // production preview, not the dev server

await page.getByTestId('some-textarea').click()

await page.evaluate(() => {
  window.__long = []
  window.__obs = new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__long.push(Math.round(e.duration))
  })
  window.__obs.observe({ entryTypes: ['longtask'] })
})

const started = Date.now()
const text = 'the keeper turns to the sea and waits'
await page.keyboard.type(text, { delay: 25 })   // real trusted keystrokes
const elapsed = Date.now() - started

const long = await page.evaluate(() => {
  window.__obs.disconnect()
  return window.__long
})

console.log(`${(elapsed / text.length).toFixed(1)}ms/char (delay 25)`, 'longtasks:', long)
```

Read it as: subtract the typing `delay` from ms/char to get the app's own per-keystroke work.
`longtask` entries are the honest measure of jank, since they record blocking over 50ms.

**Always sweep the size** that drives the render cost (8 / 40 / 120 / 300 rows). A method that
cannot show growth cannot show a regression either. Seed sizes by writing straight into
`localStorage` and reloading, rather than clicking a button hundreds of times.

For attribution once you have confirmed a cost, take a CDP CPU profile and look at self time
in `updateProperties`, `commitHostUpdate`, `updateOptions` and `updateInput`.

## Verification

Your method is trustworthy when it can show a difference it *should* show:

- Latency rises measurably between 8 rows and 300 rows.
- Emptying the expensive list drops the number.
- Reverting a genuine optimisation makes the number worse.

If none of these move your number, fix the harness before believing any result from it.

## Example

Real numbers from one investigation, same app, same machine, three methods:

| Method | 8 rows | 300 rows | Verdict |
| --- | --- | --- | --- |
| Synthetic dispatch + await rAF | 8.3ms | 8.3ms | Invalid. Flat, and exactly one frame. |
| Synthetic dispatch in a tight loop, no rAF | 0.4ms | 0.4ms | Invalid. React batched all of them. |
| CDP `keyboard.type` + longtask observer | ~3ms | ~6ms | Trustworthy. Grows, no long tasks. |

The same app profiled properly showed the real cost was the render fan-out (about 78% of it
spent on off-screen panels), while the `structuredClone` everyone suspected was 0.08ms and
never appeared in the profile at all. Measuring the right thing changed the conclusion from
"rewrite state management" to "leave it alone".

## Notes

- Do not refactor an app's core on an unreproducible measurement. Reproduce first, in
  production mode, on an idle machine, at several sizes.
- When someone else reports jank you cannot reproduce, check what they measured against: dev
  server versus production build, headed versus headless, and what else was running.
- `performance.now()` around a `flushSync` is an alternative for unit-level measurement, but
  it changes React's scheduling and so does not reflect real typing.
- Absolute timings from an M-series Mac are optimistic. A mid-range laptop is roughly 3-5x
  slower, which is what moves a "fine" median towards the frame budget.
- Related trap in the same family: an e2e or perf harness that reuses an already-running
  server can measure a stale bundle entirely. See
  [[playwright-webserver-skips-build-stale-bundle]].

## References

- [MDN: PerformanceLongTaskTiming](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceLongTaskTiming) — long tasks are main-thread blocks over 50ms.
- [Playwright: keyboard.type](https://playwright.dev/docs/api/class-keyboard#keyboard-type) — dispatches real key events through CDP.
- [React: rendering and committing](https://react.dev/learn/render-and-commit)
