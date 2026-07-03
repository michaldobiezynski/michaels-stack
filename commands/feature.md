---
description: End-to-end autonomous feature workflow. Branch, ATDD/TDD implementation, granular commits, auto-detected E2E verification, draft PR, two-round deep agent review, then fix in-scope findings and file issues for the rest. Never merges.
argument-hint: "<feature description> [--base <branch>] [--stack [branch]] [--branch <name>] [--no-pr] [--no-e2e]"
---

# /feature: autonomous feature delivery

Deliver the feature described in `$ARGUMENTS` end to end. Operate **fully autonomously**: do not pause for
approval at any step. This is a deliberate `--no-pause` contract, and it is consistent with the global
CLAUDE.md "Skip Clarification Only When ... explicitly told just do it" carve-out. Where the spec is
ambiguous, choose the most reasonable interpretation, record it as an explicit **assumption** in the
acceptance criteria and the PR body, and proceed. **Never merge** the PR and never push to the base branch.

## Parameters

Parse these out of `$ARGUMENTS`; everything that is not a flag is the feature description.

- `--base <branch>`: branch to base the new feature branch on. Default: `master`, falling back to `main` if
  `master` does not exist. The new branch is created from an up-to-date copy of this branch.
- `--stack [branch]`: stack the new feature branch on top of an existing feature branch instead of `--base`.
  With no value, stack on the **current** branch; with a value, stack on that branch. When stacking, do NOT
  pull the base branch into it, and set the PR base to the stacked-on branch.
- `--branch <name>`: explicit name for the new feature branch. If omitted, derive `feat/<kebab-case-summary>`
  from the feature description, matching the repo's existing branch-naming convention if one is detectable.
- `--no-pr`: do not open a draft PR. The review still runs against the local diff, in-scope fixes are still
  applied, and out-of-scope findings are still filed or reported (see Phase 8). Use when you want the full
  pipeline without a PR yet.
- `--no-e2e`: skip Playwright/agent-browser verification even if the repo looks like a web UI.

## Operating rules (apply throughout)

- Follow `~/.claude/CLAUDE.md` and any repo-level CLAUDE.md/AGENTS.md exactly, except where this command
  explicitly overrides them (notably the no-pause autonomy contract above). British English, no em-dashes.
- Implementation honesty: do not claim code works unless you ran it, typechecked it, or read it carefully.
  Surface what you did NOT do (tests not run, files not read, deps not checked).
- For genuinely independent sub-problems, spawn a team of agents in parallel in a single message. Each prompt
  must be self-contained (goal, background, output shape, length cap) and contain the literal word
  **ultrathink** in its body. Synthesise their outputs; do not relay verbatim. When agents disagree, surface
  it and arbitrate with reasoning.
- Commit granularly: one logical change per commit, using the CLAUDE.md format `<type>: (<scope>) <subject>`,
  imperative, lowercase, no period, under 72 chars. Never add a Claude co-author or AI-attribution line.

---

## Phase 0: preflight and branch setup

1. Confirm the working directory is a git repo (`git rev-parse --is-inside-work-tree`). If not, stop and say so.
2. If the working tree is dirty (`git status --porcelain` non-empty), **stop** and report; do not risk
   clobbering uncommitted work. (This is a safety stop, not a clarification.)
3. **Resolve the base branch**: the `--base` value, else `master`, else `main`. Confirm it exists locally
   (`git rev-parse --verify <base>`).
4. **Resolve the remote and PR capability** (do this explicitly; do not assume `origin`):
   - Remote: prefer the base branch's upstream remote (`git rev-parse --abbrev-ref <base>@{u}`, take the part
     before `/`). Else if `git remote` lists exactly one remote, use it. Else if `origin` is listed, use it.
     Else there is **no remote**: enter **local-only mode**.
   - PR capability: run `gh auth status`. `pr_capable` is true only when gh is authenticated AND a GitHub
     remote exists. If not, force local-only behaviour (no push, no PR, no direct issue creation) and record
     it as an assumption.
5. **Resolve the review-base ref** (the ref the review/diff will compare against; it must be guaranteed to
   exist, so never hard-code an `origin/` prefix):
   - Stacked mode: the local stacked-on branch name (capture its SHA too).
   - Normal mode with a remote: `<remote>/<base>` after a successful fetch.
   - Local-only mode: the local `<base>` branch.
6. **Stack-on-base guard**: if `--stack` resolves to a branch equal to the base or the repo default branch,
   treat it as a normal base run (fetch and branch from the up-to-date base), not a stack.
7. **Resolve the feature-branch name** (`--branch` value, else derived). **Collision check**: if it already
   exists (`git rev-parse --verify <feature-branch>` succeeds), stop and report rather than letting
   `git switch -c` fail or clobber. Do not auto-suffix unless the user asked to.
8. **Create the branch**:
   - Normal mode: `git fetch <remote>` then `git switch -c <feature-branch> <review-base>`.
   - Stacked mode: `git switch -c <feature-branch> <stacked-on-branch>` (local); do not pull base in.
   - Local-only mode: `git switch -c <feature-branch> <base>` (no fetch).
9. Echo the resolved **base**, **remote** (or "none"), **pr_capable**, **review-base**, **feature branch**,
   and **mode** (normal / stacked / local-only).

## Phase 1: acceptance criteria (ATDD)

Apply the **atdd-prompt-guardian** skill to turn the feature description into precise, testable acceptance
criteria as GIVEN/WHEN/THEN scenarios, including edge cases and boundaries. Because this runs autonomously,
**self-resolve** any gaps the guardian would normally ask about, choosing the most reasonable interpretation
and recording each as an explicit assumption. Keep the acceptance criteria in the conversation and the PR body;
do not create a stray spec `.md` file (per the CLAUDE.md no-unsolicited-docs rule).

## Phase 2: parallel investigation

Spawn a team of agents in parallel (one concern each, **ultrathink** in every prompt) to investigate before
writing code. Suggested concerns, adapted to the task:

- Codebase search: relevant modules, existing patterns, call sites the change must integrate with.
- Library/API/backend behaviour: verify the real contracts the feature will depend on (no guessed signatures).
- Existing-pattern audit: how similar features are already implemented here; conventions to mirror.
- Tooling/stack detection: language(s), test runner(s), and whether the project is a **web UI**, a **Tauri**
  app, or a **pure backend/CLI/library**. This drives the Phase 4 auto-detect and the `isWebUI` flag in Phase 6.

Synthesise the findings into a short implementation approach before touching code.

## Phase 3: TDD implementation (vertical slices, granular commits)

Apply the **tdd** skill. Work in **vertical slices** (tracer bullets), one behaviour at a time:
`RED -> GREEN -> REFACTOR`. Never write all tests then all code.

- Two test streams: **acceptance tests** mapping 1:1 to the GIVEN/WHEN/THEN criteria (no implementation detail
  leakage), and **unit tests** for the implementation. Tests assert behaviour through public interfaces.
- Guard against tautological regression tests: a new guard/bug-fix test must be seen to fail (RED) before it
  passes, or it protects nothing.
- Use `data-testid` for any UI selectors; add the attribute to the component if missing.
- Commit after each green slice with a granular, correctly-formatted message.
- Run the **quality-gate** (lint/format/types) between slices and fix issues before moving on.

## Phase 4: verification (auto-detect)

Run the full test suite first. Then, unless `--no-e2e`:

- **Web UI** (Playwright config present, or a browser-served dev server): write/extend **Playwright** tests
  for the acceptance criteria, run them, then additionally verify in a real browser via the **agent-browser**
  skill (open the app, snapshot, drive the new flow, screenshot the result). Use the **verify**/**run** skills
  for launching the app.
- **Tauri app**: agent-browser cannot drive a Tauri webview reliably (see the
  `tauri-v2-browser-automation-limitation` knowledge). Verify via the project's run/verify path and
  integration tests instead; note the limitation rather than forcing browser automation.
- **Pure backend / CLI / library**: skip browser E2E with an explicit note; rely on integration tests and,
  where useful, running the CLI/binary and observing output.

State plainly what was verified and what was not.

## Phase 5: draft PR

If `pr_capable` and not `--no-pr`:

- Push the feature branch.
- **Stacked work**: before `gh pr create`, ensure the stacked-on branch exists on the remote
  (`git ls-remote --heads <remote> <stacked-on-branch>`). If it is missing, push it first. If it cannot be
  pushed, fall back to opening the PR against `<base>` and note the stack relationship in the body.
- Open a **draft** PR: `gh pr create --draft --base <pr-base>`, where `<pr-base>` is the stacked-on branch for
  stacked work, else the base branch. The body must contain: summary, the acceptance criteria, assumptions
  made, a test plan, and an explicit "verified / not verified" section. Capture the PR number.

If `--no-pr` or not `pr_capable`: skip PR creation. There is no PR number; the review in Phase 6 runs against
the local diff (`review-base`...HEAD), and Phase 8 reports out-of-scope findings instead of (or in addition to)
filing issues.

## Phase 6 + 7: two-round deep review (workflow)

First confirm the review-base ref resolves (`git rev-parse --verify <review-base>`); if not, stop and report
rather than reviewing an empty range.

Then invoke the local two-round review **workflow** via the Workflow tool:

```
Workflow({
  scriptPath: "/Users/michaldobiezynski/.claude/workflows/feature-review.js",
  args: {
    base: "<review-base from Phase 0>",   // e.g. origin/master (normal), the local stacked-on branch (stack), or local base (local-only)
    head: "HEAD",
    prNumber: <pr-number-or-null>,
    featureContext: "<the feature description + key assumptions>",
    acText: "<the GIVEN/WHEN/THEN acceptance criteria>",
    isWebUI: <true|false from Phase 2 detection>
  }
})
```

**Async contract (important):** the Workflow tool runs in the background. It returns a **task id immediately**
and notifies you when the run **completes**. Treat the task-id acknowledgement as "started", NOT as the result.
**Do not advance to Phase 8** until the workflow's structured result object has actually been delivered. When
the completion notification arrives, read the returned
`{ confirmed, inScope, outOfScope, unverified, dismissed, counts }`.

This runs your exact Round-1 deep-research review prompt across parallel lenses (correctness, integration with
the rest of the repo and its backend, security, tests/ATDD, conventions/CLAUDE.md, performance, plus
accessibility/UX for web UIs), dedupes findings, then runs your exact Round-2 verify-the-findings prompt as an
adversarial pass on every finding, with one retry for agents that error.

## Phase 8: act on the review

Guard first: if the workflow result object is missing or the workflow errored, **stop and report**; do not
proceed as if there were no findings.

- **In-scope findings** (`inScope`): fix each on this branch using the same TDD discipline (failing test first
  where it applies), commit granularly, and push so any open PR updates.
- **Out-of-scope findings** (`outOfScope`): if `pr_capable`, create tracked **GitHub issues** using the
  **to-issues** skill (vertical-slice tickets with title, evidence, suggested fix, and a reference to this
  PR/branch). In autonomous mode, create them directly with appropriate labels rather than quizzing first.
  If NOT `pr_capable` (local-only or unauthenticated gh), do not silently drop them: list every out-of-scope
  finding verbatim (title, evidence, suggested fix) in the final report.
- **Unverified findings** (`unverified`): these had a verifier error, not a dismissal. Do NOT drop them.
  Verify each yourself by reading the cited file, then route to in-scope fix or out-of-scope issue; if you
  still cannot judge it, list it prominently in the final report.
- **Dismissed findings** (`dismissed`): note them briefly so the reasoning is visible.

## Phase 9: finalise

Re-run the quality gate and the full test suite. If a PR exists, update its body with a review summary
(confirmed/in-scope/out-of-scope/unverified/dismissed counts, fixes applied, issues filed with numbers).
Leave the PR as a **draft**; never merge.

## Final report

Output a concise summary: mode (normal/stacked/local-only), base, remote (or none), pr_capable, feature
branch, commits made, what was verified vs not, the review counts (including unverified), in-scope fixes
applied, GitHub issues created (with numbers/links) or out-of-scope findings listed inline when not
pr_capable, and the draft PR link if any. List every assumption you made along the way.
