---
name: council-of-thinkers-local-dev
description: |
  Start, stop, or check status of the council-of-thinkers local dev stack
  (Python MCP backend on :8766 + council-clip Next.js frontend on :3000).
  Use when the user asks to "start council", "run council locally",
  "spin up the council stack", "stop council", "kill council",
  "check council status", "is council running", or any variant referring
  to local development of the council-of-thinkers + council-clip projects.
  Invokes the shell scripts in council-of-thinkers/scripts (dev-up.sh,
  dev-down.sh, dev-status.sh) which handle pre-flight checks, detached
  backgrounding via nohup, PID tracking in /tmp, and port-based health
  checks. Also covers the SYNTHESIS_BASE_URL .zshrc requirement, and the
  critical gotcha that editing council_mcp code is NOT picked up by the
  agent's mcp__council-of-thinkers__* tools after a dev-up restart
  (those tools use a separate session-spawned stdio server — reconnect
  via /mcp, not dev-up.sh).
author: Claude Code
version: 1.2.0
date: 2026-05-26
---

# Council of Thinkers — local dev stack

## What this is

The council-of-thinkers project has two repos that must run together for
local development:

- **Backend**: `~/development/projects/council-of-thinkers` — Python MCP
  server, started via `uv run python -m council_mcp.server` with
  `COUNCIL_TRANSPORT=http`. Listens on `:8766`, serves `/mcp` and
  `/synthesis/{id}`.
- **Frontend**: `~/development/projects/council-clip` — Next.js app,
  started via `npm run dev` with `SYNTHESIS_API_BASE_URL=http://localhost:8766`.
  Listens on `:3000`.

Three scripts in the backend repo's `scripts/` directory handle the
lifecycle reliably:

| Want to... | Run |
|---|---|
| Start both | `~/development/projects/council-of-thinkers/scripts/dev-up.sh` |
| Stop both | `~/development/projects/council-of-thinkers/scripts/dev-down.sh` |
| Check status | `~/development/projects/council-of-thinkers/scripts/dev-status.sh` |

## Two servers — and which one the agent's MCP tools actually use

There are **two independent `council_mcp.server` processes**, and they
are easy to confuse:

| | Agent's MCP tools | dev-up.sh backend |
|---|---|---|
| Transport | **stdio** | HTTP on `:8766` |
| Spawned by | the Claude Code **session** at startup | `dev-up.sh` |
| Config | `~/.claude.json` → `mcpServers.council-of-thinkers` | `scripts/dev-up.sh` |
| argv tell | `uv run `**`--project`**` … python -m council_mcp.server` | `uv run python -m council_mcp.server` (no `--project`) |
| Serves | `mcp__council-of-thinkers__*` tool calls | council-clip frontend + `/synthesis` |
| Cycled by dev-down/dev-up? | **No** | Yes |

**CRITICAL GOTCHA:** editing `council_mcp/*.py` then running
`dev-down.sh && dev-up.sh` does **not** update the agent's MCP tools.
`dev-up` only cycles the `:8766` HTTP server and the `:3000` frontend; it
never touches the session-spawned stdio server. A committed code change
therefore stays invisible to `compare_speakers` / `query_council` / etc.
even after a full dev-stack restart.

**Symptom:** a tool returns output matching the *old* code while the
source (and `git log`) shows the change. Seen in practice: the #110
`compare_speakers` cartesian-product filter (commit `26306ed`, 11:18)
was still absent from the MCP tool output after a 14:36 `dev-up` restart
— because the stdio server had been running since 09:04, predating it.

**Diagnose:**

```bash
ps -Ao pid,lstart,command | grep council_mcp | grep -v grep
git log -1 --format=%cd -- council_mcp/server.py
```

The process whose argv contains `--project` is the agent's stdio server;
the other (often shown as `.venv/bin/python3 -m council_mcp.server`) is
the dev-up HTTP server. If the stdio server's start time predates the
commit, it is stale.

**Fix:** reconnect the MCP server *inside the session* — Claude Code
`/mcp` → reconnect `council-of-thinkers` (or restart the session).
`dev-up.sh` is irrelevant to the agent's MCP-tool code version, and a
tool call cannot recycle the stdio process (the harness owns it).

## Graph DB is single-writer — scripts can't open it while a server runs

The concept graph (`ladybugdb/council`) is opened as a **process-lifetime
singleton** behind an exclusive cross-process lockfile (#51 —
`concept_graph.get_graph_connection` caches one connection for the whole
process; `open_database` has no read-only mode). A running
`council_mcp.server` therefore holds the lock for its entire life, so an
external script that calls `graph_session()` / `within_connection()`
fails:

```
council_mcp.concept_graph.CotLockedError: LadybugDB at …/ladybugdb/council
is held open by PID <n>. Shut that writer down before opening again, or
remove …/council.cot.lock if you are certain it is stale.
```

**Do not** delete `council.cot.lock` or kill the PID while the server is
live — that PID is usually the session's stdio MCP server, and forcing
the DB open from a second process risks corruption. To read the graph
from a one-off script (e.g. enumerating CONTRADICTS edges), **stop the
council MCP server first**. Otherwise read it through the MCP tools
(`explore_concept`, `explore_speaker`, `compare_speakers`) — they are
served *by* the lock holder, so they never contend. The lock only blocks
*external* processes, never the tools themselves.

## How dev-up.sh works

1. **Pre-flight**: verifies `uv`, `npm`, `lsof` are installed; both repo
   directories exist; `node_modules` is present in the frontend; both
   ports are free. Fails fast with a clear message if anything is wrong.
2. **Backend**: `cd` into backend repo, `nohup uv run python -m
   council_mcp.server` with `COUNCIL_TRANSPORT=http`, log to
   `/tmp/council-backend.log`, PID to `/tmp/council-backend.pid`.
3. **Frontend**: `cd` into council-clip, `nohup npm run dev` with
   `SYNTHESIS_API_BASE_URL=http://localhost:8766`, log to
   `/tmp/council-frontend.log`, PID to `/tmp/council-frontend.pid`.
4. **Wait**: polls `lsof` on each port up to 30s. If neither binds, dumps
   the last 20 log lines and exits non-zero.

Processes are fully detached — they survive the terminal closing. Stop
them only with `dev-down.sh` (or manually via the PID files).

## How dev-down.sh works

1. Reads each PID file. Sends SIGTERM, waits 1s, escalates to SIGKILL if
   still alive. Removes the PID file.
2. Belt-and-braces: kills anything else still listening on
   `:8766`/`:3000` (handles the case where dev-up was bypassed and the
   PID file is stale or missing).

## .zshrc requirement (already configured)

The user's `~/.zshrc` should export:

```bash
export SYNTHESIS_BASE_URL=http://localhost:3000/synthesis
```

This points the user's Claude Code MCP session at the local frontend.
If a Claude Code session was open before this was added, it needs a new
shell or `source ~/.zshrc` for the var to take effect.

## When invoked from a Claude session

- **Start**: just run `dev-up.sh`. It is NOT a long-running command — it
  returns once both ports are listening (detached children continue in
  the background). Do not run it with `run_in_background: true`.
- **Stop**: run `dev-down.sh`.
- **Status**: run `dev-status.sh`.
- **"Port in use" error on startup**: run `dev-down.sh` first to clear
  stale state, then retry `dev-up.sh`.

## Overridable env vars

All three scripts honour these (defaults in parentheses):

- `COUNCIL_BACKEND_DIR`  (parent of script dir)
- `COUNCIL_FRONTEND_DIR` (`../council-clip` beside backend repo)
- `COUNCIL_BACKEND_PORT` (`8766`)
- `COUNCIL_FRONTEND_PORT` (`3000`)
