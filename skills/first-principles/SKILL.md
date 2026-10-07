---
name: first-principles
description: Approach mode for engineering tasks that decomposes the problem to first principles before choosing a solution, investigates the codebase and real library behaviour before implementing, and delegates parallel investigation to one-concern-per-agent sub-agents. Use when the user says "first principles", "investigate first", "don't pattern-match", or asks to investigate or decompose the problem before a non-trivial feature, refactor, or debugging task.
argument-hint: [off | a task to approach this way now]
---

# First principles

A session mode: apply these rules to every engineering task until the user invokes `/first-principles off`.

## Input

- No arguments: switch the mode on and confirm in one short line.
- `off`: stop applying the mode and confirm in one short line.
- Anything else: switch the mode on and treat the text as the task to approach this way now.

## Rules

- Break the problem down to first principles before reaching for a solution: why is this needed, what does success actually look like, which constraints genuinely apply. Do not pattern-match ('this looks like X, so I'll do X') without confirming the pattern fits.
- Investigate before implementing. Read the surrounding code, the relevant tests, the call sites, and the actual library or API behaviour. Conventions in this codebase override conventions seen elsewhere; verify, do not assume.
- For non-trivial tasks, delegate parallel investigation to sub-agents, one concern per agent: codebase search, library behaviour verification, alternative approaches, existing pattern audit. Synthesise their findings before writing code. In single-context environments, run the same passes sequentially and label them.

## Chaining

Pairs with `/honest-report` (evidence-based claims about the investigation) and `/clean-output` (terse presentation of the resulting change).
