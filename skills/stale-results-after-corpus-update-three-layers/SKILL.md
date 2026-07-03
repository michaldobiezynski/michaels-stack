---
name: stale-results-after-corpus-update-three-layers
description: |
  Diagnose "I fixed/updated the corpus but the client still returns old
  results" for a locally-updated dataset served remotely (council-of-thinkers:
  local LanceDB/graph -> push_to_fly -> Fly box -> claude.ai MCP connector; the
  pattern generalises to any local-build/remote-serve RAG). Use when: (1) a
  data fix is verified locally but claude.ai (or another remote client) still
  cites old timestamps/rows, (2) the SAME second-ranges/values reappear
  verbatim in a "new" answer, (3) a corpus push claims success yet results look
  unchanged. Check three layers IN ORDER: client conversation reuse, remote
  copy staleness, actual served data. Includes the LanceDB fragment-filename
  identity proof and the slim-VM OOM probe trap.
author: Claude Code
version: 1.0.0
date: 2026-07-03
---

# Stale results after a corpus update: three layers, in order

## Problem

You update/repair data locally, verify it locally, ship it, and the end client
still returns pre-fix results. Everyone's instinct is "the fix didn't work" or
"the deploy failed", and it is easy to burn an hour probing the wrong layer.

## The three layers (check cheapest-first)

1. **Client conversation reuse.** LLM clients (claude.ai etc.) keep earlier
   TOOL RESULTS in the conversation; a follow-up question is often answered
   from that context WITHOUT fresh tool calls. Smoking gun: the "new" answer
   repeats the old evidence VERBATIM (identical second-ranges, identical ids).
   Test: ask again in a BRAND-NEW conversation, phrased to force retrieval
   ("search the corpus for ... and cite clips").
2. **Remote copy staleness.** The serving box holds a COPY shipped by a push
   job. Check the push actually ran: council's `push_to_fly.sh` silently
   SKIPS whenever `graph_writer_active` pgrep-matches `council_mcp.server` —
   which includes IDLE MCP servers spawned by any open Claude Code session
   (issue #264), so day-old corpora are common. Read the daily log, don't
   assume.
3. **Actual served data.** Only after 1-2, verify bytes on the box.

## Byte-level data-identity proof (no queries, no auth, no OOM)

LanceDB fragment files are content-addressed and manifests are monotonically
versioned. If the remote table has the SAME newest fragment filenames and the
SAME latest `_versions/*.manifest` as local, the data is identical:

```bash
ls -t lancedb/council/chunks.lance/data/ | head -3           # local
fly ssh console -a <app> -C "ls /data/lancedb/council/chunks.lance/data/<frag>"
ls lancedb/council/chunks.lance/_versions/ | sort -t. -k1 -n | tail -1
fly ssh console -a <app> -C "sh -c 'ls /data/.../_versions/ | sort -t. -k1 -n | tail -1'"
```

## Probe traps on a slim serving VM

- Opening the LanceDB table from a SECOND python process next to the running
  server OOM-kills (native crash dump, `Process exited with status
  4294967295`) — even for "light" indexed queries. Don't probe by opening the
  table; use the fragment/manifest compare above.
- `curl` is absent from slim images; use `python3 -c` + urllib.
- Localhost JSON-RPC still 401s when an OAuth proxy fronts the app; the
  static admin token does not pass the OAuth path. Don't fight it — the
  fragment compare needs no auth.

## Verification

After the fragment match confirms layer 3 is fine, a fresh client
conversation returning the new ids/timestamps confirms layer 1 was the cause
(observed: exact case 2026-07-03 — fragments identical, fresh claude.ai chat
returned correct v2 clips).
