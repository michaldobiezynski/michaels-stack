---
name: switching-llm-mid-corpus-fragments-concept-graph
description: |
  Decide whether to switch the extraction LLM (e.g. Sonnet via `claude -p` ->
  a local model like Gemma 3 27B / Qwen3 / Mistral Small on Apple Silicon) for a
  high-volume concept/entity/relationship extraction pipeline that feeds a
  knowledge graph deduplicated by NAME. Use when: (1) a quota-bound extraction
  job (weekly `claude -p` subscription limit) keeps stalling and a local model is
  tempting to remove the wall; (2) someone proposes a cheaper/smaller model for
  "shallow structured-output" extraction; (3) part of the corpus is already
  extracted by model A and you are about to extract the rest with model B. Covers
  the non-obvious mixed-provenance fragmentation risk plus the prompt/breaker
  retuning and benchmark-on-your-own-chunks discipline. council-of-thinkers
  phase2 concept extraction, but the pattern is general.
author: Claude Code
version: 1.3.0
date: 2026-06-09
---

# Switching the extraction LLM mid-corpus fragments a name-deduped graph

## Problem
A high-volume LLM extraction pipeline (per-chunk concept/entity/relation
extraction) is bounded by a weekly subscription quota and keeps stalling, so a
local model looks attractive: no quota wall, run 24/7, zero marginal cost. The
task itself (shallow reasoning, structured tuple/JSON output) genuinely suits a
27-32B local model. But naively switching the model for the remaining corpus
silently degrades the GRAPH, because the graph dedupes nodes by NAME.

## Context / Trigger conditions
- A driver that shells out to `claude -p` (or any single model) per item and
  writes nodes/edges into a graph (Kuzu/LadybugDB, Neo4j, etc.).
- The graph node id is derived from the model's free-text output, e.g. a slug of
  `canonical_name` ("product market fit" -> `product-market-fit`).
- Part of the corpus is already extracted by model A; you intend to do the rest
  with model B (a different vendor/size/quant).
- Symptom you are trying to avoid: a fragmented graph where one real concept
  appears as several near-duplicate nodes, so traversal/synthesis quality drops.

## Solution / what to weigh

1. **Name-dedupe means the model's WORDING is part of your schema.** Model A
   writes "product market fit"; model B writes "achieving PMF" or "product/market
   fit". Different surface form -> different slug -> a SECOND node for the same
   concept. Relations and MENTIONS scatter across the duplicates and the graph's
   connective tissue frays. This is invisible in per-item logs ("writes are
   landing") and only shows up as degraded graph queries later.

2. **Frame the benefit correctly: subscription `claude -p` costs $0 cash.** The
   headline number (e.g. "~$1k") is QUOTA-equivalent, not money out of pocket.
   Going local does not save cash; it removes the WEEKLY QUOTA WALL so the
   backlog runs continuously instead of stop-start over weeks. Real benefit, but
   say what it actually is.

3. **The prompt + safety machinery is tuned to the incumbent model.** Tuple/JSON
   format adherence, gleaning-retry (re-ask on zero parseable output), and any
   retry-rate circuit breaker were calibrated against model A (e.g. a measured
   ~0% retry rate). Model B's adherence differs - often a much higher
   no-parseable-output rate that trips the breaker constantly until you re-tune
   the prompt and parser. Budget ~1-2 days of integration: swap the subprocess
   call, re-tune prompt, re-validate parsing, re-calibrate the breaker.

4. **A vendor-exclusion constraint can remove the BEST tool for this exact job.**
   For structured extraction the strongest open-weight models are often the ones
   a "no Chinese models" rule excludes (Qwen3, DeepSeek). Be explicit that the
   constraint costs quality on the dimension that matters most here (JSON/tuple
   reliability), and name the best allowed comparator (e.g. Gemma 3 27B vs
   Mistral Small ~24B on Apple Silicon).

5. **Recommended pattern: split by VALUE, don't wholesale-swap.**
   - Keep the strong cloud model for the HIGH-value subset (the content that IS
     the product) so it stays consistent with what is already extracted.
   - Trial the local model on the LOW-value, high-volume subset (e.g. an
     interview HOST's question/segue chunks) - lowest quality sensitivity,
     biggest quota sink, least entangled with the valuable concept web.
   - If you must mix, turn ON canonicalisation (embedding-similarity + arbitration
     merge) so model B's variant names map onto model A's existing nodes instead
     of forking new ones.

6. **Benchmark on YOUR chunks before committing - aggregate scores won't tell
   you.** Run ~30-50 representative items through model A vs model B and compare:
   concept count, NAMING CONSISTENCY against existing graph nodes, relation
   quality, parse/retry rate, and measured tok/s on the actual hardware
   (Apple-Silicon inference benchmarks for a given model/quant are scarce; do not
   trust remembered tok/s). Quant degradation varies by task and can exceed the
   headline few-percent on specialised passes.

## Verification
- Benchmark table exists with the 5 metrics above on your own sample.
- If mixing models, query the graph for near-duplicate concept names after a
  model-B batch (e.g. fuzzy-match canonical_names / embedding cosine) and confirm
  the duplicate rate did not jump versus a model-A-only baseline.

## Empirical anchor (measured 2026-06-08, council-of-thinkers)
qwen3:32b (Ollama, local) vs Sonnet-4.6 on 50 already-extracted chunks, compared
against Sonnet's canonical names IN THE GRAPH (read-only, nothing written):
- Concepts/chunk: Sonnet 4.4, qwen 4.2 (equal volume).
- Format adherence: 50/50 produced parseable tuples, 0 zero-concept, 0 markdown
  fences with thinking OFF -> the local model followed the tuple grammar fine;
  the gleaning-retry/circuit-breaker fear was unfounded for this model.
- EXACT name overlap: 3% (7/222). LOOSE (separator-insensitive) overlap: 21%.
  The 18-point gap was almost entirely ONE convention: the prompt said
  "hyphen-or-space separated", Sonnet chose spaces ("quantum computation"),
  qwen chose hyphens ("quantum-computation"), and the name-normaliser did not
  unify them -> near-total fragmentation despite the models AGREEING on the
  concept. Side-by-side reading showed true semantic agreement even higher than
  the 21% loose floor (e.g. "time-reversibility" vs "time-reversal symmetry"
  are the same idea but don't even loose-match).
- LESSON: exact-string overlap on the DISPLAY NAME drastically UNDERSTATES a
  challenger model's quality AND can measure the wrong thing entirely. FIRST find
  the graph's actual DEDUP KEY and compare on THAT. In council-of-thinkers the
  dedup key is `concept_id = _concept_id_from_name(name)`, which slugs the name by
  replacing every run of non-alphanumeric chars (spaces AND hyphens) with a single
  hyphen -- so "quantum computation" and "quantum-computation" yield the IDENTICAL
  concept_id and DO NOT fragment. The "3% exact overlap" was an artifact of
  comparing canonical_name display strings instead of the slug; the real merge
  rate equalled the ~21% loose figure. Verify in 2 lines:
  `_concept_id_from_name("a b")==_concept_id_from_name("a-b")` before assuming a
  separator problem exists.
- DO NOT "fix the separator" if your dedup key is already a separator-collapsing
  slug -- it is a no-op (the case here). The residual gap (loose ~21%, not higher)
  is PURE PHRASING variation ("time-reversibility" vs "time-reversal symmetry"),
  which only embedding CANONICALISATION merges. This phrasing drift happens even
  between two runs of the SAME model, so a deterministic-slug graph is already
  mildly fragmented; canonicalisation is the right move for any high-volume
  extraction, model-switch or not. Compute overlap THREE ways to locate the real
  gap: (a) dedup-key (true fragmentation), (b) loose/separator-insensitive,
  (c) embedding-semantic (true comprehension).
- SPEED: thinking ON was ~127s/chunk (~1000h for ~29k chunks - a non-starter);
  thinking OFF was ~22s/chunk at ~13 tok/s (~180h continuous, no quota wall).
  For high-volume bulk extraction, run the local model with thinking OFF; a
  reasoning model's thinking tokens make it ~6x slower for no format benefit
  here. Disable via Ollama top-level `"think": false`.
- A NEWER/LARGER local model + thinking did NOT close the gap. qwen3.6:35b
  (newer-gen MoE) WITH thinking scored raw 68% / merged 58% / dedup 30% -
  ~1-2 points over qwen3:32b's 66/57/23, i.e. WITHIN NOISE, at 4x the wall-time
  (~93s vs ~22s/chunk; thinking emitted ~3540 tok/chunk). LESSON: a ~60-66% recall
  gap to a frontier cloud model is usually the CLOUD MODEL'S BAR, not something a
  bigger local model or thinking-on will fix; don't burn days chasing local
  parity. The genuinely stronger tier (e.g. a 122B-A10B MoE, ~70GB Q4) overflows
  64GB unified memory, so on a 64GB Mac there is no local model that both fits AND
  clearly beats a ~32B dense for this task.
- THINKING-ON CAN HURT STRUCTURED OUTPUT. qwen3.6 thinking-on had a 5%
  zero-concept rate (vs 0% thinking-off): it emitted valid-looking tuples that the
  format parser REJECTED (a phrasing/format quirk surfaced by the reasoning pass).
  So thinking is doubly bad for bulk structured extraction: slower AND less
  parse-reliable. Set num_predict generously when testing thinking (cap = thinking
  + output combined; verify no per-call count clusters at the cap), but prefer
  thinking OFF for the real run.
- HARNESS: scripts/benchmark_local_extract.py (read-only) - reuses the pipeline's
  own _system_prompt + _parse_tuples so it tests the EXACT contract, reads
  "what model A did" from the graph (no quota needed), and reports exact/loose
  overlap, format adherence, and tok/s.

## Notes
- The local-model task fit is real: per-chunk extraction is shallow + structured,
  so throughput and output-format reliability beat frontier reasoning here.
- Related: `resumable-llm-batch-incremental-write` (the quota wall this is trying
  to escape, and the per-entity-filter ordering trick) and
  `claude-p-subscription-subprocess`.
- Cost/throughput anchor: `claude -p` Sonnet concept extraction measured
  ~$0.02-0.03 per chunk (quota-equivalent), ~14s/chunk x6 workers; a 27B local
  model may be SLOWER per chunk but finishes sooner overall by never stalling on
  quota.
