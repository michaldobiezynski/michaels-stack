---
name: scout-mcp-inline-then-workflow-fanout
description: |
  Orchestration pattern for Claude Code Workflow runs that need data from an
  MCP server (especially a session-spawned stdio server, or any
  single-connection / fragile / interactively-authenticated MCP server). Use
  when: (1) you are about to spawn parallel Workflow subagents that each call
  the same mcp__* tool; (2) the MCP server has shown fragility this session
  (a tool returned "MCP error -32000: Connection closed" or the tool list
  briefly disappeared); (3) the work is research/synthesis/judging OVER
  retrieved records, where the retrieval is separable from the reasoning.
  Pattern: do the MCP retrieval INLINE in the main loop (you control
  concurrency), then pass the retrieved data into the Workflow as args/prompt
  so subagents reason MCP-free. Avoids concurrent subagents contending on one
  stdio connection and avoids the headless-MCP-absent caveat.
author: Claude Code
version: 1.0.0
date: 2026-06-09
---

# Scout MCP inline, then fan out a Workflow over the retrieved data

## Problem
Ultracode / a substantive task pushes you to use the Workflow tool, but the
data lives behind an MCP server. Naively, each parallel subagent calls the
mcp__* tool itself. Two failure modes:
1. **Contention / fragility.** A session-spawned **stdio** MCP server is a
   single process on one connection. N concurrent subagents hammering it can
   overload it or trip a `Connection closed` (-32000). Stdio MCP servers are
   not built for fan-out.
2. **Absent in headless runs.** Interactively-authenticated MCP servers (e.g.
   claude.ai connectors) may not be present in a workflow's subagent context
   at all, so the calls silently fail.

## Context / Trigger conditions
- You are composing a `Workflow({...})` whose subagents would each invoke an
  `mcp__*` tool (query/search/retrieve).
- The MCP server is the session's stdio server (argv often shows
  `uv run --project ... python -m <server>`), or any single-writer / fragile
  endpoint.
- You have ALREADY seen instability this session: `MCP error -32000:
  Connection closed`, a deferred-tool list that vanished, or a reconnect was
  needed via `/mcp`.
- The task decomposes into RETRIEVE (needs MCP) + REASON (drafting,
  judging, verifying, synthesising) where REASON only needs the retrieved text.

## Solution
1. **Scout inline.** In the main loop, run the MCP retrieval yourself
   (`query_speaker`, `query_council`, etc.). You control the call count and
   ordering; small concurrent batches (2-3) are usually safe, but you decide.
2. **Compact + pin.** Select the strongest records, keep verbatim text + a
   stable id + the citation/clip url for each. This is the data the workflow
   reasons over AND what you will citation-verify later.
3. **Pass data into the Workflow**, not tool access. Put the compacted quotes
   in the script (a `const`, or via the `args` global). Subagents then draft /
   steelman / judge / verify FROM the provided text and need NO MCP access — so
   contention and headless-absence both disappear.
4. **Keep deterministic verification in the main loop.** Run the MCP
   verification tool (e.g. `verify_citations`) yourself on the final synthesis,
   where you control inputs and ordering — don't delegate it to a subagent that
   might not reach the server.
5. This is the "hybrid: scout inline first, then pipeline over it" guidance the
   Workflow tool itself recommends — apply it specifically whenever the
   work-list comes from a fragile MCP source.

## Verification
- The workflow runs to completion with subagents that made ZERO mcp__* calls
  (check the run: subagents only emitted structured output from the passed
  data).
- No `Connection closed` during the run.
- Final artefact's citations pass the deterministic verifier (run inline).

## Example
Task: "build a debate between two corpus speakers." Instead of a workflow whose
subagents each query the council MCP, the main loop ran two `query_speaker`
calls, pinned ~10 verbatim quotes (text + clip_url + id) per side, then launched
a 3-agent panel (advocate A, advocate B, adversarial judge) that reasoned ONLY
over the embedded quotes. The panel returned clean structured output; the main
loop then ran `verify_citations` (11/11 verified) before presenting. Zero MCP
calls inside the workflow, zero contention — earlier in the same session the
stdio server had died with `-32000 Connection closed` under direct load.

## Notes
- Corollary: if a subagent genuinely MUST hit MCP, prefer ONE retrieval agent
  feeding the rest, not N parallel retrievers on one stdio connection.
- The same server that crashes under fan-out is usually fine for a few
  sequential/2-3-way main-loop calls — the fix is where the concurrency lives,
  not avoiding the server.
- After merging fixes to an MCP server's own code, the session's stdio tools
  still run the OLD code until `/mcp` reconnect (a separate, well-known gotcha);
  don't conflate "stale code" with "contention".
- Passing data via the Workflow `args` global keeps prompts clean and makes the
  script re-runnable; embedding quotes as a script `const` is fine for one-shot.
