---
name: untracked-file-closed-pr-residue
description: |
  Before committing an untracked working-tree file (or acting on an audit
  recommendation to "commit this stray script"), check whether it is residue
  of a deliberately-CLOSED pull request whose branch was preserved for
  reference. Use when: (1) git status shows an untracked script/tool that
  looks finished and useful, (2) a freshly committed file fails at runtime
  with ImportError for symbols that exist nowhere on master, (3) an audit or
  cleanup pass recommends committing untracked artefacts, (4) you are about
  to "rescue" work whose provenance you have not traced. Covers the
  provenance-check recipe (git grep across remote branches, gh pr list
  --state all, reading close comments) and the failure mode of re-litigating
  a decision the operator already made with recorded evidence.
author: Claude Code
version: 1.0.0
date: 2026-06-11
---

# Untracked Files May Be Closed-PR Residue - Trace Provenance Before Committing

## Problem

An untracked file in the working tree looks like forgotten work that should
be committed. But it can be the local residue of a branch whose PR was
deliberately closed without merging - the operator evaluated the work,
recorded results, and decided AGAINST shipping it, preserving the branch for
reference. Committing the stray copy: (a) re-litigates that decision without
knowing it happened, (b) ships a fragment without its dependencies (the
file's imports may only exist on the preserved branch), and (c) duplicates
the canonical copy which also has tests and later bug-fix commits there.

## Context / Trigger Conditions

- `git status` shows an untracked, complete-looking script or module.
- A just-committed file fails with `ImportError: cannot import name 'X'`
  where X exists in no file on master.
- An audit recommends "commit these untracked artefacts" (the auditor saw
  the file but not its history - untracked files have NO local history, so
  provenance must be searched, not assumed).

## Solution

Before committing any untracked file you did not just create:

1. **Search branches for its symbols**: pick a distinctive identifier from
   the file and run
   `git grep -l "<symbol>" $(git branch -r --format='%(refname:short)')`.
   A hit on a non-master branch means the file has a canonical home.
2. **Find the PR**: `gh pr list --state all --head <branch>` (or search by
   file path). Read the body AND comments AND the close comment - a closed
   PR's close comment often records the decision and the evidence (e.g.
   benchmark results that failed a quality gate).
3. **Diff the copies**: `git diff <branch>:<path> <worktree-path>` - if
   identical, the untracked copy is pure residue; delete it (recoverable via
   `git show <branch>:<path>`). If the worktree copy is newer, the delta is
   the only thing worth discussing.
4. **Respect the decision**: if the PR was closed deliberately, do not
   resurrect fragments. If circumstances changed (e.g. a stronger model now
   exists for a failed benchmark gate), reopen the conversation referencing
   the original close evidence instead of silently re-shipping.
5. **If you already committed it**: close your PR with a comment explaining
   the provenance (broken dependency + canonical preserved copy + original
   decision), delete the branch, and update any issue you edited with the
   real, already-measured results.

## Verification

After cleanup: the runtime ImportError is moot (nothing imports the missing
symbol on master), the canonical branch still holds the full work
(`git show <branch>:<path>` succeeds), and the relevant issue records the
actual decision evidence rather than a plan to re-run it.

## Example

council-of-thinkers: `scripts/benchmark_local_extract.py` sat untracked; an
audit recommended committing it separately, and it was pushed as PR #204. It
immediately failed: it imports `_call_ollama`/`OLLAMA_URL` from
`council_mcp/llm.py`, which exist only on `feat/pluggable-extraction-backend`
- the branch of PR #192, closed 3 days earlier with recorded benchmark
results (qwen3:32b 57% merged recall vs a 70% gate; "Sonnet stays the
extraction engine. Branch preserved for reference"). The branch copy was
byte-identical AND carried a 332-line test file plus a later metric bug-fix.
PR #204 was closed with provenance, and the decision data went into the
planning issue (#55) instead of re-running an hour of benchmarks.

## Notes

- The benchmark had ALREADY been run; tracing provenance first would have
  saved the wasted PR and surfaced the decision data immediately.
- Audit agents evaluating `git status` output cannot see closed-PR history;
  treat "commit this untracked file" recommendations as hypotheses needing
  the provenance check above.
- Files matching a preserved branch byte-for-byte are safe to delete from
  the working tree; the branch is the backup.
