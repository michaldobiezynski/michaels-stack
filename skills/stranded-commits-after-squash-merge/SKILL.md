---
name: stranded-commits-after-squash-merge
description: |
  Recover commits left stranded on a feature branch when a PR is squash-merged
  mid-flight (at an earlier commit) while you have additional, already-pushed
  commits on the same branch. Use when: (1) a user/teammate merges your PR before
  your latest commits landed, (2) `gh pr view` shows the PR MERGED but its commit
  list is missing commits you pushed, (3) master got a squash commit and your
  branch still has extra commits on top, (4) you are about to "just open a new PR
  from the same branch" to land the leftover work. Covers WHY reopening a PR from
  that branch is wrong (its merge-base predates the squash, so the three-dot PR
  diff re-includes the already-merged changes) and the fix: branch fresh from the
  updated base and cherry-pick ONLY the stranded commits. Sibling to
  delete-merged-branches-local-and-remote (cleanup); this one is recovery.
author: Claude Code
version: 1.0.0
date: 2026-06-23
---

# Recovering stranded commits after a mid-flight squash merge

## Problem

You open a PR, then keep working and push more commits to the same branch. Someone
(often the repo owner) **squash-merges the PR before your later commits arrive**.
Now:

- `master` has one squash commit containing only the commits that were in the PR
  *at merge time*.
- Your branch still carries extra commits that never made it into `master`.

Those extra commits are **stranded**: the PR is closed/merged and cannot take them.

## Context / Trigger conditions

- `gh pr view <n> --json state,commits` shows `"state":"MERGED"` but the `commits`
  array is **missing commits you know you pushed**.
- `git log <base>..HEAD` on your branch lists more commits than the merged PR did.
- `git diff <remote>/<base> HEAD` shows only the *leftover* work (good — that is
  exactly what still needs to land), but `git log` shows the branch's first commits
  are "not in master" by SHA because the squash rewrote them.

## The trap (why "just reopen a PR from this branch" is wrong)

A squash merge collapses N commits into **one new commit with a new SHA**. None of
your branch's original commit SHAs exist in `master`. So:

- A new PR's file diff is computed three-dot: `merge-base(base, head)...head`.
- The merge base of your branch and `master` is the commit **before your feature
  started** (the squash did not advance it for your branch).
- Therefore the new PR re-shows **all** your branch's changes since then —
  including the parts already merged via the squash. Confusing diff, and merging it
  re-applies already-present changes (clean no-op only if byte-identical; otherwise
  conflicts).

`git branch --merged` / `git branch -d` will **also** wrongly report the branch as
"not merged" for the same SHA-rewrite reason — do not trust them here.

## Solution

1. Update the base: `git fetch origin` so `origin/<base>` includes the squash commit.
2. Confirm what is genuinely outstanding (content, not SHA):
   `git diff --stat origin/<base> HEAD` — this should list only the stranded work.
3. Identify the stranded commit SHAs: `git log --format='%h %s' origin/<base>..HEAD`,
   then keep only the ones whose *content* is not yet in `<base>`.
4. Branch fresh off the updated base and cherry-pick **only** those commits:
   ```bash
   git switch -c feat/<leftover-name> origin/<base>
   git cherry-pick <sha1> <sha2> ...   # in original order
   ```
   They apply cleanly when the base already contains the earlier (squashed) content,
   because each stranded commit's parent tree matches what is now on the base.
5. Verify the new branch's PR will be minimal: `git diff --stat origin/<base> HEAD`
   must equal the stranded work and nothing already merged.
6. Push, open the new PR, and (after merge) verify the squash commit's `--stat`
   contains exactly the intended files: `git show --stat <new-squash-sha>`.

## Verification

- `git show --stat <new-squash-commit>` lists exactly the stranded files — no
  re-inclusion of already-merged changes.
- `git diff origin/<base> origin/<old-branch>` is **empty** once the new PR merges,
  proving the old branch is now merged *by content* — only then is it safe to
  `git branch -D` / delete it on the remote (see
  [[delete-merged-branches-local-and-remote]]).

## Example

PR #19 squash-merged at 3 commits (`6b7ff3a 9a0ed0f 08e9b9f`). Two later commits
(`09fb997`, `64fbdd3`) were stranded on the branch.

```bash
git fetch origin
git diff --stat origin/master HEAD        # only the 7 leftover files — good
git switch -c feat/wordmark-home-link origin/master
git cherry-pick 09fb997 64fbdd3           # clean: parents match master's content
git diff --stat origin/master HEAD        # identical 7 files, no duplication
git push -u origin feat/wordmark-home-link
gh pr create --base master ...
# after merge:
git show --stat <squash-sha>              # exactly the 7 files
```

## Notes

- Order matters: cherry-pick the stranded commits in their original commit order.
- If a stranded commit edits a file the squash also touched, the cherry-pick still
  applies cleanly **as long as** the stranded commit's diff is relative to content
  now present on the base (it is, since the squash captured the earlier state). A
  conflict here usually means you mis-identified which commits are truly stranded.
- Prefer the fresh-branch-and-cherry-pick route over `git rebase --onto`; it keeps
  the leftover PR scoped to exactly the unmerged commits and is easy to verify.
- Only merge the recovery PR yourself if the user explicitly authorised it;
  otherwise leave it for review.

## Related

- [[delete-merged-branches-local-and-remote]] — cleanup of merged branches and the
  squash-merge "not recognised as merged" gotcha (the diagnostic half of this same
  problem space).
