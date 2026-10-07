---
name: langgraph-verify-tool-call-thread-state
description: |
  Prove that an agent deployed behind langgraph dev / LangGraph Agent Server
  actually called its tool, instead of trusting a plausible-looking answer.
  Use when: (1) an agent's reply contains facts the base model plausibly knows
  anyway, so output alone cannot confirm tool grounding, (2) verifying
  homework/lab agents whose spec requires a tool call, (3) debugging why a
  tool is NOT being called, (4) you cannot see the agent's stdout because it
  runs server-side. Solution: read the thread's message history via
  GET /threads/{id}/state (langgraph_sdk get_sync_client().threads.get_state)
  and look for the ai message's tool_calls plus the matching tool message.
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# Verify a Deployed Agent's Tool Call via Thread State

## Problem

An agent served by `langgraph dev` answers a question correctly and in
persona, but that proves nothing about *how*: if the base model already knows
the facts (famous people, common knowledge), it may have skipped the tool
entirely. Server-side execution means no stdout to watch, so "the answer looks
grounded" is an unverifiable claim.

## Context / Trigger Conditions

- Agent runs behind the LangGraph Agent Server API (`langgraph dev`, port 2024
  by default) rather than in-process.
- The task requires the tool to fire (course homework, grounding guarantees,
  tool-routing debugging).
- The reply's content overlaps with the model's parametric knowledge.

## Solution

Threads persist server-side, so fetch the conversation's full message list and
inspect the sequence:

```python
from langgraph_sdk import get_sync_client

client = get_sync_client(url="http://127.0.0.1:2024")
state = client.threads.get_state(thread_id)
for m in state["values"]["messages"]:
    if m.get("type") == "ai" and m.get("tool_calls"):
        print([tc["name"] for tc in m["tool_calls"]], "args:",
              [tc["args"] for tc in m["tool_calls"]])
    elif m.get("type") == "tool":
        print("tool result:", m.get("name"), str(m.get("content"))[:80])
```

Proof of grounding is the pair: an `ai` message carrying `tool_calls` with
your tool's name, followed by a `tool` message with its result, before the
final `ai` answer. The thread id comes from `client.threads.create()` (or
`threads.search()` for recent ones).

## Verification

Verified 26/08/2026 on the lca-deepagents m5.2 homework: the reply about Paul
Morphy looked tool-grounded either way; thread state showed
`chess_legend_fact({'player': 'Morphy'})` followed by the tool result, which
settled it.

## Notes

- This is the same data LangGraph Studio's debugger renders; the SDK route is
  scriptable and works headless. With `LANGSMITH_TRACING=true` the trace in
  LangSmith shows the same call tree as a third witness.
- Negative test worth adding: ask about something outside the tool's data and
  check the agent reports the gap instead of answering from memory.
- Gotcha: only one `langgraph dev` can bind port 2024; stop the previous lab's
  server first or the new one fails to boot.

## References

- [Agent Server API reference](https://docs.langchain.com/langsmith/server-api-ref)
- [LangGraph Python SDK](https://reference.langchain.com/python/langgraph-sdk)
