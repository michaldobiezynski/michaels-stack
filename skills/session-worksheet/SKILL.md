---
name: session-worksheet
description: Maintain a resumable worksheet for tasks spanning more than one sitting - goal, tickable plan, decisions with reasons, current state, remaining work - committed alongside the code so resume-state travels with the branch. Use when starting spec-driven or multi-day work, when a task will be handed to a fresh agent or continued on another machine, when the user says "worksheet", "checkpoint this", or "make this resumable", and when RESUMING such work (read the newest worksheets/*.md before re-deriving state from git diff). Do NOT use for single-sitting tasks; it adds ceremony without payoff.
argument-hint: [<task-slug> | resume]
---

# Session worksheet

Mid-task resumable state that travels with the repo. Distinct from the global memory system (durable cross-conversation facts) and from /plan (an up-front plan, not a living document): a worksheet is step-level state a fresh agent can resume from cold, versioned with the branch it describes.

## When

Only for work spanning more than one sitting, spec-driven builds, or any task likely to be handed to a fresh agent or another machine. If the task will finish in this sitting, skip this skill.

## Create

Before starting multi-step work, create `worksheets/YYYY-MM-DD-<slug>.md` in the repo root containing:

- **Goal** (one sentence)
- **Plan** (numbered steps, tick as completed)
- **Decisions** (what was chosen and why, appended as they are made)
- **Current state** (enough for a fresh agent to resume cold: branch, last completed step, known-broken bits)
- **Remaining work**

Commit the initial file as `chore: (worksheets) add <slug>`.

## Maintain (the load-bearing rule)

- Update the worksheet after **each completed step**, in the **same commit** as that step's code. A stale worksheet is worse than none: it actively misleads the resuming agent. If you cannot update it truthfully, delete the stale sections rather than leave them wrong.
- Personal repos: commit `worksheets/`. Shared/team repos: gitignore it unless the team has agreed to it.
- Do not create per-worksheet git tags; `ls worksheets/` is the index and the tag namespace stays reserved for releases.

## Resume

1. Read the newest `worksheets/*.md` first, before re-deriving state from `git diff`/`git log`.
2. Verify its "Current state" against the actual repo state; where they disagree, trust the repo and correct the worksheet in your first commit.
3. Continue ticking the plan; keep updating per step.

## Finish

When the task completes, record the outcome in a final "Done" line. Leave the worksheet in place as the decision log ("why was this built this way"); do not delete it.
