---
name: fan-out
description: Parallel-delegation mode that splits tasks with independent sub-problems across a team of agents launched concurrently in a single message, each given a self-contained prompt containing the literal word "ultrathink". Use when the user says "fan out", "parallelise this", "spawn agents", "use a team", or wants multi-angle research, review, or large-surface search run concurrently.
argument-hint: [off | a task to fan out across agents now]
---

# Fan out

A session mode: apply these rules to every qualifying task until the user invokes `/fan-out off`.

## Input

- No arguments: switch the mode on and confirm in one short line.
- `off`: stop applying the mode and confirm in one short line.
- Anything else: switch the mode on and treat the text as the task to fan out now.

## Rules

- For tasks with independent sub-problems, spawn a team of agents in parallel rather than working serially. Send all agent calls in a single message so they execute concurrently; sequential spawning wastes wall-clock time and context.
- Each agent starts cold with no view of the conversation, so every prompt must be self-contained: the goal, the relevant background, the expected output shape, and the length cap.
- Include the literal word "ultrathink" in every agent prompt body. It raises the reasoning budget for that subagent; without it they default to shallower thinking and produce worse answers on non-trivial work. The keyword goes inside the prompt content, not the description field, and it goes in regardless of whether the parent invocation used ultrathink.
- Use agents for genuinely independent work (parallel research, multi-angle review, large-surface searches), not as a reflex. Do not duplicate work an agent is already doing.
- Synthesise agent outputs into your own answer rather than relaying each agent verbatim. When agents disagree, surface the disagreement and arbitrate with reasoning; do not average their conclusions.
