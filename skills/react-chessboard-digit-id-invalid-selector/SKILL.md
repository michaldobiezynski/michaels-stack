---
name: react-chessboard-digit-id-invalid-selector
description: |
  Fix for react-chessboard v5 crashing the whole page with
  "SyntaxError: Failed to execute 'querySelector' on 'Document':
  '#<id>-square-e4' is not a valid selector" when options.id starts with a
  digit. Use when: (1) a Next.js/React page with a Chessboard dies client-side
  (Next shows "This page couldn't load" / error boundary) as soon as the
  position changes or a piece animates, (2) Playwright reports elements
  missing that were present a moment earlier, (3) the board id is derived
  from data such as a year-prefixed slug ("1858-opera-game"). Root cause:
  react-chessboard interpolates options.id into document.querySelector("#id-...")
  and CSS identifiers must not begin with a digit. Fix: prefix the id with a
  letter (e.g. `board-${slug}`).
author: Claude Code
version: 1.0.0
date: 2026-07-10
---

# react-chessboard v5: options.id must not start with a digit

## Problem

`<Chessboard options={{ id: "1858-opera-game", ... }} />` renders fine at
first, then the entire page crashes to the framework error screen the moment
the board animates or re-queries its squares. Nothing in react-chessboard's
docs or types warns about this; `id` is typed as a plain `string`.

## Context / Trigger Conditions

- react-chessboard 5.x (verified on 5.10.0) with the v5 `options` prop API.
- `options.id` derived from data that can start with a digit: game slugs
  ("1858-anderssen-match-game-9"), database ids, years.
- Browser pageerror: `SyntaxError: Failed to execute 'querySelector' on
  'Document': '#1858-opera-game-square-d8' is not a valid selector.`
- Symptom in E2E: assertions pass early in the test, then "element(s) not
  found" for everything, because React unmounted the tree to the error
  boundary. In Next.js the page shows "This page couldn't load".

## Solution

Prefix the id so it starts with a letter:

```tsx
const boardOptions = {
  // Board id feeds querySelector("#{id}-...") inside react-chessboard;
  // CSS ids must not start with a digit, so prefix data-derived slugs.
  id: `board-${slug}`,
  position: fen,
  ...
};
```

## Verification

Reproduce with a Playwright probe that listens for the real exception, which
never reaches the test failure message:

```js
page.on("pageerror", (err) => console.log("PAGEERROR:", err.message));
```

After the prefix fix the pageerror disappears and the board survives
position changes and animations.

## Notes

- Second v5 gotcha (same library, found 10/07/2026): the board sizes itself
  with JS and can UNDER-REPORT its height when placed directly in a CSS grid
  cell on small viewports; sibling elements (controls under the board) then
  overflow the cell and overlap content below, intercepting pointer events.
  Playwright symptom: "element intercepts pointer events" naming an element
  from the NEXT grid item. Fix: wrap <Chessboard> in a deterministic
  `aspect-square w-full` div so the row height never depends on the
  library's measurement.

- CSS identifiers may not begin with an unescaped digit (CSS Syntax spec);
  `querySelector` throws rather than returning null.
- The crash appears during react-chessboard's animation/diff pass, so a
  static first render can look healthy; it dies on the first move.
- Any library that interpolates a caller-supplied id into a selector has the
  same failure class; suspect it whenever "is not a valid selector" names
  your data.

## References

- react-chessboard v5 types: `node_modules/react-chessboard/dist/ChessboardProvider.d.ts` (`ChessboardOptions.id`)
- CSS ident syntax: https://developer.mozilla.org/en-US/docs/Web/CSS/ident
