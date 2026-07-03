---
name: nextjs-server-only-vitest-alias-stub
description: |
  Fix for vitest crashing at import time when a test imports a module
  guarded with `import "server-only"` (the Next.js npm package that
  prevents accidental client bundling of server-only code). Symptom:
  `Error: This module cannot be imported from a Client Component module.
  It should only be used from a Server Component.` thrown during vitest
  module collection, before any `it()` runs. Use when: (1) a Next.js
  server-only data fetcher (e.g. one that reads `process.env.FOO` for a
  non-NEXT_PUBLIC_ env var) has unit tests; (2) `npm test` fails at import
  but the same module works in `next build` and at runtime; (3) you want
  the `server-only` build-time guard without making the module untestable.
  Fix: alias the `server-only` package to an empty stub in vitest.config.ts.
author: Claude Code
version: 1.0.0
date: 2026-05-22
---

# Next.js `server-only` Import Breaks Vitest

## Problem

You've added `import "server-only"` to a Next.js module that should never
be bundled into the client (it reads a non-public env var, or pulls in a
heavyweight server-only dep). The Next.js build correctly enforces the
boundary. But running `npm test` (vitest) now crashes during module
collection with:

```
Error: This module cannot be imported from a Client Component module.
It should only be used from a Server Component.
```

before any `it()` block runs. The unit tests can't load the module to
exercise it.

## Context / Trigger Conditions

- Next.js project with App Router.
- A module exports a helper that's `process.env.SOMETHING`-coupled or
  server-only by intent.
- Top of the file: `import "server-only";`
- vitest + jsdom env (or any env that is neither Next.js's server-component
  build nor browser).
- vitest fails during the collection phase, not during a specific test.

The `server-only` npm package's whole job is to throw at import time
when loaded from a client bundle. Next.js's SWC plugin substitutes the
import with a no-op during server-component compilation. Vitest has
neither of those mechanisms.

## Solution

Alias `server-only` to an empty stub module in `vitest.config.ts`. The
alias only affects vitest's resolver; the real package still ships with
the build.

### 1. Create a tiny stub

`lib/__tests__/serverOnlyStub.ts`:

```ts
// Stub for the npm `server-only` module so vitest doesn't crash when
// importing modules that guard against accidental client-side imports.
// In Next.js the real module throws at import time; under vitest we
// resolve to this empty module via vitest.config.ts alias.
export {};
```

### 2. Wire the alias

`vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  // ... plugins, test config ...
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // The real `server-only` package throws at import time; in vitest we
      // need to resolve it to an empty stub so guarded modules can be
      // exercised by unit tests.
      "server-only": path.resolve(__dirname, "./lib/__tests__/serverOnlyStub.ts"),
    },
  },
});
```

### 3. Install the real package

```bash
npm install --save-dev server-only
```

(Yes, even though vitest stubs it, the real package must be in
`node_modules` so `next build` doesn't fail to resolve it.)

## Verification

1. `npm test` — module loads, tests run, no `cannot be imported from a
   Client Component` error.
2. `npm run build` — clean. `server-only` is properly resolved by Next.js.
3. Optional: deliberately add `"use client"` to a file that imports the
   server-only module and rerun `npm run build`. Expect a build failure
   with the canonical `server-only` error — confirms the guard is intact.

## Example

Real session: a `lib/synthesisFetch.ts` module that reads
`process.env.SYNTHESIS_API_BASE_URL` (intentionally non-`NEXT_PUBLIC_` so
the URL never ships to the client) needed `import "server-only"` so a
future client component that accidentally imports it would fail the
build. Vitest crashed at import time. Adding the alias + empty stub +
saving the real package as a dev dep let `npm test` keep working while
preserving the production guard.

## Notes

- **The stub must be importable.** A `.ts` file with `export {};` is the
  minimum that works in TypeScript-aware vitest.
- **`vi.mock('server-only', () => ({}))`** is an alternative for individual
  test files but you'd need to repeat it everywhere; the global alias is
  cleaner.
- **No analogous `client-only`** workaround is needed — `client-only`
  throws when imported from a server bundle, which vitest doesn't simulate
  either. If you ever hit that, the same alias-to-stub pattern applies.
- **Why not just delete `import "server-only"`?** Because losing the
  build-time guard means a future client component can silently import
  the module and ship `process.env` reads to the browser — at best
  returning `undefined` at runtime, at worst leaking secrets.
- **Vite's resolve.alias is applied before vitest's own module
  resolution**, so this works with any test file regardless of layout.

## References

- [Next.js: Preventing server-only code from being imported into the client](https://nextjs.org/docs/app/getting-started/server-and-client-components#preventing-server-only-code-from-being-imported-into-the-client)
- [Vitest resolve.alias config](https://vitest.dev/config/#alias)
- [server-only npm package source](https://www.npmjs.com/package/server-only) — three lines that throw.
