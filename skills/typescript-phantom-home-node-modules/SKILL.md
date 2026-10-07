---
name: typescript-phantom-home-node-modules
description: |
  Diagnose TypeScript builds that pass locally but fail on Vercel/CI with
  TS2591 "Cannot find name 'process'. Do you need to install type
  definitions for node?" (or TS2580/TS2307 for other Node globals/types)
  when @types/node is not in package.json. Use when: (1) `tsc --noEmit`
  is green on the dev machine but the identical command fails in a clean
  environment, (2) `ls node_modules/@types` shows no `node` locally yet
  `process`/`Buffer`/`__dirname` still typecheck, (3) any works-on-my-
  machine type resolution mystery. Root cause: Node-style resolution walks
  UP past the repo - a stray node_modules in a parent directory or $HOME
  (from an accidental `npm install` there) silently supplies the types.
  Diagnose with `tsc --noEmit --listFiles`; fix by declaring the dep.
author: Claude Code
version: 1.0.0
date: 2026-08-24
---

# TypeScript passes locally, fails on CI: phantom node_modules up the tree

## Problem

`npm run build` (tsc) succeeds on the dev machine but the same command
fails on Vercel/CI with e.g.
`playwright.config.ts(10,27): error TS2591: Cannot find name 'process'.`
The package that should provide the types (`@types/node`) is not in
package.json, is not in the project's node_modules, yet local tsc is green.

## Context / Trigger Conditions

- Clean-environment build errors: TS2591/TS2580 (`process`, `Buffer`),
  or missing-module errors for packages you never installed.
- Locally, `ls node_modules/@types` does NOT list the package.
- A `node_modules` directory exists somewhere above the repo: a parent
  projects folder, or `$HOME/node_modules` from a long-forgotten
  accidental `npm install` in the home directory.

## Solution

1. Ask tsc where every type actually comes from:

   ```bash
   npx tsc --noEmit --listFiles | grep -v "^$PWD"
   ```

   Any path outside the project (e.g. `/Users/<you>/node_modules/@types/node/index.d.ts`)
   is a phantom. (Also check `--traceResolution` for single-module mysteries.)

2. Fix the project, not the machine: declare the real dependency,
   `npm i -D @types/node`, and re-run `--listFiles` to confirm it now
   resolves inside the repo.

3. Optionally clean the phantom source (`rm -rf ~/node_modules` plus any
   stray `~/package.json`) - but only with the user's consent; other
   projects may be leaning on it too, which is worth surfacing.

## Verification

`npx tsc --noEmit --listFiles | grep types/node` prints a path inside the
project's own node_modules, and the CI/Vercel build goes green.

## Example

Vite + Playwright project: `playwright.config.ts` used
`!process.env.CI`. Local tsc (TypeScript 7 tsgo) green; Vercel deploy
failed with TS2591. `--listFiles` showed
`/Users/<user>/node_modules/@types/node/index.d.ts` - $HOME, two levels
above the repo. `npm i -D @types/node` fixed the deploy.

## Notes

- A quick decisive test for "is this file even being checked": append a
  deliberate type error and run tsc - separates "not checked" from
  "checked against phantom types".
- Runtime phantoms behave the same way: `import x from 'pkg'` can work
  locally via a parent node_modules and crash in production.
- Vercel CLI footnote: `vercel deploy` appends its own `.vercel` line to
  .gitignore even when `.vercel/` is already listed - expect a dirty
  worktree after first deploy.
