---
name: page-overflow-assert-scrollx-not-scrollwidth
description: |
  Correctly test "the page must not scroll sideways" in Playwright/Puppeteer.
  Use when: (1) a responsive test asserting
  document.documentElement.scrollWidth <= clientWidth fails on a layout that
  visibly does not scroll horizontally, (2) the reported overflow matches the
  width of a table/code block/chart living inside an overflow-x:auto container,
  (3) you are about to "fix" a layout by adding min-width:0 or overflow:hidden
  and the fix does nothing, (4) you need a mobile-viewport assertion that cannot
  produce a false positive. Root cause: content inside a scroll container still
  contributes to documentElement.scrollWidth in Chrome, so that value is not a
  measure of page overflow. Includes a DOM probe that names the real offender.
author: Claude Code
version: 1.0.0
date: 2026-08-12
---

# Assert page overflow with scrollX, not scrollWidth

## Problem

The obvious responsive assertion

```ts
const overflow = await page.evaluate(() => {
  const d = document.documentElement;
  return d.scrollWidth - d.clientWidth;
});
expect(overflow).toBeLessThanOrEqual(1);     // ❌ false positives
```

fails on layouts that are correct. It reports overflow whenever a wide child
(table, `<pre>`, chart, carousel) sits inside an `overflow-x: auto` box, even
though that box is absorbing the width exactly as designed.

## Context / Trigger conditions

- A responsive/mobile spec fails with a number like "expected <= 1, received 228".
- `document.body.scrollWidth` equals the viewport width while
  `document.documentElement.scrollWidth` does not.
- The page, opened by hand at that width, plainly does not scroll sideways.
- The overflow figure is close to `scroller.scrollWidth - scroller.clientWidth`.

## Solution

Assert the **behaviour** instead. If the page cannot scroll horizontally, trying
to scroll it leaves `scrollX` at 0:

```ts
const scrolledX = await page.evaluate(() => {
  window.scrollTo(9999, 0);
  return window.scrollX;
});
expect(scrolledX).toBe(0);
```

This cannot be fooled by content inside a scroll container, and it is the thing
the user actually experiences.

Pair it with a positive assertion that the inner box really is doing the
scrolling, so "no page overflow" cannot be satisfied by content being clipped or
missing:

```ts
const box = await page.getByTestId("data-table").evaluate((el) => ({
  clientWidth: el.clientWidth,
  scrollWidth: el.scrollWidth,
  overflowX: getComputedStyle(el).overflowX,
}));
expect(box.overflowX).toBe("auto");
expect(box.scrollWidth).toBeGreaterThan(box.clientWidth);
```

That second assertion only holds below the breakpoint, so tag the spec and run
it in a narrow-viewport project only:

```ts
// playwright.config.ts
{ name: "chromium", use: devices["Desktop Chrome"], grepInvert: /@narrow/ },
{ name: "mobile",   use: devices["Pixel 7"],        grep: /@mobile/ },
```

## Verification

Before changing any CSS, find out whether anything genuinely escapes. This probe
reports only elements that overflow the viewport **and** have no scroll-container
ancestor:

```ts
const report = await page.evaluate(() => {
  const docW = document.documentElement.clientWidth;
  const escapes: string[] = [];
  let clipped = 0;
  document.querySelectorAll("*").forEach((el) => {
    if (el.getBoundingClientRect().right <= docW + 1) return;
    let a = el.parentElement, contained = false;
    while (a) {
      const ox = getComputedStyle(a).overflowX;
      if (ox === "auto" || ox === "hidden" || ox === "scroll") { contained = true; break; }
      a = a.parentElement;
    }
    contained ? clipped++ : escapes.push(`${el.tagName}.${el.className}`);
  });
  return { escapes, clipped };
});
```

`escapes: []` with a large `clipped` count means the layout is fine and the test
was wrong. A non-empty `escapes` array names the element to fix.

## Example

Real case: a 50-row data table with `min-width: 34rem` inside
`overflow-x: auto`, at a 412px viewport.

```
docScrollW   640     ← documentElement, the misleading number
docClientW   412
bodyScrollW  412     ← body, correct
scroller: clientWidth 379, scrollWidth 669, overflowX "auto", minWidth "0px"
escapes: []          ← nothing actually escapes; 314 nodes clipped correctly
```

The layout needed no change. The assertion did.

## Notes

- `document.body.scrollWidth` happens to be right here, but it has its own edge
  cases (absolutely positioned and fixed elements). The `scrollX` probe is the
  reliable one.
- A grid or flex **item** does still need `min-width: 0` to shrink below its
  content — that is a real fix for a real symptom. Just confirm with the probe
  above that you have that symptom before applying it.
- Do not reach for `overflow-x: hidden` on `body` or `html`: it hides the
  evidence, can break `position: sticky`, and turns a layout bug into a silent
  one.
- The same reasoning applies to Puppeteer, Cypress (`cy.window()`), and manual
  DevTools checks.

## References

- [MDN: Element.scrollWidth](https://developer.mozilla.org/en-US/docs/Web/API/Element/scrollWidth)
- [CSS Sizing: automatic minimum size of grid/flex items](https://www.w3.org/TR/css-sizing-3/#min-size-auto)
