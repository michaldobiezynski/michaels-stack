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
  mock, (5) a navigator.clipboard writeText spy reports "expected to be called 1 times, but
  got 0 times" in a test that uses userEvent.setup(). Root cause: Node 25 ships an
  experimental GLOBAL localStorage that shadows jsdom's window.localStorage and is missing
  parts of the Storage contract; jsdom 29 removed document.execCommand entirely (older jsdom
  stubbed it to return false); and user-event v14's setup() installs its own clipboard stub
  over any mock defined before it. All three are environment/harness gaps, not code bugs.
  Fix: install an in-memory Storage double in the Vitest setup file, assign
  document.execCommand before spying on it, and install clipboard spies AFTER userEvent.setup().
author: Claude Code
version: 1.1.0
date: 2026-08-03
---

# Vitest + jsdom Web API gaps on Node 25

## Problem

Three test-environment gaps make otherwise-correct app code fail **only in tests** under
Vitest + jsdom on Node 25. The first two are version-specific; the third is a harness
interaction that has caught people out for years:

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

3. **`userEvent.setup()` replaces your clipboard mock** — user-event v14 installs its own
   stub over `navigator.clipboard`, silently discarding a spy defined before it. The
   assertion fails with zero calls even though the component copied correctly, so the
   evidence points at the component rather than the harness.

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

### 3. `userEvent.setup()` overwrites your `navigator.clipboard` mock

`@testing-library/user-event` v14's `setup()` installs its **own** clipboard stub over
`navigator.clipboard`. A spy defined before `setup()` is silently replaced, so
`expect(writeText).toHaveBeenCalled()` reports zero calls even though the component copied
correctly. Nothing errors; the assertion just fails, which sends you hunting in the component
instead of the harness.

Symptom: `AssertionError: expected "vi.fn()" to be called 1 times, but got 0 times` on a
clipboard assertion, in a test that calls `userEvent.setup()`.

Install the spy **after** `setup()`:

```ts
let writeText: ReturnType<typeof vi.fn>
beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined)
})

// user-event's setup() stubs navigator.clipboard, so the spy has to go on afterwards
// or it is silently replaced and never called.
function setupUser() {
  const user = userEvent.setup()
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
    writable: true,
  })
  return user
}
```

Use `setupUser()` in place of `userEvent.setup()` throughout. The alternative is to read back
through user-event's own stub via `await navigator.clipboard.readText()`, which exercises the
real path but makes rejection paths (testing your "copy blocked" branch) awkward to simulate.

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
