---
name: turbopack-home-lockfile-memory-runaway
description: |
  Next.js (Turbopack) dev server eats all memory and crashes a laptop because it took the HOME
  directory as its workspace root. Use when: (1) `next dev` logs "Next.js inferred your workspace
  root, but it may not be correct. We detected multiple lockfiles and selected the directory of
  ~/package-lock.json as the root directory", (2) Tailwind v4 fails with "Can't resolve
  'tailwindcss' in '<the project's PARENT directory>'" even after fixing the root, (3) a dev server's
  memory jumps by gigabytes within a second, or the machine froze after starting `next dev`,
  (4) you need to run any dev server or test suite with a hard memory ceiling on macOS. Covers
  pinning `turbopack.root`, clearing the stale `.next` cache, and a process-tree memory watchdog.
author: Claude Code
version: 1.0.0
date: 2026-09-25
---

# Turbopack rooted at ~ : memory runaway

## Problem
A stray `~/package.json` + `~/package-lock.json` (here from an accidental `npm i vercel` in the home
directory) makes Next.js 16 infer `~` as the Turbopack workspace root. Turbopack then scans and
watches the home directory. On a 64 GB MacBook this reached about 200 GB and crashed the machine,
twice, with nothing else unusual running.

## Context / Trigger Conditions
- The `next dev` log warns that it "selected the directory of /Users/<you>/package-lock.json as the
  root directory" and lists the project's own lockfile under "additional lockfiles".
- After pinning the root, the log still shows `Error: Can't resolve 'tailwindcss' in '<parent of the
  project>'`, and memory jumps (measured: under 4 GB to 10 GB in one second).
- Mechanism for the Tailwind error (read in `@tailwindcss/postcss` 4.2.2): the import base is
  `dirname(resolve(result.opts.from ?? ""))`; with an empty `from`, `resolve("")` is the project
  directory, so its dirname is the PARENT. The stale `.next` cache from the ~-rooted runs kept
  feeding that state.

## Solution
1. Pin the root in `next.config.ts` (commonjs projects have `__dirname`):
   ```ts
   import path from "node:path";
   const nextConfig: NextConfig = { turbopack: { root: path.join(__dirname) } };
   ```
2. Delete the stale cache: `rm -rf .next` (gitignored, regenerated).
3. Start the server only under a memory watchdog, and read the first lines of its log before sending
   any request: no "inferred your workspace root" warning, no resolve error.
4. Tell the user about the home-directory `package.json`/lockfile; delete them only with consent.

## The watchdog (`scripts/guard.sh`)
`guard.sh LIMIT_MB MAX_SECONDS LOG -- command...` runs the command, sums the resident memory of its
whole process tree every `GUARD_INTERVAL` seconds (default 1), and kills the tree when it passes
LIMIT_MB, when `sysctl kern.memorystatus_level` (the system's free-memory percentage) falls under 40,
or after MAX_SECONDS. It prints `GUARD: stopped (<reason>), peak <n> MB`, also when killed.
- Proven: a Node process allocating 50 MB every 200 ms was killed at 522 MB with a 300 MB cap; the
  runaway dev server was killed at 9,979 MB with a 4 GB cap. It samples, so it overshoots: use
  `GUARD_INTERVAL=0.25` and a cap well below the danger line for anything that can grow fast.
- `pkill -f "<the command>"` also matches the guard's own command line, since the command is in its
  arguments. The trap still stops the tree and reports.
- Never edit `guard.sh` while a copy is running: bash reads scripts as it goes, so an in-place edit
  garbles the running instance. Edit a copy.

## Verification
After the pin and `rm -rf .next`, the log was clean ("Ready", no warning, no error), free memory
stayed at 92-93%, and the site served normally, including a proxied `/play` path driven by a headless
Chrome test that peaked at 2.1 GB.

## Notes
- RSS undercounts compressed or swapped memory on macOS; the system free-memory floor catches that.
- See also: next-turbopack-rejects-symlinked-node-modules, pgrep-f-self-match-in-agent-sessions.
