---
name: agent-browser-below-fold-click-miss
description: |
  Diagnose agent-browser `click @ref` reporting "✓ Done" while the page state never
  changes. Use when: (1) a click on a snapshot ref has no effect but the same element
  responds to a programmatic el.click() via eval, (2) an instrumented click listener
  shows the event target is HTML with clientY larger than window.innerHeight,
  (3) window.scrollY is still 0 after clicking something far down the page,
  (4) clipboard verification is needed but `clipboard read` throws NotAllowedError.
  Root cause: agent-browser dispatches coordinate clicks at the element's document
  position WITHOUT auto-scrolling, so any element below the fold silently misses
  (Chrome dispatches on <html>). Fix: scrollIntoView via eval first, then click.
author: Claude Code
version: 1.0.0
date: 2026-07-21
---

# agent-browser: clicks silently miss below-fold elements

## Problem

`agent-browser click @eN` returns success, but the button's handler never runs.
Re-snapshotting shows no change. The element, its refs, and the page JS are all
correct — a programmatic `.click()` via `eval` works fine.

## Context / Trigger Conditions

- Element sits below the visible viewport (its `getBoundingClientRect().top`
  exceeds `window.innerHeight`; note headless viewports can be shorter than
  expected, e.g. 1280x577, so "below the fold" starts earlier than you think)
- Instrumentation shows a trusted click whose target is `HTML` at coordinates
  matching the element's DOCUMENT position, and `window.scrollY` is unchanged
- Clicks on in-viewport elements (top of page) work normally, which misleads
  you into blaming the page (sticky-header overlay, `scroll-behavior: smooth`)
  rather than the tool

## Solution

Scroll the target into the viewport before clicking:

```bash
agent-browser eval 'document.querySelector("SEL").scrollIntoView({block:"center"}); "ok"'
agent-browser click @eN   # coordinates are recomputed at click time — same ref now hits
```

Refs stay valid across the scroll; click coordinates are recalculated at click
time, so no re-snapshot is needed just for scrolling (re-snapshot only after DOM
changes).

## Diagnosis recipe (portable to any automation click mystery)

```js
// via agent-browser eval --stdin
window.__clicks = [];
document.addEventListener('click', e => window.__clicks.push({
  tag: e.target.tagName, x: e.clientX, y: e.clientY, trusted: e.isTrusted}), true);
```

Then click, and read `__clicks` alongside `window.scrollY`, `window.innerHeight`,
and the target's `getBoundingClientRect()`. Interpretation:

- target `HTML` + clientY > innerHeight + scrollY 0 → the tool clicked document
  coordinates without scrolling (this skill)
- target is a DIFFERENT element at sane coordinates → real overlay/z-index issue
- no event recorded at all → click intercepted before dispatch (ref stale, frame
  mismatch)

## Verifying clipboard copies when `clipboard read` is denied

`agent-browser clipboard read` can throw NotAllowedError (read permission) even
though the page's copy button works. Verify the write side instead: monkey-patch
the page's copy function to record the outcome, then use a REAL agent-browser
click (trusted, carries user activation, which `navigator.clipboard.writeText`
requires):

```js
window.copyText = async function(text){
  try { await navigator.clipboard.writeText(text); window.__copyResult = {ok:true, chars:text.length}; }
  catch(e) { window.__copyResult = {ok:false, err:String(e)}; }
};
```

A plain `eval` call of `writeText` may fail for lack of user activation — the
trusted click is the point.

## Example

A local posting-workbench page: story-toggle buttons ~3000px down returned
"✓ Done" with no effect. Two plausible-looking fixes (removing
`scroll-behavior:smooth`, adding `scroll-margin-top` for the sticky header)
changed nothing — instrumentation then showed clientY 3180 vs innerHeight 577
and scrollY 0. `scrollIntoView({block:"center"})` before the click fixed it
immediately; the same approach validated checkbox toggles and clipboard writes.

## Notes

- Test in-viewport elements first when smoke-testing a page: if those pass and
  deep elements fail, suspect this before suspecting the page.
- Do not conclude a page's handlers are broken from coordinate clicks alone;
  cross-check with `eval` `.click()` — if that works, it's a targeting issue.
