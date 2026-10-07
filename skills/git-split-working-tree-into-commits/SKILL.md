---
name: git-split-working-tree-into-commits
description: |
  Split a working tree holding several interleaved fixes (many files, fixes sharing files) into one commit per
  fix without interactive git (no `git add -p` / `git rebase -i`, which Claude Code's shell cannot drive). Use
  when: (1) review findings or several changes were implemented together and must land as granular commits,
  (2) `git apply --cached --unidiff-zero` of a subset of `git diff -U0` hunks puts lines in the wrong place
  (tests end up spliced into other tests, "Cannot find name" errors in the staged tree), (3) a hunk mixes two
  fixes on one line and the staged tree will not compile, (4) commit subjects must be reworded on a branch
  non-interactively. Covers exact hunk staging by rebuilding files from HEAD, typechecking the index alone,
  and rewording messages with filter-branch.
author: Claude Code
version: 1.0.0
date: 2026-09-30
---

# Split a working tree into one commit per fix, non-interactively

## Problem
Several changes were made together (for example 30 review fixes across 32 files) and now need one logical
commit each. `git add -p` and `git rebase -i` are interactive. The obvious scripted route, applying chosen
`git diff -U0` hunks with `git apply --cached --unidiff-zero`, misplaces lines once earlier hunks in the same
file are skipped: with no context, git cannot find where a hunk belongs.

## Solution
1. **Number the hunks against HEAD, not the index**: `git diff -U0 --no-color HEAD`, parsed per file into hunks
   of `(old_start, old_len, new_lines)`. Recompute the numbering after every commit, and `git reset -q` before
   staging each commit's set. A listing made before a staging, or a diff against the index, points at the
   wrong hunks.
2. **Stage exactly by rebuilding files**: for each touched file, take `git show HEAD:path`, replace each chosen
   hunk's old range with its new lines, bottom-up (so earlier ranges keep their positions; for `old_len == 0`
   the insertion goes after line `old_start`), then:
   ```bash
   blob=$(git hash-object -w --stdin < rebuilt)      # or python: run('git','hash-object','-w','--stdin', input=text)
   git update-index --add --cacheinfo 100644,$blob,path
   ```
   Whole files that belong to one commit: plain `git add path`.
3. **Mixed hunks** (two fixes on one line or in one block): give the hunk to the commit where it compiles, and
   say so in that commit's body. Or stage it and then edit the staged blob (`git show :path > f`, edit, then
   `hash-object -w` and `update-index` again) to hold back the other fix's lines, which come in with their own
   commit.
4. **Typecheck the staged tree alone** before each commit:
   ```bash
   rm -rf idx && git checkout-index -a -f --prefix=idx/ && ln -s "$PWD/node_modules" idx/node_modules
   (cd idx && npx tsc --noEmit -p tsconfig.json)
   ```
   Run that commit's unit tests there too when they are fast.
5. **Reword subjects** (for example over a length limit) without `-i`: a filter that maps exact old subjects,
   then check the tree did not change, and push with a lease:
   ```bash
   before=$(git rev-parse HEAD^{tree})
   FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --msg-filter 'python3 reword.py' origin/master..HEAD
   [ "$before" = "$(git rev-parse HEAD^{tree})" ] && git push --force-with-lease origin <branch>
   git update-ref -d refs/original/refs/heads/<branch>
   ```

## Verification
Each commit's tree typechecks on its own; `git status` is clean at the end; `git diff <final> <original tip>` is
empty (or the tree hash is unchanged after rewording).

## Example
Chess Explosion, 30/09/2026 (PR #60): 34 review findings fixed in one working tree became 12 commits. The first
attempt with `--unidiff-zero` spliced the reset test's tail after a new test. A second listing taken against
the index staged wrong hunks. The HEAD-based rebuild then staged every set exactly. One hunk held both a
map-rule helper and a later legibility constant: that commit's staged blob had the constant taken out, and it
came back with its own commit. Three over-long subjects were reworded with filter-branch, and the tree hash
stayed the same.

## Notes
- Stage from a fresh listing every time, and never keep partial stagings across commits: reset, then stage.
- The same technique splits any set of changes, not only review fixes.
- Related: `zsh-colon-modifiers-and-nomatch-break-git-chains` (quoting in the chains around this).
