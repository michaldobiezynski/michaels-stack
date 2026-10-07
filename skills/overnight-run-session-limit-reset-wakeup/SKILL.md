---
name: overnight-run-session-limit-reset-wakeup
description: |
  Keep an overnight autonomous Claude Code run alive across a subscription
  session-limit outage. Use when: (1) Workflow subagents or Agent tasks fail
  with "You've hit your session limit · resets HH:MM", (2) an overnight /loop
  or long autonomous build must continue after the reset, (3) a morning
  check-in reveals the session idled for hours after a limit reset. Core
  rule: the failure message names the reset time; immediately schedule
  chained ScheduleWakeup hops (max 3600s each) that bridge to just PAST the
  reset, then resume the failed workflow with resumeFromRunId so cached
  agents replay free.
author: Claude Code
version: 1.0.0
date: 2026-07-10
---

# Surviving session-limit resets in overnight autonomous runs

## Problem

During a long autonomous run, fan-out workflows burn the subscription's
session budget. Subagents start failing with
`You've hit your session limit · resets 1:20am (Europe/London)`. The
workflow completes partially, its completion notification wakes the main
loop while the limit is still active, and any wake-ups scheduled earlier
fire into a rate-limited session and die. Result: the run sleeps from the
failure until a human returns, losing the entire post-reset window (six
hours in the observed case).

## Context / Trigger Conditions

- `<failures>` blocks in a task-notification listing many agents with
  "You've hit your session limit · resets HH:MM".
- An overnight instruction like "keep improving until morning".
- ScheduleWakeup exists but clamps to 3600s, so a single hop cannot reach a
  reset several hours away.

## Solution

1. **Parse the reset time from the failure message.** It is the single most
   valuable fact in the notification; do not discard it.
2. **Stop launching new LLM work** until the reset. Local work (builds,
   tests, link checks, commits, deploys of already-written content) still
   works: the limit applies to model calls, not the machine.
3. **Bridge to the reset with chained wake-ups.** ScheduleWakeup clamps to
   3600s, so schedule an hourly chain: each wake-up's prompt carries the
   target reset time and instructs re-scheduling until `now > reset + 5min`.
   Example prompt payload: "If current time is before 01:25, ScheduleWakeup
   again for min(3600, secondsUntil(01:25)); otherwise resume workflow
   wf_XXX with resumeFromRunId and continue the build."
4. **After the reset, resume rather than relaunch**: `Workflow({scriptPath,
   resumeFromRunId})` replays completed agents from cache; only the failed
   writes/reviews re-run, costing a fraction of the original run.
5. **Deploy the partial state first** if the project is deployable: users
   wake up to the best available version even if the tail work is pending.

## Verification

On resume, the workflow's usage block shows cached agents completing
instantly and only the previously-failed agents consuming tokens; the
morning gap disappears from the run timeline.

## Notes

- Budget the night: a 34-game × (write + high-effort review) fan-out plus a
  12-chapter fleet plus a 37-game fleet consumed a full session budget in
  roughly 40 minutes. Sequence the biggest fleets first, or stagger them,
  when running on a subscription rather than API billing.
- The main conversation may keep working after subagents are throttled;
  treat subagent failures as the early warning.
- Do not rely on the workflow-completion notification as the resume signal:
  it arrives while the limit is still active.
