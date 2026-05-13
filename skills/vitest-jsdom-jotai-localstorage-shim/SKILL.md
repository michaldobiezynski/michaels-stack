---
name: vitest-jsdom-jotai-localstorage-shim
description: |
  Fix for vitest test suites that fail with `TypeError: _a.getItem is not a function`
  during module IMPORT (before any `it()` runs), bringing down 20+ unrelated
  test files in a single cascade. Use when: (1) vitest 2.x with
  `environment: "jsdom"` (jsdom 24.x); (2) project uses jotai 2.7.x
  `atomWithStorage(...)` at module scope; (3) tests fail with `0 test`
  loaded and a stack trace pointing at `jotai/esm/vanilla/utils.mjs:362`
  inside `Module.atomWithStorage utils.mjs:409`; (4) `Object.getPrototypeOf(globalThis.localStorage).constructor.name`
  returns `"Object"` rather than `"Storage"` inside a test. The root
  cause is a known jsdom-via-vitest interaction where `window.localStorage`
  resolves to a bare `{}` instead of a real `Storage` instance, and
  any module-scoped `atomWithStorage(key, default)` crashes on import.
  Fix is an in-memory Storage polyfill in the shared vitest setup file.
author: Claude Code
version: 1.0.0
date: 2026-05-04
---

# vitest + jsdom + jotai localStorage Polyfill

## Problem

In a vitest 2.x + jsdom 24.x + jotai 2.7.x stack, `window.localStorage`
inside a test sometimes resolves to a bare `{}` (proto: `Object`)
rather than a real `Storage` instance with `getItem` / `setItem`.
Every module that calls `atomWithStorage(...)` at module scope then
crashes during the IMPORT phase with:

```
TypeError: _a.getItem is not a function
 ❯ Object.getItem node_modules/.../jotai/esm/vanilla/utils.mjs:362:73
 ❯ Module.atomWithStorage utils.mjs:409:25
 ❯ src/state/atoms.ts:117:38
```

The vitest report shows the test file as `(0 test)` with the failure
attributed to the suite import, not to any individual `it(...)`. A
single broken module cascades through every test that transitively
imports it — typical observed impact: 20-30 test files all flagged
as failed for the same root cause.

## Context / Trigger Conditions

All of these together:

1. `vitest.config.ts` (or `vite.config.ts`) sets `test.environment: "jsdom"`
2. `vitest@^2.1`, `jsdom@^24`, `jotai@^2.7` in `package.json`
3. A module under `src/` calls `atomWithStorage<T>(key, default, …)`
   at module top-level — i.e. evaluated synchronously on first import.
4. Test failures cluster around suites that transitively import that
   module. Affected files share the same stack frame:
   `jotai/esm/vanilla/utils.mjs:362` → `utils.mjs:409` → your
   atom-defining module.
5. The runtime app itself is unaffected (real browser / Tauri webview
   provides a working `Storage`).

## Diagnosis (probe before fixing)

Drop a one-shot test file like `src/state/probe.test.ts`:

```typescript
import { describe, it } from "vitest";
describe("probe", () => {
  it("localStorage availability", () => {
    const ls = (globalThis as { localStorage?: Storage }).localStorage;
    console.log("typeof:", typeof ls);
    console.log("getItem typeof:", typeof ls?.getItem);
    console.log(
      "proto:",
      Object.getPrototypeOf(ls)?.constructor?.name,
    );
  });
});
```

Run it: `npm test -- --run src/state/probe.test.ts`.

If you see:

```
typeof: object
getItem typeof: undefined
proto: Object
```

…the polyfill below applies. If `proto` is `Storage` and `getItem
typeof` is `function`, jsdom is healthy and the fix isn't needed.

## Solution

Install an in-memory `Storage` polyfill in the shared vitest setup
file (the path referenced by `setupFiles` in vitest config — usually
`src/test/setup.ts` or `tests/setup.ts`).

```typescript
// src/test/setup.ts (or wherever your vitest setupFiles points)
import "@testing-library/jest-dom/vitest";

// jsdom-via-vitest 2.x sometimes exposes `window.localStorage` as a
// bare `{}` rather than a real `Storage` instance, which makes any
// module-level `atomWithStorage` call crash on import with
// `_a.getItem is not a function` (a 20+-test cascade that takes down
// every suite transitively importing the affected module).
// Provide a deterministic in-memory polyfill so test runs don't depend
// on the underlying jsdom version's quirks.
if (
  typeof globalThis.localStorage === "undefined" ||
  typeof globalThis.localStorage.getItem !== "function"
) {
  const memory = new Map<string, string>();
  const polyfill: Storage = {
    get length() {
      return memory.size;
    },
    clear: () => memory.clear(),
    getItem: (key) => (memory.has(key) ? (memory.get(key) ?? null) : null),
    key: (index) => Array.from(memory.keys())[index] ?? null,
    removeItem: (key) => {
      memory.delete(key);
    },
    setItem: (key, value) => {
      memory.set(key, String(value));
    },
  };
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    writable: true,
    value: polyfill,
  });
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    writable: true,
    value: polyfill,
  });
}
```

The conditional guard means the polyfill is a no-op when a future
jsdom upgrade does provide a real `Storage` — you don't need to remove
the polyfill manually after upgrading.

`sessionStorage` is unaffected by this specific bug; if your project
also uses `atomWithStorage` against `sessionStorage`, mirror the same
pattern with the same conditional.

## Verification

Re-run the full vitest suite:

```sh
npm test -- --run
```

You should see all previously-failing suites move from `0 test`
imports-fail-state to actually executing their tests. On the project
where this was discovered, the result moved from
`5 failed | 49 passed (54)` / `27 failed | 1123 passed (1150)` to
`54 passed (54)` / `1196 passed (1196)`.

The probe test from the Diagnosis section will now report:

```
typeof: object
getItem typeof: function
```

(`proto` may still be `Object` rather than `Storage`, because the
polyfill is a plain object literal — that's intentional and harmless.
The only thing jotai cares about is the presence of `getItem` and
`setItem`.)

## Notes

- **Test-only**: the polyfill lives in vitest's setup file. Production
  builds never load it. Real browsers and Tauri webviews have a real
  `Storage` so production code is unaffected.
- **No state leakage between processes**: each vitest worker process
  has its own module instance, so `memory` is per-process. Test
  isolation within a process is the test author's responsibility (call
  `localStorage.clear()` in `beforeEach` if your tests pollute it).
- **`Object.defineProperty` not direct assignment**: jsdom installs
  `localStorage` as a non-writable property on `window` in some
  versions. `Object.defineProperty(... { configurable: true,
  writable: true, ... })` ensures the assignment succeeds regardless
  of the underlying descriptor.
- **Check existing skill index**: if a sibling skill like
  `mantine-notifications-vitest-cleanup` or
  `vitest-captured-callback-needs-act-wrap` is already in your
  `~/.claude/skills/`, this one is a peer — different symptom, same
  family of vitest+jsdom interactions.

## Example

A `src/state/atoms.ts` module using jotai's `atomWithStorage`:

```typescript
import { atomWithStorage } from "jotai/utils";

export const showCoordinatesAtom = atomWithStorage<boolean>(
  "show-coordinates",
  false,
);

export const storedDocumentDirAtom = atomWithStorage<string>(
  "document-dir",
  "",
  undefined,
  { getOnInit: true },
);
```

Without the polyfill, every test file that does
`import { someAtom } from "@/state/atoms"` (directly or via a
transitive React component import) crashes on import with the stack
trace above. With the polyfill, the same atoms initialise cleanly
(reading from / writing to the in-memory `Map`) and tests run
normally.

## References

- [jotai/jotai issue tracker](https://github.com/pmndrs/jotai/issues) — search for "atomWithStorage jsdom" to track upstream
- [vitest jsdom environment docs](https://vitest.dev/guide/environment.html)
- [jsdom 24 release notes](https://github.com/jsdom/jsdom/releases) — verify whether the upstream issue has been addressed in newer versions before assuming the polyfill is still needed
