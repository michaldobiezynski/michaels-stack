---
name: merge-stacked-prs-bottom-up-no-squash
description: |
  Safely merge a stack of dependent GitHub PRs (PR-B based on PR-A's branch,
  not master) without auto-closing children or creating phantom conflicts. Use
  when: (1) merging two or more PRs where one PR's base is another feature
  branch (a "stack"); (2) `gh pr merge <base> --squash --delete-branch` closed
  the child PR instead of retargeting it; (3) after squash-merging the base, the
  child PR shows CONFLICTING/DIRTY against master even though it was CLEAN
  before; (4) `gh pr reopen` fails with "Could not open the pull request" and
  `gh pr edit --base` fails with "Cannot change the base branch of a closed
  pull request". Covers the two traps (branch-deletion closes children;
  squash-divergence conflicts) and the recovery (rebase --onto, or a fresh PR).
author: Claude Code
version: 1.0.0
date: 2026-06-06
---

# Merge stacked PRs bottom-up (and don't squash the base)

## Problem
A PR stack is `master <- PR-A (branch a) <- PR-B (base: branch a)`. Merging it
naively breaks in two ways:
1. **Deleting the base branch closes the child.** `gh pr merge A --delete-branch`
   deletes branch `a`. PR-B's base was `a`, so GitHub CLOSES PR-B (a PR whose
   base branch is deleted is closed, not always retargeted). It then cannot be
   reopened (base gone) or retargeted (`Cannot change the base branch of a
   closed pull request`).
2. **Squash-merging the base makes the child conflict.** Squash collapses A's
   commits into one new commit on master. The child branch still carries A's
   ORIGINAL commits, so a 3-way merge re-applies A's changes on top of a master
   that already has them -> add/add and content CONFLICTs.

## Context / Trigger Conditions
- Two+ open PRs where `gh pr view <n> --json baseRefName` shows a feature branch
  (not master/main) as the base.
- A child PR flips to CONFLICTING right after the base PR merges.
- Recovery commands error with the "closed pull request" messages above.

## Solution
**Merge bottom-up, one at a time, and prefer MERGE COMMITS for the base PR.**

1. Order PRs so each base merges before its child. `gh pr merge A --merge`
   (merge commit, NOT squash, and do NOT `--delete-branch` yet). A merge commit
   keeps A's commit SHAs in master, so the child's merge-base stays correct.
2. Retarget the child to master: `gh pr edit B --base master`. With a merge
   commit it is now CLEAN (A's commits are in master by identity). Merge B.
3. Only after the whole stack is merged, delete the leftover branches
   (`gh api -X DELETE repos/<owner>/<repo>/git/refs/heads/<branch>`).
4. Mark drafts ready first: `gh pr ready <n>` (a draft refuses to merge with
   "Pull Request is still a draft").

If you already squashed the base and the child is now closed/conflicting:
- The child's HEAD branch still exists. Rebase ONLY the child's own commits onto
  master, dropping the base commits already squashed in:
  `git worktree add --detach /tmp/fix origin/<child-branch>`
  `cd /tmp/fix && git rebase --onto origin/master <base-PR-tip-sha> HEAD`
  (get `<base-PR-tip-sha>` from `gh pr view <basePR> --json commits` — the newest
  commit), then `git push --force origin HEAD:<child-branch>`.
- The original child PR is dead (closed, base deleted); open a FRESH PR from the
  rebased branch to master.

## Verification
- Between merges, re-query the child: `gh pr view <n> --json mergeable,mergeStateStatus`
  should read MERGEABLE/CLEAN after retarget (allow a few seconds; UNKNOWN means
  GitHub is still recomputing).
- After all merges: `gh pr list --state open` is empty; `gh api repos/.../commits/master --jq '.commit.message'` shows the last PR.

## Example
```bash
# stack: master <- #176 (a) <- #179 (base a);  independent: #181 (base master)
gh pr ready 176; gh pr merge 176 --merge        # merge commit, keep branch
gh pr edit 179 --base master                    # retarget child
gh pr ready 179; gh pr merge 179 --merge        # now CLEAN
gh pr ready 181; gh pr merge 181 --squash       # independent PR, any method
# cleanup last:
gh api -X DELETE repos/o/r/git/refs/heads/feat/a
```

## Notes
- Squash is fine for the TOP of a stack and for independent PRs; the danger is
  squashing a base that has children still pointing at it.
- `--delete-branch` is safe only for a PR nothing else targets. During a stack
  merge, defer all branch deletion to the end.
- Worktree (`git worktree add`) lets you rebase the child without disturbing an
  unrelated working checkout (e.g. another feature in progress).
