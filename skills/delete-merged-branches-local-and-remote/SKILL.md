---
name: delete-merged-branches-local-and-remote
description: |
  Clean up feature branches after their PR merges — delete BOTH the local and
  the remote (origin) branch, and reliably detect branches that are already
  merged even when a SQUASH merge has hidden that fact. Use when: (1) after
  running `gh pr merge` / merging a PR on GitHub; (2) `git branch -d X` errors
  "The branch X is not fully merged" even though its PR clearly merged;
  (3) stale local/remote branches have piled up (a `git branch` wall of dead
  feature branches); (4) you need to know which branches are safe to delete but
  `git branch --merged` shows nothing because everything was squash-merged;
  (5) bulk-pruning merged branches across a repo. Covers why `-d` refuses
  squash-merged branches (and when `-D` is safe), content-based merge
  verification, `git push origin --delete`, `git fetch --prune`, and enabling
  GitHub auto-delete so it never accumulates again.
author: Claude Code
version: 1.0.0
date: 2026-06-08
---

# Delete merged branches (local AND remote), squash-merge aware

## Problem

After a PR merges, its feature branch usually lingers in two places — the
**local** ref and the **remote** (`origin`) ref. Over a busy repo these pile
up into dozens of dead branches. Two traps make the cleanup non-obvious:

1. **`git branch -d` refuses squash-merged branches.** A squash merge collapses
   the branch's commits into ONE new commit on `master` with a different SHA and
   a different patch-id. So `git branch -d feature` reports *"The branch
   'feature' is not fully merged"* and `git branch --merged master` does **not**
   list it — even though every line of its work is in `master`. Naive cleanup
   (`git branch --merged | xargs git branch -d`) silently misses all of them.

2. **Deleting the local branch leaves the remote one** (and vice-versa). You
   have to delete both, and `git fetch --prune` to drop the stale
   remote-tracking ref.

## Context / Trigger conditions

- Just merged a PR (`gh pr merge`, or "Merge" on GitHub).
- `git branch -d X` → "not fully merged", but the PR is merged.
- `git branch` lists many old `feat/*`, `fix/*` branches you suspect are dead.
- `git branch --merged master` is empty/misleading (squash-merge workflow).
- You want to bulk-prune merged branches without nuking unmerged work.

## Solution

### Best path: delete at merge time

Merge with `--delete-branch` so the **remote** branch is removed automatically:

```bash
gh pr merge <number> --squash --delete-branch
```

Then locally:

```bash
git switch master && git pull        # get the squash commit
git branch -D <branch>               # -d refuses squash-merges; -D is fine, it's merged
git fetch --prune                    # drop the stale origin/<branch> tracking ref
```

Even better, enable it once per repo so remote branches never accumulate:
GitHub → repo **Settings → General → "Automatically delete head branches"**
(or `gh api -X PATCH repos/:owner/:repo -f delete_branch_on_merge=true`).

### Cleaning up an existing pile (squash-merge safe)

**Do NOT trust `git branch --merged` or `git branch -d`** — they miss
squash-merges. Verify "is this branch's work already in master?" by CONTENT,
using any of these (strongest first):

```bash
# 1. Authoritative: GitHub knows the PR merged.
gh pr list --state merged --head <branch> --json number,mergedAt

# 2. master's squash-merge commit subjects mention the PR/issue number.
git log origin/master --oneline | grep -E "\(#?<NNN>\)"

# 3. The branch adds NO file that master lacks (a merged branch rarely does):
mb=$(git merge-base origin/master origin/<branch>)
git diff --diff-filter=A --name-only "$mb" origin/<branch> | while read f; do
  git cat-file -e origin/master:"$f" 2>/dev/null || echo "MISSING IN MASTER: $f"
done   # any "MISSING" line => genuinely-unmerged content; investigate before deleting

# 4. Corroboration: master's version of a key file is a superset (more lines /
#    contains the branch's signature strings).
git show origin/master:<file> | wc -l   # vs the branch's
```

Once confirmed merged, delete **both** refs:

```bash
git branch -D <branch>                       # local (force; safe once verified)
git push origin --delete <branch>            # remote
```

Bulk-prune everything GitHub reports as merged:

```bash
gh pr list --state merged --limit 200 --json headRefName -q '.[].headRefName' \
  | sort -u | while read b; do
      git branch -D "$b" 2>/dev/null
      git push origin --delete "$b" 2>/dev/null
    done
git fetch --prune
```

## Verification

```bash
git branch          # local ref gone
git branch -r       # origin/<branch> gone (after fetch --prune)
gh pr list --state open   # nothing dangling
```

## Example

`council-of-thinkers` (2026-06): 24 local + several remote branches, almost all
squash-merge ghosts. `git branch --merged` listed none. Verified each via
master's history (`23c0a38 ... (#100)`, `7a2b6bc ... (#181)`) and feature-file
presence, then `git branch -D` (×22) + `git push origin --delete` (×3). Result:
2 local branches (`master` + the one active feature), 1 remote (`master`).

## Notes

- **`-d` vs `-D`**: `-d` is the safe delete (refuses if not merged) but is
  *useless* for squash-merges (always refuses). Use `-D` (force) ONLY after
  confirming merged-by-content. `-D` is recoverable: it prints
  `Deleted branch X (was <sha>)`, and the reflog keeps the tip ~30–90 days
  (`git branch X <sha>` restores it). A deleted REMOTE branch's commits also
  survive inside the squash commit on `master`.
- **Deleting a remote branch is outward-facing** — confirm/authorize before
  doing it on shared repos, even though merged commits are preserved in master.
- **`gh pr merge --delete-branch` aborts the REMOTE delete if the LOCAL delete
  fails first.** It deletes local then remote; if the local branch is checked
  out (e.g. in a `git worktree`, error *"cannot delete branch X used by
  worktree at ..."*), `gh` stops and the **remote branch is left undeleted** —
  even though the merge itself succeeded. Verify with
  `git ls-remote --heads origin <branch>` and finish with
  `git push origin --delete <branch>` + `git fetch --prune`. Avoid the trap by
  merging from a normal checkout, not a worktree that holds the PR branch.
- **Never `-D` a branch with a "MISSING IN MASTER" file** from check #3 — that's
  genuinely-unmerged work; open/finish a PR for it instead.
- The whole problem disappears if `delete_branch_on_merge` is enabled and you
  pass `--delete-branch` to `gh pr merge`.

## References

- `git branch --help` (`-d`/`-D`/`--merged` semantics)
- `gh pr merge --help` (`--delete-branch`), `gh pr list --help`
- GitHub: "Managing the automatic deletion of branches"
