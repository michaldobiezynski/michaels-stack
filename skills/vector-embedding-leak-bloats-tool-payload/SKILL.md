---
name: vector-embedding-leak-bloats-tool-payload
description: |
  Fix for an MCP tool / API endpoint over a vector store (LanceDB, pgvector,
  Pinecone, Qdrant, Chroma, etc.) whose result is enormous or "exceeds the
  maximum allowed tokens" even though it returns only a handful of rows. Use
  when: (1) one tool/endpoint returns hundreds of KB for ~10-20 records and
  spills to a file or blows the LLM tool-output token cap, while a SIBLING
  tool over the same store returns small results; (2) a chunk/record dict in
  the response carries fields like dense_vector / embedding / vector /
  text_for_embedding / embedding_model_version / _relevance_score; (3) the
  transcript-text field name is inconsistent across tools (raw_text in one,
  text in another) and one tool omits the citation/clip url. Root cause: that
  tool returns RAW store rows (every column, including the ~1-21 KB embedding)
  instead of routing through the shared lean projection the other tools use.
author: Claude Code
version: 1.0.0
date: 2026-06-09
---

# Embedding columns leaking into an LLM-facing tool payload

## Problem
A tool or API backed by a vector store returns a giant payload (hundreds of
KB) for only a few rows, overflowing the model's tool-output token cap (the
result gets spilled to a file, or the call fails). The culprit is almost never
the text — it is the **raw embedding vector** being serialised into every
record. A 1024-dim float vector is ~21 KB as JSON; 20 rows = ~440 KB of pure
noise the model can never use.

## Context / Trigger conditions
- "Output too large / exceeds maximum allowed tokens" on ONE tool while
  sibling tools over the same corpus are fine.
- Inspecting a record shows fields such as: `dense_vector`, `embedding`,
  `vector`, `text_for_embedding`, `embedding_model_version`, `token_count`,
  `_relevance_score`, internal `attribution_*` / `ingest_version` columns.
- Field-name drift between tools: e.g. transcript text under `raw_text` in the
  bloated tool but `text` in the others; the bloated tool also lacks the
  citation/clip URL the others include — a tell that it bypasses the shared
  projector.
- The bloated tool was written to return `search.to_list()` / raw ORM rows
  directly, e.g. `"chunks": rows` instead of `"chunks": [project(r) for r in rows]`.

## Solution
1. **Find the shared projection.** Most codebases already have ONE canonical
   "row -> citation-ready dict" helper (e.g. `_project_chunk`) used by the
   healthy tools. Grep for the field names the good tools return (`clip_url`,
   `text`) to locate it. Do NOT invent a second projector.
2. **Route the bloated tool through it.** Change `"chunks": rows` to
   `"chunks": [project_chunk(r) for r in rows]` at every return site of the
   offending impl (there are often two: a primary and a variant, e.g.
   comparative + cross-reference modes).
3. **Verify the projector never emits the heavy fields** — it should return an
   explicit allow-list of keys, never `dense_vector`/`text_for_embedding`/
   `embedding_model_version`/`raw_text`. Prefer `text` (aliased from the raw
   column) + the citation/clip url so the shape matches sibling tools.
4. **Find the one coupled consumer.** A downstream builder may read the RAW
   field names (`speaker_name`/`raw_text`/`_score`) from the now-projected
   output. Realign it (e.g. flip a `projected=False` flag to `True`, fix
   `.get("speaker_name")` -> `.get("speaker")`) and update its test fixtures.
5. **Make the projector tolerant of partial rows** (`.get(col, default)` with
   coercion like `float(row.get("ts") or 0.0)`) so the many minimal test stubs
   don't `KeyError` — real store rows always carry every column, so their
   output is byte-identical; only stubs benefit.
6. **Note**: scan-time column projection (only `.select()`-ing needed columns
   so the engine never materialises the vector) is a SEPARATE, complementary
   fix for performance; this skill is about not RETURNING the vector in the
   response. Do both.

## Verification
- Add a test that feeds a HEAVY row (with `dense_vector`, `text_for_embedding`,
  etc.) through the impl and asserts those keys are ABSENT from each returned
  record and that `text` + the clip/citation url ARE present. Cover every
  projection branch (e.g. both compare modes), not just one.
- `len(json.dumps(result))` for a 20-row result should drop from hundreds of KB
  to a few KB.

## Example
`compare_speakers` returned ~534 KB for 20 chunks because each chunk carried a
~21 KB `dense_vector` (+ `text_for_embedding`, `embedding_model_version`,
`raw_text`) and omitted `text`/`clip_url`. A `_project_chunk` helper already
existed and was used by `query_council`/`query_speaker`/`query_channel`;
`compare_speakers`/`cross_reference` just bypassed it. Routing both impls
through it, flipping the one coupled `build_debate` consumer to the projected
shape, and adding a leanness test fixed it — payload dropped ~95%, sibling-tool
parity restored.

## Notes
- The smell test: "the tool succeeded and the data is internally consistent"
  is NOT "the payload is reasonable". A success that overflows the cap is still
  a bug.
- Watch for field-name drift as a leading indicator that a tool skipped the
  shared projector — fix the inconsistency at the same time (one field name for
  text across all tools; always include the citation url).
- Raising the client output-token cap (e.g. `MAX_MCP_OUTPUT_TOKENS` for Claude
  Code) treats the symptom; the projection is the real fix. Avoid silent
  server-side truncation of result rows (it reads as "covered everything").
- Related: a column-projection-during-scan skill addresses the perf half (never
  materialise the vector); this one addresses the payload/contract half.
