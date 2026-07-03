---
name: workflow-args-string-falls-back-to-defaults
description: |
  The Workflow tool's `args` must be an actual JSON object/value, NOT a
  JSON-encoded string. If passed as a string, the script's `args` is a string,
  every `args.foo` read is undefined, and ALL config silently falls back to the
  script's defaults. For a diff/review workflow the defaults are usually
  base=origin/master, head=HEAD - so when HEAD == origin/master (e.g. right after
  a merge or `git pull --ff-only`), the range is EMPTY and the workflow reviews
  nothing while still fanning out every agent (huge token waste). Use when: (1) a
  feature-review / diff workflow returns a top "SETUP: comparison range empty" or
  "branch does not exist" finding; (2) a review of repo/PR B returns findings
  about repo A or the cwd; (3) a workflow ignored the base/head/repoPath you
  passed; (4) you are about to launch a parameterised Workflow and want it to
  actually receive its params.
author: Claude Code
version: 1.0.0
date: 2026-06-09
---

# Workflow `args` passed as a string silently defaults the whole script

## Problem
You launch a parameterised workflow (e.g. feature-review with
`{base, head, prNumber, repoPath, ...}`) and it behaves as if you passed nothing:
it reviews `origin/master...HEAD` in the current repo instead of your branch, the
range is empty, and you get a single "SETUP: empty comparison range" finding after
the workflow already spent dozens of agents and ~1M+ tokens.

## Root cause
The Workflow tool delivers its `args` input to the script as the global `args`
verbatim. If you pass a JSON-ENCODED STRING (`'{"base":"...","head":"..."}'`)
instead of an actual JSON object, then inside the script `typeof args === 'string'`,
so `const a = args || {}; a.base` is `undefined`, and every
`a.base || 'origin/master'` / `a.head || 'HEAD'` / `a.repoPath || null` takes the
DEFAULT. The script runs, but on the wrong (usually empty) target. The tool's own
docs warn about exactly this: "Pass arrays/objects as actual JSON values in the
tool call, NOT as a JSON-encoded string ... a stringified list reaches the script
as one string, so args.filter/args.map throw" - the object case fails more quietly
(no throw, just silent defaults).

## Why empty range, specifically
A diff/review workflow defaults to `base=origin/master`, `head=HEAD`. After you
merge a PR and `git pull --ff-only`, local `HEAD` becomes identical to
`origin/master`, so `git diff origin/master...HEAD` is empty by construction. The
lens agents then either report a setup error or wander the cwd repo and invent
findings about unrelated code.

## Solution
1. **Pass `args` as a real JSON object** in the Workflow tool call, not a quoted
   string.
2. **If a workflow must target a repo other than the session cwd**, remember its
   `git` runs in the cwd - parameterise with `git -C <repoPath>` (via an arg) or
   the agents will diff the wrong repo.
3. **Most robust for a one-off: HARDCODE the params as `const`s in the script**
   (no `args` dependency at all), then launch with just `{scriptPath}`. Zero chance
   of a silent default.
4. **Make the script fail fast on an empty diff**: early in the run, check
   `git diff --name-only <base>...<head>` (or `git -C <repo> ...`) and
   `return {error: 'empty range'}` BEFORE fanning out lens agents, so a
   mis-pointed run costs ~1 agent, not the whole fleet.
5. **Verify the target before trusting the result**: confirm the intended
   `base...head` actually produces a non-empty diff with a quick Bash check
   *before* launching, and check the workflow's opening `log()` shows your intended
   refs/repo. If the first finding is "empty range" or names the wrong repo, stop
   and re-launch.

## Verification
- Pre-launch: `git [-C repo] diff --stat <base>...<head>` shows the expected files.
- Post-launch: the workflow's first log line / first lens agent's diff lists your
  changed files, not an empty set or the wrong repo's files.

## Notes
- Same failure mode applies to ANY parameterised workflow (migration over a file
  list, research over a question), not just reviews - stringified args => defaults
  or `.map`/`.filter` throws.
- Cost anchor: one mis-pointed feature-review burned 23 agents / ~1.3M tokens
  producing a single useless "empty range" finding before this was caught.
- Related: `cross-repo-feature-coupled-draft-prs` (the cwd-bound git constraint
  that motivates `git -C`/repoPath in the first place).
