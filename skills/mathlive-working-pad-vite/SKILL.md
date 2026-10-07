---
name: mathlive-working-pad-vite
description: |
  Build a maths answer field and a continuous multi-line 'working' sheet with MathLive
  (<math-field>) in a Vite vanilla-JS app, and grade its LaTeX with sympy. Use when: (1) you
  need typed equation input with a symbol/template palette, (2) Enter inside a math-field
  must add a row rather than submit, (3) `inlineShortcuts` or `mathVirtualKeyboardPolicy`
  seem ignored, (4) a learner's LaTeX (\frac, \sqrt, \hat{p}, e^{-\lambda b}) must be graded
  by a Python checker. Verified on mathlive 0.110.0, 14/09/2026.
author: Claude Code
version: 1.0.0
date: 2026-09-14
---

# MathLive working pad in Vite, graded by sympy

## Findings that cost time (all verified in node_modules/mathlive/types and in Chrome)
- **Fonts under Vite**: import the package's `mathlive/fonts.css` export (sets
  `--ML__static-fonts`) and set `MathfieldElement.fontsDirectory = null`; set
  `soundsDirectory = null` too. Otherwise glyphs render in a fallback font.
- **`inlineShortcuts` replaces the whole table** and is only readable after the `mount`
  event, so spread the built-ins: `mf.inlineShortcuts = { ...mf.inlineShortcuts, xbar: '\\bar{x}' }`
  inside a `mount` listener.
- **Attributes on a `<math-field>` created from detached `innerHTML` are silently ignored**
  (e.g. `math-virtual-keyboard-policy`). Build fields with `document.createElement('math-field')`
  and set properties (`mathVirtualKeyboardPolicy = 'manual'`, `menuItems = []`).
- **One continuous multi-line sheet = a single field rooted in `\displaylines{...}`**: MathLive
  treats it as multiline and left-aligned, so rows, arrow keys and backspace-merging come for
  free. Return needs help: `executeCommand('addRowAfter')` refuses unless the caret is directly
  in a row cell (after typing a fraction it is inside the fraction), so step out with
  `executeCommand('moveAfterParent')` until the row is the parent, then add the row.
  Split the value on top-level `\\` to get the working lines.
- **Palette keys**: `mf.insert('\\frac{#@}{#?}', { focus: true })`; `#@` = the argument left
  of the caret, `#?` = a placeholder, `#0` = the selection. Use `mousedown` + `preventDefault`
  on the key so the field keeps focus; track the last focused field with `focusin`.
- **Global keyboard shortcuts** (digits selecting choices, Enter submitting) must ignore
  events whose `composedPath()` includes a `MATH-FIELD`.
- Playwright/agent-browser gotcha: pressing Return while focus is still in the ANSWER field
  submits for real; stub the answer endpoint when testing against a live server.

## Grading the LaTeX
Write a brace-aware walker, not regexes: tokens `\\cmd | \\. | { } ^ _ | number | letter`;
`\frac{a}{b}` -> `((a)/(b))`, `\sqrt[n]{a}`, `\bar{x}` -> `xbar`, `\hat{p}` -> `phat`,
`\binom{n}{k}` -> `binomial(n,k)`, Greek -> names (`lambda` -> `lam`, it is a Python keyword),
`e^{...}` -> `exp(...)` with a lookbehind that allows a digit before `e` (`2e^{-2x}`), strip
`\left \right \, \;`. Strip commas only as thousands separators (`(?<=\d),(?=\d{3}\b)`) or
`binomial(n,k)` breaks. Then hand the text to the sympy-based checker (see the
`sympy-answer-grader-leniency` skill for the parser traps: N, E, S, O, Q and lambda).

## Addendum: clicks and focus (14/09/2026)
- MathLive only focuses on pointerdown over its rendered content. Clicks on a host's padding
  or on a tall transparent field's empty area do nothing, so add a `click` listener on the
  box that calls `field.focus()` + `executeCommand('moveToMathfieldEnd')` unless
  `document.activeElement === field` already (a content click keeps MathLive's caret).
- In a headless Chrome page `document.activeElement` never leaves BODY when a math-field is
  focused, and `blur()` does not clear `hasFocus()`. Probe focus behaviour through the caret
  instead: set `mf.position = 0`, dispatch the click, expect `mf.position === mf.lastOffset`.
- Setting `mf.value = '...'` programmatically is not readable back in the same tick: a
  submit that reads the field's value immediately after sees the OLD value. Wait a tick
  (separate eval / `await` a timeout) before reading or submitting in tests.
