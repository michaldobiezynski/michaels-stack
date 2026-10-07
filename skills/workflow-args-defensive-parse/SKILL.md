---
name: workflow-args-defensive-parse
description: |
  Workflow tool scripts crashing with "pipeline() expects an array" or
  "args.X is undefined" even though the Workflow call passed a proper JSON
  object as `args`. Use when: (1) a Workflow dies instantly (duration <100ms,
  0 agents) with a TypeError on the first pipeline()/parallel() call,
  (2) `args.<key>` is undefined inside the script despite being present in
  the tool call. The args value may arrive stringified or reshaped; scripts
  must normalise before use. Also covers the free-retry path via
  resumeFromRunId after editing the persisted script file.
author: Claude Code
version: 1.0.0
date: 2026-07-16
---

# Workflow `args` defensive parse

## Problem

A Workflow script accessed `args.batches` (args was passed in the tool call
as `{"batches": [...]}`) and crashed at t=24ms with
`TypeError: pipeline() expects an array as the first argument` — the key
lookup returned undefined inside the script runtime.

## Solution

Open every workflow script that consumes `args` with a normaliser:

```js
const _a = typeof args === 'string' ? JSON.parse(args) : args
const items = Array.isArray(_a) ? _a : (_a && _a.batches)
if (!Array.isArray(items)) throw new Error(`bad args shape: ${JSON.stringify(args).slice(0, 200)}`)
```

The explicit `throw` with a JSON.stringify snippet turns the next failure
from a misleading TypeError deep in pipeline() into a first-line message
showing what actually arrived.

## Recovery is cheap — don't rebuild

Every Workflow invocation persists its script to a file (path in the tool
result). Fix = Edit that file, then relaunch with
`Workflow({scriptPath, resumeFromRunId})`. Completed agent() calls replay
from cache; a crash before any agent ran costs nothing to retry.

## The silent-empty-fanout variant (no crash, fake success)

Distinct from the TypeError case above: if `args` parses to an object but a
**numeric field is missing/undefined**, fanning out over it produces an empty
array and the workflow returns a *successful* empty result with no error:

```js
const N = A.count                     // undefined
Array.from({length: N}, ...)          // Array.from({length: undefined}) === []  -> 0 agents
await parallel([])                    // no-op, resolves instantly, NO throw
```

Signature: ~14 ms, `agent_count: 0`, and a result like `{total: 0, items: []}`
— looks like "nothing matched" rather than a bug. Guard with fallbacks + a
first-line `log()` of the derived count so a 0 is visible immediately:

```js
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const N = A.count || 40               // fallback, never undefined
const PATH = A.path || '<absolute-fallback>'
log(`fanning out over ${N} items from ${PATH}`)   // a 0 here is the smoking gun
```

## Large fan-out payloads: pass `{path, count}`, not the array

Agents (unlike the script) can read files. For a big work-list, write it to a
JSON file and pass only `{path, count}` in `args`; fan out over indices
`[0..count)` and have each agent `Read <path>` and take element `[i]`. Keeps
`args` tiny, sidesteps the stringify quirk for the bulk payload, and avoids a
60 KB array in the tool call. (Verified: 40-candidate discovery + 12-paper
reproduction pipelines both driven purely by `{path, count}` + per-agent index.)

## Notes

- Instant-death signature: duration under ~100ms with agent_count 0 means
  the script body threw before any agent spawned — a script bug, not an
  agent failure. (Or the silent-empty-fanout above, which does NOT throw.)
- Keep meta a pure literal; the normaliser goes in the body, after meta.
