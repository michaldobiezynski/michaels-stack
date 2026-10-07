---
name: workflow-agent-fanout-cap-and-offline-harness
description: |
  Stop a Claude Code Workflow script spawning far more sub-agents than intended, and prove
  the cap holds without spending any. Use when: (1) a Workflow run reports a surprising
  agent count, e.g. 50 agents for one PR review, (2) a workflow spawns one agent per item
  over a list whose length you do not control (one verifier per finding, one fixer per file),
  (3) you are editing a workflow script and want to assert its fan-out before running it for
  real, (4) an option like isWebUI or extraLenses quietly adds another agent and breaks a
  cap, (5) you need to check that no prompt tells its own sub-agent to "use a team of
  agents". Covers the recursive-fan-out-via-prompt-text trap, per-item versus batched
  agents, deriving phase counts from one AGENT_BUDGET constant, and an offline harness that
  runs the script with agent/parallel/phase/log stubbed so the fan-out is unit-testable.
author: Claude Code
version: 1.0.0
date: 2026-08-04
---

# Capping sub-agent fan-out in a Workflow script, and testing it offline

## Problem

A two-round PR review workflow spent **50 sub-agents on a single PR**. The script looked
modest: a handful of review lenses, then a verification round. Two separate causes, and the
expensive one is invisible unless you read the prompt strings.

**Cause 1, structural: one agent per item over an unbounded list.**

```js
// Round 2: one verifier per finding. Round 1 found 44. That is 44 agents.
const checked = await parallel(deduped.map(verifyThunk))
```

The list length is an *output* of the previous phase, so the agent count is unbounded in the
size of the review. A thorough Round 1 is punished with a combinatorial Round 2.

**Cause 2, textual: the prompt told each agent to fan out again.**

```js
const ROUND1 = `use a team of agents to do a deep research review of this PR...`
// ...embedded into every lens agent's prompt
```

Each of the seven lens agents was being instructed to spawn its own team. The script's own
`parallel()` call showed seven agents; the real tree was far wider. Nothing in the workflow
source reveals this. You have to read the prompt *content*, not the control flow.

## Context / Trigger Conditions

- A Workflow run's `agent_count` is much larger than the number of `agent()` calls you can
  see in the script.
- The script contains `parallel(someDerivedList.map(...))` where the list comes from a
  previous phase.
- Prompt constants contain "use a team of agents", "spawn agents to", "delegate this to".
- An `isWebUI`, `extraLenses` or similar option appends to a lens array, so enabling it
  silently raises the agent count past whatever cap you thought you had.
- A retry path (`if (failed.length) parallel(failed.map(...))`) adds agents on top of a cap.

## Solution

### 1. Declare one budget constant and derive every phase from it

Do not scatter magic numbers. One constant, and the phase counts fall out of it, so the cap
cannot drift when someone edits a phase.

```js
const AGENT_BUDGET  = Math.max(2, Math.min(12, Number(a.agentBudget) || 6))
const LENS_AGENTS   = Math.max(1, Math.min(4, AGENT_BUDGET - 2))
const VERIFY_AGENTS = Math.max(1, AGENT_BUDGET - LENS_AGENTS)
```

### 2. Replace per-item agents with a fixed number of batched agents

Slice the list across the agents you can afford, round-robin so batch sizes stay even, and
have each agent return an array of results keyed by id.

```js
function chunk(items, buckets) {
  const out = Array.from({ length: Math.max(1, Math.min(buckets, items.length)) }, () => [])
  items.forEach((item, i) => out[i % out.length].push(item))
  return out
}

const batches = chunk(deduped, VERIFY_AGENTS)
const lists   = await parallel(batches.map((b, i) => verifyBatchThunk(b, i)))
```

The batch schema must demand one entry per input id, and the script must reconcile by id so
an omitted id becomes `unverified` rather than vanishing:

```js
const verdictById = {}
for (const list of lists.filter(Boolean)) for (const v of list) if (v?.id) verdictById[v.id] = v
const checked = deduped.map((f) => ({ ...f, verdict: verdictById[f.id] || null }))
```

### 3. Tell each agent to work alone

Rewrite embedded prompts so they cannot recurse:

```js
const ROUND1 = `Review this PR yourself, working alone. Do NOT spawn sub-agents; the review
is already split across a small team and you are one member of it. ...`
```

Keep the phrase on one line. A template literal that wraps as `do\nNOT spawn sub-agents`
still reads fine to a model but defeats any grep you write to enforce it.

### 4. Make optional lenses fold in, never append

An option that appends to the lens array breaks the cap silently. Fold it into an existing
lens instead, and merge any overflow:

```js
if (isWebUI) requested[requested.length - 1].focus += WEB_FOCUS   // fold, do not push

function packLenses(lenses, max) {
  if (lenses.length <= max) return lenses
  const kept = lenses.slice(0, max - 1)
  const tail = lenses.slice(max - 1)
  kept.push({ key: tail.map((l) => l.key).join('+'),
              focus: tail.map((l) => `${l.key.toUpperCase()}: ${l.focus}`).join('\n\n') })
  log(`Merged ${tail.length} lenses so the cap holds.`)   // never truncate silently
  return kept
}
```

Merging one-concern lenses into fewer broader ones preserves coverage far better than
dropping lenses. Six one-concern reviewers became four: correctness+integration, security,
tests, and craft (conventions+performance+accessibility).

### 5. Drop retries, or count them

A retry path breaches a hard cap. Either budget for it explicitly, or drop it and return the
affected items as `unverified` with a do-not-drop note, so the orchestrator becomes the
fallback rather than another agent.

## Verification

Do not run it for real to find out. Run the script offline with the runtime globals stubbed.
Workflow scripts cannot be imported: they rely on injected globals and end in a top-level
`return`. Wrap and evaluate instead.

`scripts/workflow-harness.mjs` in this skill does it:

```js
import { runWorkflow, promptsEncouragingFanout } from './scripts/workflow-harness.mjs'

const { result, calls, logs } = await runWorkflow('/path/to/feature-review.js', {
  args: { isWebUI: true },
  onAgent: (prompt, opts) =>
    opts.phase === 'Review' ? { lens: opts.label, findings: [...] } : { verdicts: [...] },
})

const review = calls.filter((c) => c.phase === 'Review')
const verify = calls.filter((c) => c.phase === 'Verify')
console.assert(calls.length === 6)
console.assert(review.length === 4 && verify.length === 2)
console.assert(promptsEncouragingFanout(calls).length === 0)
```

Assert at least these, since each maps to a way the cap breaks:

| Assertion | Failure it catches |
| --- | --- |
| exact total agent count | any new `agent()` call slipping in |
| count with `isWebUI: true` and with `extraLenses` | options appending an agent |
| counts across several `agentBudget` values | phase maths not deriving from the budget |
| a stubbed agent that **throws** | a dead batch silently dismissing findings |
| a stub that **omits an id** | reconciliation dropping items |
| zero findings | verifier agents spawned for nothing |
| grep over generated prompts | recursive fan-out language |

## Example

Real before and after on one PR-review workflow:

| | Before | After |
| --- | --- | --- |
| Round 1 | 7 one-concern lens agents | 4 merged-lens agents |
| Round 2 | 1 verifier per finding (44) | 2 batched verifiers |
| Retries | unbounded | none, surfaced as `unverified` |
| Prompt text | "use a team of agents..." | "work alone, do NOT spawn sub-agents" |
| **Total** | **~50 agents** | **6 agents** |

32 assertions ran against the rewritten script in under a second, at zero agent cost. They
caught two real defects before it ever ran: a prompt whose key phrase wrapped across a line
break, and a test regex that matched the prohibition it was meant to enforce.

## Notes

- The harness stubs `parallel()` to run thunks sequentially by default so `calls` is ordered
  deterministically. It also mirrors the real contract that a throwing thunk resolves to
  `null` rather than rejecting, which is what makes error-path assertions meaningful.
- `new Function(...)` on your own config file is fine. Do not point the harness at a script
  you have not read.
- Counting `agent()` calls in the source is not enough on its own. Check the prompt strings
  too: a workflow's real cost is the tree, not the top level.
- Budget split heuristic that worked: reviewers get the larger share, verification gets the
  remainder with a floor of one. Reviewers determine what is found at all; verification only
  filters what was already found.
- Batched verification trades a little independence per finding for a bounded cost. If a
  finding genuinely needs isolated adversarial scrutiny, raise the budget for that run rather
  than reverting to per-item agents.
- Related: [[playwright-webserver-skips-build-stale-bundle]] for the same species of problem
  in test harnesses, where a green result proves less than it appears to.

## References

- The Workflow tool's own contract is the authority for the injected globals (`args`,
  `agent`, `parallel`, `pipeline`, `phase`, `log`, `workflow`, `budget`), the per-workflow
  concurrency cap of `min(16, cores - 2)`, the 1000-agent lifetime backstop, and the
  "no silent caps: log what was dropped" guidance. Read the tool description rather than
  relying on memory; these numbers have changed before.
- No external documentation exists for this: workflow scripts are a Claude Code internal
  format, so everything above was verified empirically against real scripts in
  `~/.claude/workflows/`.
