---
name: rag-hoist-query-embedding-out-of-per-entity-fanout
description: |
  Performance fix for RAG/retrieval systems that run a "balanced" or
  per-entity fan-out (one filtered search per speaker / tenant / category /
  shard) and re-embed the SAME query text inside the loop. The paid query
  embedding then scales linearly with the number of entities. Use when:
  (1) a balanced/round-robin retrieval loops over N entities calling a
  hybrid/vector search that internally calls embed_query(query) each
  iteration; (2) adding many entities (e.g. enrolling ~200 speakers) silently
  multiplies embedding API cost/latency per request; (3) a code review flags
  "embeds once per entity" or a cost regression appears with no logic change,
  only data growth. Fix: embed once, thread the precomputed vector into the
  search via an optional query_vector param.
author: Claude Code
version: 1.0.0
date: 2026-06-05
---

# Hoist the query embedding out of a per-entity retrieval fan-out

## Problem
A "balanced" retrieval runs one filtered search per entity (per speaker, tenant,
category, index shard) and merges the results, so a high-volume entity cannot
crowd out a low-volume one. If the per-entity search embeds the query itself,
the SAME query text is embedded once per entity. The cost is invisible at small
N and explodes as entities grow (e.g. 4 -> ~200 speakers = ~50x paid embedding
round-trips per request), purely from a data change, with no code change.

## Context / Trigger Conditions
- A loop like `for sid in entities: rows = hybrid_search(query, k, sid)` where
  `hybrid_search` calls `embed_query(query)` internally.
- A paid embedder (Voyage, OpenAI, Cohere) where each call is a network
  round-trip and a billable unit.
- Adding entities (enrolment, multi-tenant onboarding, sharding) regresses
  latency/cost with no logic change.
- A reviewer notes "re-embeds the query per speaker/entity".

## Solution
The query vector is independent of the per-entity FILTER, so compute it once and
reuse it:

1. Add an optional `query_vector` param to the search function; use it when
   given, else embed:
   ```python
   def hybrid_search(query, k, entity_id, *, query_vector=None):
       qv = query_vector if query_vector is not None else embed_query(query)
       return table.search(query_type="hybrid").vector(qv).text(query)...
   ```
2. Embed once in the fan-out, pass it into every call:
   ```python
   qvec = embed_query(query)
   for eid in entities:
       rows = hybrid_search(query, k, eid, query_vector=qvec)
   ```
This is backward compatible (default `None` preserves all existing callers and
results: the vector is identical to what the function would have computed).

Safe because: a query embedding is deterministic for a (text, model) pair, and
the vector is read-only once passed to the vector index (`.vector(qv)`), so
sharing one object across calls is correct. (If callers might mutate it, return
/ pass a copy, or use a bounded LRU cache on `embed_query` keyed by text.)

## Verification
- Unit test: monkeypatch `embed_query` to count calls and the search to record
  the `query_vector` it received; assert the fan-out calls `embed_query` exactly
  once and hands the same vector to every per-entity search.
- Results are unchanged (same vector), so existing retrieval tests still pass;
  add the count assertion as a regression guard.

## Notes
- The same trap hides in any "do X per entity" loop that recomputes a
  per-request-constant input: embeddings, auth tokens, compiled queries,
  rerankers. Hoist the request-constant work above the loop.
- Text-keyed `functools.lru_cache(maxsize=...)` on `embed_query` fixes ALL
  fan-out callers at once, but is process-global and returns a shared mutable
  list; the explicit `query_vector` thread is more surgical and review-friendly.
- This is a data-scale regression: it does not show up until the entity count
  grows, so guard it with a test, not just a one-off fix.
