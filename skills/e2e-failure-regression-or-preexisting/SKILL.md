---
name: e2e-failure-regression-or-preexisting
description: |
  Decide, before merging, whether e2e failures on a feature branch are regressions or flakes that were
  already there. Use when: (1) a full Playwright (or similar browser) suite on a branch ends with a few
  failures and you must say "mine or not" before merging, (2) the failing tests sit in a part of the app
  the branch should not touch, (3) failures are tolerance or timing checks (positions within 0.02, frame
  gaps) that pass on some runs, (4) playwright.config has `reuseExistingServer: true` and you want to run
  the same test on the base commit in a second checkout, (5) small batches (5 runs a side) disagree and
  seem to show a regression in a check that also flakes on the base. Covers isolated reruns, a merge-base run in a
  worktree on its own port, a static proof that the branch cannot reach the failing page (import graph from
  the HTML entry intersected with the branch's diff), a same-checkout code swap with rotated arms and
  enough runs to tell base rates apart, a decision table, and filing the flake with rates.
author: Claude Code
version: 1.2.0
date: 2026-10-01
---

# Is this e2e failure mine? Regression or pre-existing flake, before a merge

## Problem
A long suite on a branch ends with a handful of failures. Rerunning it until green hides regressions;
merging on "probably flaky" ships them. Three cheap measurements settle it: the failure alone, the failure on
the base commit, and whether the branch's changes can reach the page the test drives at all.

## Context / Trigger Conditions
- `N failed` at the end of a full run on a feature branch, before `gh pr merge`.
- Failing tests in areas the branch did not edit (the game page failing on a dev-tools branch).
- Tolerance checks (`expect(drift).toBeLessThan(0.02)`) or frame-gap checks that fail by small margins.

## Solution
1. **Rerun each failure alone**, a few times, nothing else on the GPU:
   `npx playwright test <file>:<line> --repeat-each=3 --workers=1` (or `--last-failed` right after the run).
   Passing every time alone and failing only in the full run means load (see `r3f-webgpu-playwright-gpu-perf`).
2. **Run it on the merge base** (`git merge-base origin/master HEAD`) in a second worktree
   (`git worktree add --detach ../repo-base <base>`, reuse `node_modules` if the lockfile is unchanged), on
   **its own port**. With `reuseExistingServer: true`, a dev server still up on the default port (from the other
   checkout) is silently reused and you test the branch's code while believing it is master's. Give the config an
   env override (`const PORT = Number(process.env.E2E_PORT) || 5175`) and run with `E2E_PORT=5177`. Check
   first: `lsof -nP -iTCP -sTCP:LISTEN | grep node`.
3. **Prove reachability statically**: follow relative imports from each HTML page's `<script src>` and
   intersect with `git diff --name-only <base>...HEAD`:
   `python3 ~/.claude/skills/e2e-failure-regression-or-preexisting/scripts/reach.py <repo> <base> index.html spotlight.html`.
   Include a page the branch does change as a positive control, so an empty answer means something. A grep of
   the entry's direct imports is not enough; the claim has to hold for the whole graph.
3b. **When the failure also flakes on the base, compare rates in one checkout, not two.** Runs in
   different checkouts, at different times, differ in more than the code. Swap the branch's changed files
   for the base's versions in the branch's own worktree (`git show <base>:path > path`, restored with
   `git checkout HEAD -- <files>` in a `trap ... EXIT`). Check first that nothing else on the page under
   test imports what the base versions lack. Alternate the arms and rotate their order each round
   (A B, B A, ...). Run enough to tell the rates apart: at a base rate near 25%, 5 runs a side cannot
   separate 25% from 50%; 30 a side can come close. Do not pool batches that were controlled differently
   into one significance test. A mechanism that sounds right and a 'fix' are not evidence: measure the fix
   as a third arm, and revert it when it does not move the rate (all the more when keeping it would ship
   code the full suite never ran). One-sided Fisher exact for a failures in n (branch) against b in m (base):
   `python3 -c "from math import comb; a,n,b,m=8,30,8,30; K=a+b; print(sum(comb(n,k)*comb(m,K-k) for k in range(a,min(n,K)+1))/comb(n+m,K))"`
4. **Decide**:

   | Alone on branch | On base | Branch reaches the page | Verdict |
   | --- | --- | --- | --- |
   | passes every run | (not needed) | any | load flake; note it |
   | fails sometimes | fails sometimes | no, or trivially | pre-existing flake: file it, merge |
   | fails | never, over enough runs | yes | suspect regression: do not merge |
   | fails more often | fails less often, small batches | yes | not yet decided: same-checkout swap, 30 runs per arm (3b) |
   | fails | never | no | small sample: run more on both before deciding |

5. **File the pre-existing flake** with the failure rate per commit, the measured values against the limit,
   the repro command, and what the branch touches on that page; then merge and say so in the PR body.
6. After a merge commit, prove the base now holds what was tested:
   `[ "$(git rev-parse 'origin/master^{tree}')" = "$(git rev-parse "$TIP^{tree}")" ]` (quote `^{tree}` in zsh).

## Verification
The PR body names every failure with its rates on branch and base; the reachability output is quoted; the
issue for the flake exists before the merge.

## Example
Chess Explosion, 30/09/2026, PR #60 (a dev-only world lab), full suite 346 of 348:
- `navigation.spec.ts:69` (rubble replay drifted 0.053 against 0.02): 3 of 3 alone at 0.0000, so load.
- `spotlight-return.spec.ts:89` (rubble moved 0.031): 1 of 3 alone on the branch, 1 of 5 on master `d5adeae`
  (run from a worktree at the base with `E2E_PORT=5177`), so pre-existing; filed as #64.
- `reach.py` with `index.html spotlight.html world.html lab.html`: the game and spotlight pages reached 99 and 62
  modules, of which only `src/debug/probe.ts` changed (one boolean field); the world and lab pages, the positive
  controls, reached dozens of changed files. A first direct-imports grep had said "nothing changed", which
  overstated it, and the filed issue needed correcting.

Chess Explosion, 01/10/2026, PR #71 (Lichess extension moves), full suite 346 of 348 on the tip:
- `navigation.spec.ts:69` (rubble replay 0.19 against 0.02): 2 of 5 alone on the branch, 1 of 5 on master,
  so pre-existing; filed as #72.
- `promotion.spec.ts:146` (one dropped frame as the chooser opens, the known #35): batches of five said
  2/5 against 0/5, then 4/5 against 1/5, then 1/5 against 1/5. Pooled, the comparison looked
  significant (p about 0.02). A plausible cause was found (a `useSyncExternalStore` subscribe recreated on
  every render) and 'fixed'. The same-checkout swap, 30 rotated runs per arm, settled it: branch 8/30,
  master's files 8/30, the 'fix' 11/30. No regression; the fix was reverted; #35 got the data.

## Notes
- Playwright's `--only-changed [ref]` also runs test files that import a changed file (release notes, v1.46):
  that is the test file's own graph, not the page a browser test opens, so it cannot answer this question.
- Merge from outside the worktree that holds the branch: `gh -R owner/repo pr merge N --merge ...` without
  `--delete-branch`, then switch, pull and delete by hand (see `gh-pr-merge-delete-branch-fails-in-worktree`).
- Searching a Claude Code transcript (`~/.claude/projects/.../<session>.jsonl`) for an earlier command: grep
  here is ugrep, which rejects patterns like `[^"\\]{0,160}` ("exceeds complexity limits"), and BSD
  `/usr/bin/grep` caps repetition at 255. Parse the JSONL in Python instead.
- `reach.py` does not resolve path aliases (`@/x`) until you add them to `ALIASES`, and it skips packages.
- A failure that matches a known flake is still a reason to read what the branch changed under it. On
  01/10/2026 a known load flake (navigation.spec.ts:69) led to `play()`, which the branch had turned into a
  synchronous replacement `setState` that drops queued updates (skill `react-ref-mirror-replacement-setstate`).
  The flake stayed a flake; the gap under it was real.
- Frame-timing ("without a stall") tests fail on any concurrent CPU load, including a `tsc` or `vitest` run
  in another worktree: in one run two such tests failed at exactly one dropped frame (33.3 and 33.4 ms
  against a 26.7 ms limit) while typechecks ran alongside. Give a full suite the machine to itself before counting
  its failures.

## References
- Playwright web server option `reuseExistingServer`: https://playwright.dev/docs/test-webserver
- Playwright CLI (`--repeat-each`, `--last-failed`, `--only-changed`): https://playwright.dev/docs/test-cli
- Playwright release notes (`--only-changed`, v1.46): https://playwright.dev/docs/release-notes
