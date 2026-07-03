---
name: vitest-jsdom-node25-web-api-gaps
description: |
  Fix Vitest + jsdom tests that fail on Web APIs which the runtime provides differently
  than a real browser, on Node 25 with modern jsdom. Use when: (1) a persistence test
  throws "localStorage.clear is not a function" (or getItem/setItem behave oddly) even
  though the app works in a real browser, (2) the Vitest run prints "--localstorage-file
  was provided without a valid path", (3) vi.spyOn(document,'execCommand') throws "The
  property execCommand is not defined on the object", (4) clipboard/copy code that calls
  document.execCommand('copy') works at runtime (try/catch) but its tests explode on the
  mock. Root cause: Node 25 ships an experimental GLOBAL localStorage that shadows jsdom's
  window.localStorage and is missing parts of the Storage contract; and jsdom 29 removed
  document.execCommand entirely (older jsdom stubbed it to return false). Both are
  environment/version gaps, not code bugs. Fix: install an in-memory Storage double in the
  Vitest setup file, and assign document.execCommand before spying on it.
author: Claude Code
version: 1.0.0
date: 2026-07-01
---

# Vitest + jsdom Web API gaps on Node 25

## Problem

Two version-specific test-environment gaps make otherwise-correct app code fail **only in
tests** under Vitest + jsdom on Node 25:

1. **`localStorage` shadowing** — Node 25 exposes an experimental *global* `localStorage`
   (Web Storage) that shadows jsdom's `window.localStorage` inside the Vitest `jsdom`
   environment. It is incomplete: `localStorage.clear()` throws
   `TypeError: localStorage.clear is not a function`. Any test with
   `beforeEach(() => localStorage.clear())` fails, and persistence assertions run against
   the wrong (partial) store.

2. **`document.execCommand` removed** — jsdom 29 no longer defines `document.execCommand`
   at all (older jsdom stubbed it to return `false`). `vi.spyOn(document, 'execCommand')`
   throws `Error: The property "execCommand" is not defined on the object`. App code that
   guards `document.execCommand('copy')` in a try/catch still works at runtime; only the
   test's mock setup breaks.

## Context / Trigger Conditions

- Stack: Vite + React (or any Vitest project) with `test.environment: 'jsdom'`, Node 25.x,
  jsdom 29.x, Vitest 4.x.
- The Vitest run prints: `Warning: --localstorage-file was provided without a valid path`.
- Errors: `localStorage.clear is not a function`; `The property "execCommand" is not
  defined on the object`.
- The same code works in a real browser (verified via the dev server / agent-browser).

## Solution

### 1. Install a real in-memory `localStorage` double in the Vitest setup file

`vite.config.ts` -> `test.setupFiles: './src/test/setup.ts'`, then in that setup file:

```ts
function createStorage(): Storage {
  let store: Record<string, string> = {}
  return {
    get length() { return Object.keys(store).length },
    clear() { store = {} },
    getItem(k: string) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null },
    key(i: number) { return Object.keys(store)[i] ?? null },
    removeItem(k: string) { delete store[k] },
    setItem(k: string, v: string) { store[k] = String(v) },
  } as Storage
}

try {
  Object.defineProperty(globalThis, 'localStorage', { value: createStorage(), configurable: true, writable: true })
} catch {
  // Existing descriptor is non-configurable: graft a working impl onto it.
  const mem = createStorage()
  Object.assign(globalThis.localStorage, {
    clear: () => mem.clear(), getItem: (k: string) => mem.getItem(k), key: (i: number) => mem.key(i),
    removeItem: (k: string) => mem.removeItem(k), setItem: (k: string, v: string) => mem.setItem(k, v),
  })
}
```

Then `beforeEach(() => localStorage.clear())` works and gives per-test isolation.

### 2. Assign `document.execCommand` before mocking it

Do NOT `vi.spyOn(document, 'execCommand')` — the property does not exist. Assign it, then
delete it after:

```ts
afterEach(() => { vi.restoreAllMocks(); delete (document as { execCommand?: unknown }).execCommand })

it('copies via execCommand', () => {
  const exec = vi.fn().mockReturnValue(true)
  ;(document as { execCommand?: unknown }).execCommand = exec
  expect(copyViaExecCommand('x')).toBe(true)
  expect(exec).toHaveBeenCalledWith('copy')
})
```

To test the failure path, assign a throwing function (or leave it undefined) and assert the
app's try/catch returns `false`.

## Verification

- `npm test` (or `vitest run`) passes; the persistence `beforeEach` no longer throws.
- Add a probe if unsure which `localStorage` is live: assert `typeof localStorage.clear`
  is `'function'` after setup.
- The app itself was independently confirmed to work in a real browser (dev server), proving
  these are test-env-only issues.

## Notes

- These are **version-specific**: a future Node may stabilise/rename its Web Storage global,
  and jsdom may re-add `execCommand`. Re-check when bumping Node/jsdom major versions.
- The `localStorage` double also fixes silent wrong-store bugs, not just `clear` — the Node
  global may not round-trip the way jsdom does.
- General principle: when a test fails on a Web API but the app works in a browser, suspect
  the runtime/jsdom providing (or omitting) that API differently, and stub it in the setup
  file rather than changing app code. Related: keep DOM-touching fallbacks (execCommand,
  clipboard) wrapped in try/catch so runtime degradation is graceful even if tests must mock.

## References

- Verified empirically against Node 25.8.1, jsdom 29.1.1, Vitest 4.1.9, React 19.2 (Vite 8).
- MDN Web Storage API: https://developer.mozilla.org/en-US/docs/Web/API/Storage
- MDN `Document.execCommand` (deprecated): https://developer.mozilla.org/en-US/docs/Web/API/Document/execCommand
