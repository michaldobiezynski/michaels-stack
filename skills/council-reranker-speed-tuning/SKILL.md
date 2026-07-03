---
name: council-reranker-speed-tuning
description: |
  Speed up slow council-of-thinkers queries (query_speaker ~2.5s, query_council
  ~6-10s warm). The bottleneck is the cross-encoder reranker (BAAI/bge-reranker-v2-m3)
  scoring top_k*RERANK_OVERFETCH candidates per query, lock-serialised so concurrent
  queries queue. Use when: queries feel slow, a bulk sweep over many speakers drags,
  or someone asks to speed up retrieval/rerank. Covers the env knobs already exposed
  in council_mcp/rerank.py (RERANK_OVERFETCH, RERANK_DTYPE, RERANK_MODEL, RERANK_ENABLE,
  RERANK_BATCH_SIZE, RERANK_MAX_LENGTH), the measured 3.6x safe win, the benchmark
  method, and the "overlap != quality" / "max_length is not a lever here" gotchas.
author: Claude Code
version: 1.0.0
date: 2026-06-19
---

# Council reranker speed tuning (measured)

## Problem

Council queries are slow: warm `query_speaker` ~2.5s, `query_council` ~6-10s. The
cost is the Phase-1 cross-encoder reranker, not the LanceDB search (which is fast,
especially after the chunks table is compacted).

## Why it's slow (verified)

- Per query: `embed_query` (Voyage AI network, ~200ms, charged once) → hybrid
  BM25+dense search → **cross-encoder reranks `top_k * RERANK_OVERFETCH` candidates**
  (default overfetch 10, so top_k=5 reranks 50, then slices to 5). Rerank dominates.
- Cross-encoder latency is ~linear in candidate count and ~quadratic in sequence
  length. `bge-reranker-v2-m3` is a 560M multilingual XLM-R-large; the corpus is English.
- `_LockedCrossEncoder` in `council_mcp/rerank.py` holds a class-level lock around
  `.predict`, so concurrent requests SERIALISE (threads don't help; the model isn't
  thread-safe). A 28-query sweep runs back-to-back, not in parallel.

## Solution — env knobs already exposed (no code change)

All read in `council_mcp/rerank.py`; set them where the backend launches
(`scripts/dev-up.sh:40` for local dev). **Measured on M-series, 2026-06-19:**

- **`RERANK_OVERFETCH=4`** (from 10): reranks ~20 not ~50. **Biggest safe win.**
- **`RERANK_DTYPE=fp16`** (keep device mps): added ~1.4x here (more than the generic
  "fp16 is negligible on MPS" advice predicted — measure, don't assume).
- Together: **6.5s avg → 1.8s (~3.6x)**, same model. `query_speaker` returned the
  **identical top-5** (lossless); `query_council` overlap dropped to ~0.62-0.88 (broad
  search draws candidates from the whole corpus, so a smaller pool costs more recall).
- **`RERANK_ENABLE=0`** for breadth ("who even mentions X") → sub-second, hybrid-only.
- **`RERANK_MODEL=BAAI/bge-reranker-base`** (278M) → ~9x (0.7s); `cross-encoder/ms-marco-MiniLM-L12-v2`
  (~33M) → ~10x (0.65s). BUT both change rankings materially (overlap 0.12-0.8 vs the
  big model). Do NOT adopt blind — see gotcha.
- `RERANK_BATCH_SIZE` (default 32), `COUNCIL_WARM_RERANK=1` (hide cold model load),
  `RERANK_DEVICE`, `RERANK_MIN_SCORE` also exist.

## Gotchas

- **`max_length` is NOT a lever here.** Chunks are median ~370 tokens (p99 392, max 496);
  `RERANK_MAX_LENGTH=256` would truncate ~96% of them. Leave it at 512. Check
  `token_count` in the chunks table before ever lowering it.
- **Overlap with the big model is NOT quality.** A smaller model's lower overlap means
  "ranks differently", which could be different-but-fine OR worse. You cannot tell
  without relevance labels. So `OVERFETCH`/`fp16` (same model) is provably safe; a model
  swap needs a real relevance eval first.
- **Measured 2026-06-19 (eval/rerank_relevance.py, Sonnet-judged nDCG):** overlap was
  MISLEADING; settle it with the eval, not overlap. n=18 (easy "head" queries) gave a
  NOISY result (minilm best, reranking +5%). Expanding to **n=50 with harder/sparser
  queries reversed it**: nDCG@10 hybrid 0.776, bge-v2-m3 0.774, minilm 0.761, bge-base
  0.751, and a **paired bootstrap (10k, 95% CI) found EVERY pairwise difference
  non-significant** including no-rerank-vs-rerank (hybrid - bge_v2_m3 = +0.002
  [-0.037, +0.038]). So: (a) MiniLM (~10x faster) is statistically tied with the big
  model -> model choice does not affect relevance; (b) the cross-encoder shows **no
  measurable nDCG benefit over pure hybrid** on this corpus, so the real lever is
  whether to rerank AT ALL, not which model. CAVEAT: the judged pool was ~78% relevant
  and the 0-3 judge is coarse, so the metric UNDER-credits the reranker (which earns its
  keep on precision@1 / near-duplicate distractors); "no measured benefit" != "no
  benefit". Validate rerank-off with a precision@1 hard-negative eval before flipping it.
  Lesson: always run a paired significance test (per-query nDCG bootstrap) before
  acting on small nDCG gaps; n=18 lied, n=50 with a CI told the truth.
- **BUT the nDCG eval UNDER-CREDITED the reranker (its pool was too easy).** A second
  eval (eval/rerank_value.py, 2026-06-19) tests reranker VALUE properly: known-item
  retrieval with claude -p-PARAPHRASED queries (lexically distant from the gold chunk,
  so first-stage hybrid surfaces lookalikes = hard negatives), scored by the gold
  chunk's RANK (deterministic, no judge). Hardness gate: hybrid ranks gold #1 only 28%
  of the time = genuinely hard. Result (n=71): the BIG bge-v2-m3 reranker LIFTS P@1
  0.28->0.42 (+50% rel) and MRR +18% over no-rerank (borderline sig, 95% CI [-0.014,
  +0.189]); **MiniLM does NOT help and HURTS recall@20 (0.87->0.77)** - it demotes
  correct answers below rank 20. So: (1) reranking DOES earn its keep on hard queries;
  do NOT turn it off; (2) MiniLM is NOT equivalent to the big model once queries are
  hard - the "all tied / free 10x" reading was an artifact of the easy nDCG pool. KEEP
  bge-v2-m3 + overfetch4 + fp16 (current prod). META-LESSON: an eval only reveals a
  reranker's value if its queries are hard enough (low hybrid-#1 rate); build the
  hardness gate into the eval and report it.
- **Concurrency won't speed a bulk sweep** (the predict lock). Run ONE `query_council`
  instead of N `query_speaker`, or set `RERANK_ENABLE=0` for the sweep.
- Stock LanceDB `CrossEncoderReranker` forwards none of batch_size/max_length/dtype,
  but this repo already subclassed it (`_LockedCrossEncoder`) to thread them through env.

## Verification

After `dev-down.sh && dev-up.sh`, time a warm query via the HTTP MCP helper:
`query_speaker` should be ~1.2s (was ~2.5s). Revert with
`RERANK_OVERFETCH=10 RERANK_DTYPE= bash scripts/dev-up.sh`.

## Benchmark method (reusable)

For each config: kill `:8766`, `Popen` the backend with the config's env, wait for
`initialize` to succeed, run ONE warm-up query (lazy model load/download), then time N
fixed queries ×3 and record the **top-k chunk_ids**. Compare configs on (a) median
latency and (b) top-k id overlap vs baseline as a quality gate. Restart `dev-up.sh` at
the end (the loop leaves the backend on the last config).

## Notes

- Relabel/extraction and the MCP server contend on the LadybugDB graph lock, but pure
  rerank tuning only restarts the read-only backend, so no lock dance is needed.
- Related: `council-mcp-over-http-and-ladybug-writer-lock`,
  `lancedb-launchd-fd-exhaustion-compaction` (compaction already sped the search step),
  `ort-apple-silicon-kleidiai-leak-coreml-fix` (if you pursue ONNX+CoreML for the next ~2x).
