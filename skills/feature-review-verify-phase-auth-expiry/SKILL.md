---
name: feature-review-verify-phase-auth-expiry
description: |
  Recover a /feature or feature-review two-round review whose Round-2 adversarial
  verification (and possibly some Round-1 lenses) failed mid-run, most often because the
  auth token expired. Use when: (1) the workflow completes but counts show
  `unverified == raw` and `confirmed == 0` `dismissed == 0`, (2) the <failures> block is
  full of "Login expired · Please run /login" for verify:F* (and maybe a couple of
  review:<lens>) agents, (3) every finding carries note "verification agent failed after
  one retry; treat as needs-manual-review, do NOT silently drop", (4) the task-notification
  <result> is truncated ("... truncated N chars, full result in .../tasks/<id>.output").
  Covers: why 0-confirmed is NOT "clean", how to read the full findings, and the correct
  recovery (self-verify against source, do not re-run blindly or drop).
author: Claude Code
version: 1.0.0
date: 2026-07-20
---

# Recovering a review workflow whose verify phase died (auth expiry)

## Problem
The `/feature` pipeline (and the standalone `feature-review` workflow) runs a two-round
review: Round 1 = parallel multi-lens finders, Round 2 = one adversarial verifier per
finding. If the session's auth token expires while the workflow is running in the
background, the verify agents fail *en masse*. The workflow still completes and returns a
well-formed result object, but with **every finding in `unverified[]`** and
`confirmed/dismissed/inScope/outOfScope` all empty.

The trap: `confirmed: 0` looks like "the review found nothing actionable" or "all findings
were refuted". It is neither. The findings were never verified at all — the second opinion
simply did not run. Treating 0-confirmed as "nothing to do" silently discards a full round
of real review findings.

## Context / Trigger Conditions
All of these co-occur in the completion notification / result:

- `counts`: `unverified` equals `raw`/`deduped`; `confirmed == dismissed == 0`.
- `<failures>` lists `verify:F1..FN` (and often 1-2 `review:<lens>`) as
  `failed: Login expired · Please run /login`.
- Each `unverified[]` finding has `note: "verification agent failed after one retry;
  treat as needs-manual-review, do NOT silently drop"`.
- The `<result>` in the task-notification is truncated with a pointer to
  `.../tasks/<task-id>.output`.
- Usage often shows `agents_error` ≈ (verify count × 2 retries) + failed lenses.

Same recovery applies to any transient per-agent error that wipes the verify phase (rate
limit, terminal API error), not just auth expiry.

## Solution
1. **Re-authenticate** if needed (`/login`) so any follow-up tooling works. This does NOT
   retroactively fix the completed run.
2. **Read the FULL findings**, not the truncated notification. The workflow's
   `.../tasks/<task-id>.output` file is the STRUCTURED result JSON (safe to read), unlike
   the per-agent `agent-*.jsonl` transcripts (which overflow context — do not read those).
   It can be large; page it with Read `offset`/`limit`, or `jq '.result.unverified[]'`.
   The findings you need are `.result.unverified` (id, title, file, severity, lens,
   description, suggestedFix).
3. **Self-verify each finding against source** — you are now the missing Round 2. For each:
   open the cited file at the cited construct and decide: real+reachable, already-correct,
   out-of-scope, or non-code noise. Triage examples seen in practice:
   - Real + concrete failure → fix in-scope (TDD: add a test that goes RED first).
   - "Assumption unverified" that actually matches verified upstream behaviour → no code
     change, add a clarifying comment so it is not re-flagged.
   - SETUP/base-ref notes (e.g. "origin/master does not exist, reviewed origin/main") →
     dismiss as review-harness noise if your `args.base` was already correct.
   - Broader hardening (dependency pinning, etc.) → file as out-of-scope issue.
4. **Do NOT re-run the whole workflow blindly** just to get green — it is expensive and the
   Round-1 findings are already valid. Re-running is only worth it to *restore the
   independent second opinion*; if you do, use
   `Workflow({scriptPath, resumeFromRunId})` so unchanged agents replay from cache and only
   the failed verify agents re-execute.
5. **Record the caveat honestly** in the PR/report: these findings had one reviewer plus
   your manual check, not the intended independent adversarial pass.

## Verification
- You have read `.result.unverified` for all N findings (not just the ~8 shown before the
  notification truncated).
- Every finding is routed: fixed / already-correct / issue-filed / dismissed-with-reason.
  None silently dropped.
- Re-run your own quality gate (tests, lint) after fixes; report the counts.

## Example
`feature-review` returned `{confirmed:[], dismissed:[], unverified:[F1..F19], counts:{raw:19,
confirmed:0, unverified:19}}` with `<failures>` = 40× "Login expired" (19 verify × 2
retries + 2 lenses). Recovery: read `tasks/<id>.output` (paged past the truncation),
triaged 19 findings → 14 fixed in-scope (TDD), 1 already-correct (added comment), 1 filed as
an out-of-scope issue, 3 dismissed as base-ref/spec-artefact noise. Suite went 40 → 57
tests; PR body documented that Round 2 did not run.

## Notes
- `unverified` ≠ `dismissed`. The `/feature` Phase 8 contract is explicit: unverified
  findings must be individually verified by reading the cited file, never dropped.
- The truncated `<result>` in the notification typically shows only the first ~8 findings;
  always open the `.output` file for the rest.
- Two Round-1 lenses failing (commonly `integration` and `conventions`, which do more
  tool/Bash/WebFetch work and so are likelier to be mid-call when the token dies) means
  those lenses have NO findings at all — note the coverage gap, and self-check those lenses
  if the change touches integration points or repo conventions.
- Guard rule from the workflow tool: read the structured `.output`/`journal.jsonl` result,
  never the raw `agent-*.jsonl` transcripts.

## References
- Related: `workflow-task-output-envelope`, `workflow-args-defensive-parse` (other
  feature-review/workflow operational gotchas).
