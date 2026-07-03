---
name: council-mcp-over-http-and-ladybug-writer-lock
description: |
  Two linked council-of-thinkers operational fixes. (A) Call the council MCP tools
  when the session's mcp__council-of-thinkers__* tools are NOT connected: ToolSearch
  "+council" returns nothing, but the backend is up (lsof :8766) and curl
  http://127.0.0.1:8766/mcp returns HTTP 406. The server speaks streamable-HTTP MCP;
  drive it directly over JSON-RPC. (B) Graph tools (explore_speaker / explore_concept /
  compare_speakers) error with "LadybugDB at .../ladybugdb/council is held open by
  PID N. Shut that writer down ... or remove ...council.cot.lock" — a running
  phase2_extract_concepts.py writer holds the single-writer lock and blocks all graph
  reads, while query_speaker / query_council (LanceDB) still work. Use when wiring up
  council queries from a session without the MCP tools, or when graph reads are locked.
author: Claude Code
version: 1.0.0
date: 2026-06-18
---

# Council MCP over HTTP + the LadybugDB single-writer lock

## Problem

You need council data (`explore_speaker`, `query_speaker`, `compare_speakers`, etc.)
but either:

- **(A)** the `mcp__council-of-thinkers__*` tools are not in the session toolset
  (`ToolSearch "+council"` -> "No matching deferred tools"), even though the server
  is configured in `~/.claude.json` and running; or
- **(B)** the graph tools fail with `LadybugDB at .../ladybugdb/council is held open
  by PID N`, while the chunk tools still work.

## Context / Trigger conditions

- `lsof -nP -iTCP:8766 -sTCP:LISTEN` shows a `python -m council_mcp.server` process.
- `curl -s http://127.0.0.1:8766/mcp` -> `Not Found` on `/` but `/mcp` returns
  **406** (missing `Accept` header) — i.e. it is a streamable-HTTP MCP endpoint.
- Graph-tool errors naming a `phase2_extract_concepts.py` PID and a
  `ladybugdb/council.cot.lock` file.

## Solution

### (A) Drive the MCP server over HTTP (JSON-RPC)

The `406` means it wants `Accept: application/json, text/event-stream`. Flow:
`initialize` (capture `mcp-session-id` from response headers) ->
`notifications/initialized` -> `tools/list` / `tools/call`. Responses are SSE, so
read the `data:` line. Use the helper in `scripts/mcp_http_call.py` (copy to /tmp):

```bash
python3 /tmp/mcp_http_call.py tools                                  # list tools
python3 /tmp/mcp_http_call.py call query_speaker \
  '{"speaker":"cliff_weitzman","query":"quality","top_k":12}'        # call a tool
```

Argument-name gotchas (verified):
- `query_speaker` takes **`speaker`** (not `speaker_id`) and `query`.
- `query_council` takes `query` (+ optional `speaker_id`, `top_k`,
  `balance_by_speaker`).
- `compare_speakers` needs a **resolved canonical concept** for graph edges — see
  `council-of-thinkers-compare-speakers-needs-resolved-concept`.

This avoids needing the user to reconnect via `/mcp`. (Restarting the local dev
stack does NOT reconnect the session's stdio tools either — see
`council-of-thinkers-local-dev`.)

### (B) Unblock the LadybugDB writer lock

LadybugDB is **single-writer**. A running `phase2_extract_concepts.py` holds an
exclusive lock; graph reads (`explore_speaker`, `explore_concept`,
`compare_speakers`) then error. **`query_speaker` / `query_council` use LanceDB and
keep working** — so prefer those for chunk-level work while the graph is locked.

If the writer is a legitimately-running extraction, do NOT kill it casually (it is
expensive, ~hours; it is resumable via `--skip-existing` + ledger, so at most the
in-flight batch of 25 is lost). But if it is a **wedged/runaway** run (see Notes),
stop it **top-down so the supervisor cannot respawn the child**:

```bash
# 1. kill the respawner FIRST, then the hung child
kill -TERM <phase2_run_to_completion.py PID> <daily_ingest.sh PID> <caffeinate PID>
kill -TERM <phase2_extract_concepts.py PID>   # hung -> may need -KILL after a few s
# 2. remove the stale lock ONLY after confirming its PID is dead
cat ladybugdb/council.cot.lock          # holds the PID
ps -p <pid> || rm -f ladybugdb/council.cot.lock
```

Then re-test a graph read (`explore_speaker`) — it should succeed.

## Verification

- (A) `tools/list` returns `query_council, explore_speaker, compare_speakers, ...`.
- (B) `explore_speaker` returns `top_concepts_overall` instead of the LadybugDB
  "held open by PID" error; the lock file is gone or owned by a live, intended
  writer.

## Notes

- **Spotting a runaway extraction**: the daily-ingest log shows cycles like
  `cycle: +2 -> 34831/all [HUNG-killed (no output)]` making ~no progress over
  hours. Root cause seen in the wild: **file-descriptor exhaustion**
  (`RuntimeError: lance error ... Too many open files (os error 24)`) in the
  long-lived process; each relaunched extractor opens nothing, hangs, is killed,
  relaunched — while holding the graph lock. The supervisor chain is
  `launchd(com.council.daily-ingest) -> daily_ingest.sh -> phase2_run_to_completion.py
  (+ caffeinate) -> phase2_extract_concepts.py`.
- The launchd job is `RunAtLoad=false` + `StartCalendarInterval` 10:00 (no
  KeepAlive), so killing the chain does **not** trigger an immediate relaunch; it
  next runs at 10:00.
- Related: `council-of-thinkers-local-dev`,
  `council-of-thinkers-compare-speakers-needs-resolved-concept`,
  `adaptive-backoff-diagnoses-stall-cause`.
