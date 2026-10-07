---
name: subagent-idle-without-report-pull-it
description: |
  Named subagents/teammates can signal idle WITHOUT delivering their final report, so the
  work looks lost. Use when: (1) you spawned an agent with the Agent tool and received a
  bare {"type":"idle_notification","idleReason":"available"} teammate-message with no
  findings, (2) ListAgents shows a teammate as "idle" but you never got its output,
  (3) a review/research agent has been running a long time and you are tempted to respawn
  it, (4) a spawned agent fans out into many subagents and never converges. Fix: SendMessage
  the agent asking for the findings verbatim in its reply; if two explicit requests fail,
  TaskStop it and respawn with a tightened brief.
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# A subagent going idle is not a subagent reporting

## Problem

An agent spawned with the Agent tool (`name:` set) finishes its work and emits only:

```json
{"type":"idle_notification","from":"<name>","idleReason":"available"}
```

No findings. The result the agent produced is still retrievable, but it will not arrive
on its own, and the notification carries no hint that anything is missing. Observed on
three independent agents in one session, so treat it as the norm rather than a glitch.

## Solution

1. **Pull the report**: `SendMessage({to: "<name>", message: "You signalled idle but your
   report did not reach me. Send your findings now as your reply message (not a file, not
   a summary of intent) ..."})`. Restate the required format and say explicitly what to do
   about empty sections ("if you found nothing on a question, say so in one line rather
   than omitting it"). This usually returns the full report immediately, and works
   repeatedly for follow-up rounds on the same agent, which keeps its context.
2. **Re-point it if the target moved**: an agent that has been running a while may have
   reviewed a file you have since rewritten. Tell it to re-read and list what changed, so
   it does not report defects that no longer exist.
3. **Two strikes, then respawn**: if two explicit requests produce nothing (watch for the
   agent having spawned many subagents of its own and never converging), `TaskStop` it and
   spawn a replacement with a tightened brief:
   - "Do NOT spawn subagents. Do the work yourself."
   - "Budget roughly N web/API lookups, then STOP and report."
   - "Your final message IS the report. Return findings as text, not a file."

## Verification

After the SendMessage, the findings arrive as a normal teammate-message. `ListAgents`
showing `idle` both before and after is expected and is not evidence either way.

## Notes

- Do not sit in a `sleep`/`ListAgents` poll loop waiting for a report that will never
  self-deliver; and never fabricate or predict what a pending agent will say.
- The idle ping can repeat (an agent may ping again 45 min later, still with nothing).
  Repeat pings are availability signals, not new findings.
- While waiting, do the independent work yourself. In the session that produced this
  skill, checking the single most important review question directly found a real defect
  before any reviewer reported.
