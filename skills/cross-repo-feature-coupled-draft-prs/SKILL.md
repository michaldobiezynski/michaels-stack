---
name: cross-repo-feature-coupled-draft-prs
description: |
  Deliver a single user-facing feature that spans TWO repos (e.g. a Next.js
  frontend + a Python backend) when your feature tool (/feature) is single-repo
  and the session is rooted in only one of them. Use when: (1) a request like
  "add a download button AND a generated summary to the frontend" actually needs
  a backend field plus frontend rendering; (2) /feature would only branch/PR the
  cwd repo; (3) you want each side independently reviewable and mergeable. Covers
  the optional-field contract that lets each PR stand alone, per-repo agent
  isolation, and the "new data only" caveat after both merge.
author: Claude Code
version: 1.0.0
date: 2026-06-09
---

# Cross-repo feature: two coupled draft PRs via per-repo agents

## Problem
A feature the user describes as one thing ("download button + a summary on the
synthesis page") actually crosses a repo boundary: the frontend renders it, but
the data (a generated summary) must come from the backend. /feature (and most
single-repo flows) branch + PR only the current working directory's repo, and the
session is usually rooted in just one of the two repos. Trying to make one PR span
both repos produces a broken commit graph (the other repo's files never land in
its git history).

## Context / Trigger conditions
- Two separate git repos (frontend + backend) for one product.
- A feature whose UI lives in repo A but whose data/logic needs repo B.
- You were asked to "use /feature" but it is single-repo and rooted in one of them.

## Solution
1. **Fix an explicit contract FIRST, and make the consumer's side OPTIONAL.** Define
   the wire field both sides agree on, e.g. `Payload.summary?: string`. Optional is
   the key: the frontend renders it only when present and degrades to nothing when
   absent, so the frontend PR is correct and mergeable BEFORE the backend ships.
2. **Split into two coupled draft PRs, one per repo.** Each follows the full
   feature methodology (ATDD -> TDD -> granular commits -> draft PR). Tell the user
   it is two PRs precisely because the tool is single-repo; this is expected, not a
   shortcut.
3. **Run one agent per repo, isolated, concurrently.** They touch different
   directories so there is no working-tree conflict.
   - The agent for the SESSION repo: use worktree isolation (the Agent tool's
     `isolation: "worktree"` makes a worktree of the SESSION repo) so it does not
     disturb the cwd's untracked files / running processes.
   - The agent for the OTHER repo: worktree isolation does NOT help (it would
     worktree the session repo). Run it directly in that repo's directory via
     absolute paths; ensure that repo's tree is clean enough to branch first.
4. **Each side tests independently against the contract.** Frontend: add the
   optional field to its types + FIXTURE (so the demo/fixture path renders it) and
   unit-test render-present / absent-when-missing (mutation-test the absence guard so
   it is not vacuous). Backend: thread the field through generation -> store
   (migration with a NOT NULL DEFAULT '' column, guarded ALTER TABLE for legacy DBs)
   -> served payload; mock all external calls.
5. **Prefer folding generation into an EXISTING paid call.** If the backend already
   makes one LLM call to produce the main output, extend that call's output shape to
   also return the summary (object `{summary, blocks}` with a fallback to the legacy
   bare-array parse) instead of adding a second paid call.

## Verification
- Both PRs: draft, base default branch, never merged; each repo's own gate green
  (vitest / pytest), with pre-existing environmental failures proven identical on a
  clean base checkout.
- Frontend verified live against its fixture (the field shows) even though the
  backend is not wired yet.

## The caveat to tell the user
After BOTH merge, the feature is fully live only for NEW data. Existing stored
records were written before the backend produced the field, so they serve it empty
and the optional UI stays hidden for them — re-generate to backfill. The
frontend-only part (here, the download button) works the moment its PR merges,
independent of the backend.

## Notes
- Clean up the session-repo agent's worktree afterwards (`git worktree remove
  --force <path>`); the branch persists on the remote for its PR.
- Related: the worktree-isolation pattern is the same one used to run a feature
  agent alongside a long-running process in the same repo without file conflicts.
