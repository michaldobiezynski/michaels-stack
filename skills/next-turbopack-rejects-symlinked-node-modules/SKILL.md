---
name: next-turbopack-rejects-symlinked-node-modules
description: |
  Fix for a Next.js (Turbopack) build failing in a git worktree (or any checkout)
  when node_modules is a symlink pointing outside the project root. Use when:
  (1) you created a `git worktree` and symlinked node_modules from the main checkout
  to avoid reinstalling, then `next build`/`next dev` fails; (2) the error is
  `TurbopackInternalError: Symlink [project]/node_modules is invalid, it points out
  of the filesystem root` (often wrapped in "find_package failed" / "resolve failed"
  frames); (3) more generally, any tool change where node_modules is a symlink to a
  sibling/parent directory. Root cause: Turbopack confines module resolution to the
  project root and refuses to follow a node_modules symlink whose target lives outside
  that root. The classic "symlink node_modules across worktrees" trick does NOT work
  with Turbopack.
author: Claude Code
version: 1.0.0
date: 2026-06-22
---

# Next.js / Turbopack rejects a symlinked node_modules in a worktree

## Problem

A common way to work on a repo in an isolated `git worktree` without a slow
`npm install` is to symlink the main checkout's `node_modules` into the worktree:

```bash
git worktree add /tmp/feature-wt -b feat/x master
ln -s /path/to/main/node_modules /tmp/feature-wt/node_modules
cd /tmp/feature-wt && npm run build
```

With **Next.js on Turbopack** (the default builder in Next 15/16) this fails:

```
Error [TurbopackInternalError]: Symlink [project]/node_modules is invalid,
it points out of the filesystem root
  ... Execution of find_package failed
  ... Execution of resolve failed
```

The build never starts; every dependency fails to resolve.

## Root cause

Turbopack scopes module resolution to the project root (the worktree directory).
A `node_modules` symlink whose **target is outside that root** (e.g. the main
checkout's `node_modules`, a sibling or parent path) is rejected on purpose, so the
resolver cannot follow it. Webpack historically followed such symlinks; Turbopack
does not. The trick that works fine for Vite/Webpack/Jest silently breaks here.

## Trigger conditions

- A Next.js app built/served from a `git worktree` (or any copy) where you symlinked
  `node_modules` to another location to skip installing.
- Error text contains `Symlink [project]/node_modules is invalid, it points out of
  the filesystem root`.
- `next dev`, `next build`, or `next start` all affected (resolution happens up front).

## Solution

Pick one:

1. **Install real deps in the worktree** (most robust). Use a package manager with a
   shared/global store so it is fast:
   - `pnpm install --frozen-lockfile` (content-addressable store, near-instant if the
     store is warm), or
   - `npm ci` (slower but correct).
   A real `node_modules` directory inside the worktree resolves fine.

2. **Don't build in the worktree at all** — verify against the **main checkout** which
   already has working deps. Copy the changed files into main, build/serve/verify, then
   restore main (`git checkout -- <files>` / remove new files). Good for quick checks
   (e.g. confirming a favicon or static asset is emitted) without installing.

3. If you must keep a symlink, a **copied** `node_modules` (real directory, not a
   symlink) inside the worktree also works, but that defeats the speed goal — prefer
   pnpm.

Note: disabling Turbopack is not a reliable escape on Next 16 (build is Turbopack by
default); don't rely on the Webpack symlink behaviour.

## Verification

After a real install (or verifying in main), `next build` completes and the dev/prod
server resolves modules normally. For asset-only changes (icons, public files) you can
confirm by serving the build and curling the routes, e.g.:

```bash
curl -s -o /dev/null -w '%{http_code} %{content_type}' localhost:3000/icon.svg
```

## Notes

- This is specific to Turbopack's root-confinement; the same symlink works for many
  other toolchains, which is why it is surprising.
- `git worktree remove --force` is needed to clean up a worktree that has untracked
  build output (`.next/`) left in it.
- Next 16 file-based icons (`app/icon.svg`, `app/favicon.ico`, `app/apple-icon.png`)
  are emitted automatically as `<link rel="icon|apple-touch-icon">`; no metadata code
  needed — handy context if the worktree work was favicon-related.
