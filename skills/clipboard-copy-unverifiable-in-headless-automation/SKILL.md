---
name: clipboard-copy-unverifiable-in-headless-automation
description: |
  Explains why a "Copy to clipboard" button cannot be verified through
  agent-browser (or any headless / background-window browser automation), and
  the split-verification technique to use instead. Use when: (1) you click a
  copy button via `agent-browser click @eN` and no success/error toast appears,
  (2) `pbpaste` (or the OS clipboard) stays empty after the automated click,
  (3) BOTH `document.execCommand('copy')` and `navigator.clipboard.writeText()`
  appear to do nothing — neither the resolve nor the reject callback fires,
  (4) you are about to "fix" working copy code because automation says it
  failed. Root cause is missing OS window focus, NOT a code bug. Covers the
  technique: unit-test the data/content layer (extract the formatting/CSV/JSON
  builder from the real source and assert in node) and accept that clipboard
  transport only works in a focused tab, i.e. real user usage.
author: Claude Code
version: 1.0.0
date: 2026-06-30
---

# Clipboard copy cannot be verified in headless / background-window automation

## Problem

You build a "Copy to clipboard" feature, then try to verify it end-to-end by
driving the page with `agent-browser` (or Playwright/Puppeteer in a background
window). The click "succeeds", but:

- no success or error toast appears,
- the OS clipboard stays empty (`pbpaste` returns nothing),
- it looks like the copy code is broken.

The trap is concluding the code is wrong and rewriting it. The code is fine; the
**automation environment cannot exercise the clipboard at all**.

## Context / Trigger Conditions

All of these together point at this issue:

- The copy handler runs through `agent-browser click @eN` (or any automation
  whose browser window is not the frontmost, OS-focused window).
- `agent-browser get text "#toast"` shows a stale or empty toast — the copy
  branch never called your feedback function.
- `pbpaste` (macOS) / `xclip -o` (Linux) is empty right after the click.
- The same button works perfectly when *you* click it in a normal, focused tab.

## Root cause

Clipboard writes require the document to have user focus / transient activation:

- `navigator.clipboard.writeText(text)` requires the page to be **focused**.
  In a non-focused window it rejects with `NotAllowedError: Document is not
  focused`, and in some automation contexts the returned promise simply never
  settles — so a `.then(onOk, onErr)` fires *neither* callback and your toast
  never updates.
- `document.execCommand('copy')` requires focus **and** a live selection; in a
  background window it returns `false` (or throws), copying nothing.

`agent-browser` drives a background browser window that does not hold OS focus,
so both paths are dead. This is an environment limitation, not a defect in the
page.

## Solution: split the verification

Do not try to verify the clipboard *transport* headlessly. Split it:

1. **Verify the content (headless, deterministic).** Extract the pure builder
   that produces the copied text — `toCSV()`, `toJSON()`, a formatter — from the
   *real source file* and assert on it in node. Pulling the function out of the
   actual file (rather than re-implementing it) means you test the shipped code,
   not a copy. A brace-matching `grab(name)` over the file source + `eval` is
   enough for a self-contained function.
2. **Accept the transport works only in a focused tab.** The user clicks the
   button in their own focused window, where `writeText`/`execCommand` succeed.
   State this explicitly rather than claiming the clipboard was verified.
3. **Harden the code while you are there.** Try the synchronous
   `execCommand('copy')` path first (gesture-bound, returns a boolean, gives
   immediate feedback) and fall back to the async Clipboard API, with an
   explicit "copy failed — use the file export instead" message if both are
   blocked. This guarantees the user always gets feedback even on strict
   `file://` origins, and avoids the silent-hang failure mode.

## Verification

- node assertions on the extracted content builder pass (the bytes that would be
  copied are correct, including CSV quoting/escaping).
- Manually, in a focused browser tab, the button copies and `pbpaste` shows the
  expected text. (This step is for a human/focused session, not the automation.)

## Example

```js
// test-csv.js — test the REAL toCSV() pulled from the shipped HTML
const fs = require("fs");
const src = fs.readFileSync("app.html", "utf8");
function grab(name) {                       // brace-match a function decl out of source
  const start = src.search(new RegExp("function\\s+" + name + "\\s*\\("));
  let depth = 0, started = false;
  for (let j = start; j < src.length; j++) {
    if (src[j] === "{") { depth++; started = true; }
    else if (src[j] === "}" && --depth === 0 && started) return src.slice(start, j + 1);
  }
}
let entries = [{ id: 1, seconds: 330, label: "Background noise" }];
eval([grab("pad"), grab("fmt"), grab("toCSV")].join("\n"));
console.assert(toCSV() === '#,Time,Label\n1,00:05:30,Background noise');
```

## Notes

- The same blindness applies to anything gated on focus/activation:
  `document.hasFocus()`-dependent code, paste, fullscreen requests, and some
  `<dialog>` behaviours.
- `confirm()` / `alert()` also can't be answered headlessly — `agent-browser`
  auto-dismisses them (treated as Cancel), so a click behind a `confirm()` is a
  no-op there too. That is *correct* gating, not a failure.
- If you genuinely must test clipboard transport in automation, you need a
  focused/headed browser with clipboard read/write permissions granted and the
  window brought to the foreground — usually more effort than it is worth versus
  testing the content layer.

## References

- MDN — `Clipboard.writeText()` (requires document focus / transient activation):
  https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText
- MDN — `Document.execCommand()` (deprecated; needs focus + selection):
  https://developer.mozilla.org/en-US/docs/Web/API/Document/execCommand
