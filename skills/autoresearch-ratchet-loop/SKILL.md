---
name: autoresearch-ratchet-loop
description: |
  Greedy-ratchet pattern for autonomous iterative improvement of strategies,
  prompts, or configurations. Use when: (1) building self-improving agent loops,
  (2) optimising prompts/strategies through trial and error, (3) running Claude Code
  as an outer-loop agent that iterates on inner-loop performance, (4) any task where
  you commit a variant, measure it, keep improvements, discard regressions, and repeat.
  Covers: strategy files, commit discipline, results tracking, exploration rules,
  and resume support across sessions.
author: Claude Code
version: 1.0.0
date: 2026-03-31
---

# Autoresearch Greedy-Ratchet Loop

## Problem
You need an autonomous system that iteratively improves a strategy, configuration,
or prompt by testing variants, keeping what works, discarding what doesn't, and
repeating — without human intervention.

## Context / Trigger Conditions
- Building a self-improving agent (e.g., browser automation, code generation, testing)
- Optimising prompts or strategies through systematic experimentation
- Running Claude Code as an orchestrator that manages inner-loop experiments
- Any measurable task where you want to find the best approach automatically

## Solution

### Architecture

```
Outer loop (Claude Code) → edits strategy → runs inner loop → evaluates → keeps/discards → repeats
```

### Core Components

**1. Strategy files (the mutable target)**
Store configuration as JSON files that the outer loop edits:
```json
{
  "instructions": "...",
  "parameters": { "max_steps": 15, "timeout": 300 },
  "num_runs": 3
}
```

**2. Results tracking (the ratchet mechanism)**
Append-only TSV or JSON log (gitignored) that persists across sessions:
```
timestamp  variant  result  time  score  config_hash  commit  kept
```

**3. The loop (7 steps, repeat until killed)**

1. **Read results** — check what's been tried, current best score
2. **Decide what to change** — based on failure patterns, try a new variant
3. **Commit BEFORE running** — `git commit -m "try: <description>"`
4. **Run N attempts** (N≥3 for nondeterministic tasks) — measure success rate
5. **Evaluate** — keep if better than best, discard if worse: `git reset --hard HEAD~1`
6. **Log results** — append to TSV (survives git reset because gitignored)
7. **REPEAT** — never stop, never ask confirmation, loop until timeout kills you

**4. Commit discipline**
- Commit strategy changes BEFORE running (so you can revert)
- Results TSV is gitignored (survives `git reset --hard`)
- Git history = successful strategy evolution
- Use `git reset --hard HEAD~1` to discard failed variants

**5. Exploration rule**
Every Nth variant (e.g., every 8th), try something radically different regardless
of recent success. This prevents local optima:
- Completely rewrite the strategy
- Change parameters dramatically
- Remove all optimisations and start fresh

**6. Resume support**
Check for existing results at startup. If results.tsv exists, skip tried strategies
and resume from where the last session left off.

**7. Diagnostic mode**
If stuck after 15+ failed variants, run a diagnostic-only attempt that collects
maximum information without trying to succeed. Use findings to write targeted strategies.

### Orchestrator Script

```bash
#!/usr/bin/env bash
set -euo pipefail
BRANCH="autoresearch/$(date +%Y%m%d-%H%M)"
git checkout -b "$BRANCH" main
timeout "${TIMEOUT}h" claude \
    --print --dangerously-skip-permissions --max-turns 500 \
    -p "Read program.md. Begin the ratchet loop. Do not ask for confirmation."
```

### Key Metrics to Track
- **Success rate** (solved/total) — primary metric
- **Time per attempt** — secondary metric for optimisation
- **Config hash** — identify which strategy produced which results
- **Error column** — distinguish crashes from failures

## Verification
The ratchet is working when you see:
1. Results TSV growing with each run
2. Git history showing "try:" commits with some reverts
3. Success rate improving over time (or holding steady while time improves)
4. Exploration variants appearing periodically

## Example

A browser automation agent that solves challenges:
- **Strategy file**: instructions for the browser agent, model params, timeouts
- **Inner loop**: run the agent 3 times, measure solve rate
- **Evaluation**: keep if solve rate > previous best
- **Result**: evolved from 30-min solves to 6-min solves over 44 attempts

## Notes
- The outer loop (Claude Code) uses cloud intelligence; the inner loop can use
  anything (local LLM, deterministic script, API calls)
- Nondeterministic tasks MUST use multiple runs per variant (≥3) to avoid
  keeping/discarding based on luck
- The exploration rule is critical — without it, the ratchet gets stuck
  optimising minor details of a suboptimal approach
- Rate limit awareness: on Max plan, expect ~90 min of intensive use before
  limits. Save state and commit before hitting limits.
- The results TSV being gitignored is essential — `git reset --hard` must not
  destroy measurement history
- Watch out for the agent learning to game success detectors rather than
  actually solving the task (e.g., embedding trigger words in output)

## References
- [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — the original
  greedy-ratchet pattern this skill is based on. Karpathy's approach: treat research
  as an optimisation loop where an LLM agent iteratively improves its own strategy,
  committing improvements and discarding regressions.
