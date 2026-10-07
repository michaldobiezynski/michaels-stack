---
name: gh-pr-merge-delete-branch-fails-in-worktree
description: |
  Diagnose `gh pr merge --delete-branch` "failing" when run from inside a git
  worktree. Use when: (1) you ran `gh pr merge <n> --squash --delete-branch`
  from a `.claude/worktrees/...` (or any worktree) and it printed
  "failed to run git: fatal: '<base>' is already used by worktree at <main>";
  (2) you're unsure whether the merge actually happened; (3) the remote branch
  was NOT deleted afterwards. Root cause: the REMOTE merge SUCCEEDED; only gh's
  LOCAL post-merge step (checkout base + delete local branch) failed because the
  base branch is checked out in another worktree. Do NOT re-run the merge.
  Also: (4) merging several PRs that were each tested on their own ("merge
  all") and proving master then holds exactly the tested combination.
author: Claude Code
version: 1.1.0
date: 2026-10-01
---

# `gh pr merge --delete-branch` errors inside a git worktree

## Problem

Running `gh pr merge <n> --squash --delete-branch` from inside a git worktree
prints:

```
failed to run git: fatal: '<base>' is already used by worktree at <main-checkout>
```

This looks like the merge failed. It did not. GitHub merged the PR server-side;
only gh's *local* convenience cleanup failed: after merging, gh tries to
`git switch <base>` (e.g. master) and delete the local branch, but `<base>` is
already checked out in the main checkout, so git refuses. A side effect is that
the `--delete-branch` step is abandoned, so the REMOTE branch is usually left
undeleted too.

## Context / Trigger conditions

- The working directory is a worktree (e.g. created by `EnterWorktree` /
  `git worktree add`), and the PR's base branch (master/main) is checked out in
  the primary checkout.
- The error message contains `is already used by worktree`.
- Re-running the merge would error with "Pull request is already merged".

## Solution

1. **Do not re-run the merge.** Confirm it landed:
   ```bash
   gh pr view <n> --json state,mergedAt,mergeCommit --jq '{state,mergedAt,mergeCommit:.mergeCommit.oid}'
   # state == "MERGED" => done server-side; the squash commit is on the base branch
   ```
2. **Finish the cleanup gh skipped.** Delete the remote branch (it was likely left behind):
   ```bash
   git ls-remote --heads origin <branch>            # still there?
   git push origin --delete <branch>
   ```
3. **Remove the worktree + its local branch.** If you used `EnterWorktree`, call
   `ExitWorktree({action:"remove", discard_changes:true})` (the untracked files
   and the now-squashed commits make a plain remove refuse). Otherwise:
   ```bash
   git worktree remove --force <worktree-path>
   git branch -D <branch>   # -D, not -d: squash rewrote the SHA so -d won't see it as merged
   ```
4. **Update the primary checkout's base branch** to include the merge:
   ```bash
   cd <main-checkout>
   git fetch origin --prune
   git merge --ff-only origin/<base>
   ```

## Merging several PRs that were tested one by one (verified 01/10/2026)

Each PR was tested against the old base, never together. Test the combination GitHub will build, then
merge so that only that combination can land:

```bash
git fetch origin
git diff --name-only origin/master...origin/a | sort > a.txt   # files both touch: textual risk
git diff --name-only origin/master...origin/b | sort > b.txt; comm -12 a.txt b.txt
git worktree add --detach /tmp/combo origin/master && cd /tmp/combo
ln -s <main>/node_modules node_modules                          # lockfile unchanged
git -c user.name=x -c user.email=x@local merge -q --no-ff origin/a
git -c user.name=x -c user.email=x@local merge -q --no-ff origin/b
git rev-parse 'HEAD^{tree}' > /tmp/tested-tree                  # quote ^{tree} in zsh
npm run build && npx vitest run                                 # the project's gates
# from a folder outside every checkout, so gh touches no local branch:
gh pr ready A -R owner/repo && gh pr merge A -R owner/repo --merge \
  --match-head-commit "$(git rev-parse origin/a)" --subject "<title, short> (#A)" --body ""
# wait until `gh pr view B --json mergeable` is MERGEABLE (UNKNOWN while GitHub recomputes), then B likewise
git fetch origin && [ "$(git rev-parse 'origin/master^{tree}')" = "$(cat /tmp/tested-tree)" ] && echo same
```

- `--match-head-commit` makes GitHub refuse if the branch moved after you tested it.
- With merge commits (not squash) the server's merges give the same tree as the local ones, so the
  tree check proves the base now holds what you tested, byte for byte.
- `--body ""` leaves the merge commit's body empty (gh sends it when the flag is given). `<title> (#N)`
  can run past a 72-character subject rule; shorten the subject, not the PR title.
- Drafts must be marked ready (`gh pr ready`) before `gh pr merge` will take them.
- Remove each worktree whose `node_modules` is a symlink after `rm <wt>/node_modules` (no trailing
  slash): only the link goes, never the shared folder. Merge commits keep the branch SHAs, so `git
  branch -d` (not `-D`) works once `git merge-base --is-ancestor <branch> origin/master` holds.

## Verification

```bash
gh pr view <n> --json state --jq .state        # MERGED
git ls-remote --heads origin <branch>          # empty (remote branch gone)
git worktree list                              # only the main checkout
git -C <main-checkout> log --oneline -1        # the "(#<n>)" squash commit
```

## Notes

- This is purely a LOCAL cleanup wrinkle; the server-side merge is unaffected, so
  the merged code is never at risk (it is in the squash commit on the base branch).
- The squash-merge SHA differs from the branch tip, so `git branch -d` /
  `git branch --merged` will NOT recognise the branch as merged — confirm via
  `gh pr view` or the `(#n)` squash commit, then `git branch -D`. See the
  related `delete-merged-branches-local-and-remote` skill.
- To avoid the wrinkle entirely, run `gh pr merge` from the main checkout, or
  just accept it and do the manual cleanup above.
