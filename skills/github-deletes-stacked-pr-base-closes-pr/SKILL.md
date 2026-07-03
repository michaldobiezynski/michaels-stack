---
name: github-deletes-stacked-pr-base-closes-pr
description: |
  Merging the bottom PR of a stacked pair on GitHub with --delete-branch can
  CLOSE the upper (stacked) PR instead of retargeting it to the default branch,
  and a PR whose base branch was deleted CANNOT be reopened or retargeted. Use
  when: (1) you merged PR A (base master) and PR B was stacked on A's branch,
  (2) after the merge PR B shows state CLOSED and/or "CONFLICTING/DIRTY" with
  its base still pointing at the now-deleted branch, (3) `gh pr reopen` fails
  with "Could not open the pull request" and `gh pr edit --base master` fails
  with "Cannot change the base branch of a closed pull request", (4) you're
  about to merge stacked PRs bottom-up. The fix is to verify there is no real
  git conflict, then create a REPLACEMENT PR from the same head branch to
  master. Pairs with merge-stacked-prs-bottom-up-no-squash.
author: Claude Code
version: 1.0.0
date: 2026-06-20
---

# GitHub closes a stacked PR when its base branch is deleted on merge

## Problem

You have two stacked PRs:
- **PR A**: `feat/a` -> `master`
- **PR B**: `feat/b` -> `feat/a` (stacked; `feat/b` contains all of `feat/a`'s commits plus more)

You merge **PR A** bottom-up with `gh pr merge A --merge --delete-branch`. You
expect GitHub to **retarget PR B to master** (its usual behaviour). Instead,
**PR B is auto-CLOSED**, its base still shows the now-deleted `feat/a`, and it
reads `CONFLICTING / DIRTY`. Worse, you cannot recover it in place:

```
gh pr reopen B   -> GraphQL: Could not open the pull request. (reopenPullRequest)
gh pr edit B --base master
                 -> GraphQL: Cannot change the base branch of a closed pull request.
```

So PR B is stuck closed, and its work is not in master.

## Context / Trigger conditions

- Merging the lower PR of a stacked pair with `--delete-branch`.
- After the merge: upper PR `state=CLOSED`, base = the deleted branch,
  mergeStateStatus `DIRTY` / mergeable `CONFLICTING`.
- `gh pr reopen` and `gh pr edit --base` both error as above.
- (GitHub normally retargets an open PR when its base is deleted, but when the
  base is consumed by a merge of a stacked PR, it can close the dependent PR
  instead. The auto-retarget is not guaranteed for stacked PRs.)

## Solution

The `CONFLICTING` flag is usually a **GitHub artifact of the deleted base**, not
a real git conflict, because a `--merge` (merge commit, not squash) preserves
the lower branch's commit SHAs, so master already contains them.

1. **Verify there is no real conflict** before doing anything destructive:
   ```sh
   git fetch origin --prune
   # empty output (no CONFLICT lines) == clean merge:
   git merge-tree --write-tree origin/master origin/feat/b | grep -i conflict
   # sanity: the commits feat/b adds over master should be only the upper-PR work
   git log --oneline origin/master..origin/feat/b
   ```
2. **Create a replacement PR** from the same head branch to master (the closed
   PR keeps its review history; reference it):
   ```sh
   gh pr create --base master --head feat/b \
     --title "... [replaces #B]" --body "Replacement for #B (auto-closed when its
   stacked base branch was deleted on merge). Identical content; #B has the review."
   ```
3. **Merge the replacement**:
   ```sh
   gh pr merge <new#> --merge --delete-branch
   git checkout master && git pull --ff-only && git fetch --prune
   ```

## Verification

- `gh pr view <new#> --json state` -> `MERGED`; the closed PR stays `CLOSED`.
- `git log --oneline master` shows the merge commit and the upper-PR commits.
- Full test suite green on the merged master (don't assume from branch runs).

## Notes

- **Prevention:** merge stacked PRs bottom-up, and after merging the lower one,
  immediately retarget the upper PR to master **before** the base branch is
  deleted: `gh pr edit B --base master`, *then* delete the lower branch. Or
  merge the lower PR **without** `--delete-branch`, retarget B, then delete.
- Use `--merge` (merge commit), not `--squash`, for stacked pairs: squash
  rewrites SHAs/patch-ids so the upper PR re-shows the lower PR's changes and
  branch-merged detection breaks (see merge-stacked-prs-bottom-up-no-squash).
- `gh pr merge --delete-branch` run from a local clone deletes the **local**
  head branch too and switches you to the default branch; untracked working-tree
  files follow across the switch (they are branch-independent).
- The replacement-PR trail is cosmetic (an extra PR number); the merged content
  and history are identical.

## References

- gh pr merge / reopen / edit: https://cli.github.com/manual/gh_pr
- GitHub docs, deleting branches with open PRs (retarget behaviour): https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-branches#working-with-branches
