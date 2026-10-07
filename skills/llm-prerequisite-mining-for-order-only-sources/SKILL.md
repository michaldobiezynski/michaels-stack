---
name: llm-prerequisite-mining-for-order-only-sources
description: |
  Add prerequisite edges to knowledge-graph sources that only carry teaching ORDER
  (textbooks, standards documents, syllabi) using embeddings + an LLM, without
  corrupting the source-asserted graph. Use when: (1) a learning-path walk from
  university-level nodes never reaches school-level nodes because textbook sections have
  no prerequisite edges, (2) you need 'connect all X to Y' style coverage and measured
  reach stalls, (3) inferred edges must stay distinguishable and auditable. Covers
  target selection by closure test, candidate constraints (younger-than-target, exclude
  same_as peers, always include previous-in-order), cycle-guarded emit, a stronger-model
  audit that drops weak/no verdicts, and the free structural hops to try FIRST
  (term inherits section) which closed 22 points of a 34-point gap at zero cost.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# LLM prerequisite mining for order-only sources

## Problem
Curricula and textbooks give chapter order, not prerequisites. In a merged graph the
sources with real prerequisite edges (a primary taxonomy, a standards coherence map, a
formal library) do not connect to textbook sections, so 'what must I learn before X'
dead-ends at a section boundary. Reach from university topics to primary was 66%.

## Context / Trigger Conditions
- Nodes of kind section/lesson/standard with `next` edges only.
- A reachability metric (walk prerequisite ∪ same_as ∪ free hops backwards) plateaus.
- Budget exists for a few hundred LLM calls but not for hand-authoring edges.

## Solution, in cost order
1. **Free structural hops first.** A glossary term / definition inherits its
   containing section's prerequisites (term -> section as a free hop, only for
   section/lesson containers, never chapters/books). This alone took reach 66% -> 88%.
   Mirror the rule in every walker (Python and JS) and test it.
2. **Targets by closure test, not by degree.** A target is a node of an order-only
   source whose closure (with all walker rules, depth ~12) contains no primary-stage
   node. That gave 549 targets instead of the 3,300 'nodes without prerequisites'.
3. **Candidates**: top-k by embedding cosine (k=12, floor 0.55) over all sources,
   excluding the target, its same_as peers, containers/exercises, and anything with
   age_min > target.age_max (never propose something older); always append the
   previous-in-order node with a note. Batch 3 targets per call.
4. **Prompt**: 'genuine prerequisites the target builds on directly; not the same topic,
   not more advanced, not merely related; 0-4 per target with confidence and reason'.
   Store decisions per target, resumable.
5. **Emit** with its own source tag ('mine'), confidence floor 0.6, and a cycle guard:
   add edges in descending confidence, skipping any where `nx.has_path(dst, src)`
   already holds in prerequisite ∪ formal_dependency ∪ emitted edges.
6. **Audit** 80 random emitted edges with a stronger model (yes/weak/no). Observed with
   Sonnet-mined, Opus-audited maths edges: 70% yes, 22% weak, 8% no, with confidence
   0.9 all 'yes' and 0.6-0.8 mixed. Drop 'no' and 'weak' at emit time (they are not
   prerequisites even if related) and keep the tag so paths can exclude inferred edges.
7. **Bridges** for roots: for unreached foundational nodes (formal-library or
   ML-taxonomy concepts), ask the stronger model directly for at most 2 school-level
   prerequisites among younger candidates; keep as source 'bridge'. 79 roots -> 82 edges
   for ~$2.

## Verification
Re-run the reach measurement over the FULL target set with the same walker rules, never
only over the previous residue: tightening an emit filter can re-orphan nodes that were
reached through edges you just removed (eight textbooks here). Save the failing id list; the validator must still
report a DAG and one connected component; the emitted edge count minus cycle skips
minus audit drops must reconcile with the decision file.

## Notes
- Structural hops before LLM spend: subsection -> parent section (free), chapter opener
  -> previous chapter's last section, front matter -> first chapter's first section,
  back matter -> last chapter, syllabus topic chaining. These took 88% -> ~98%.
- 'Book entry' mode: preface/introduction text is generic, so retrieve candidates with
  the opener's vector blended with its successor section and exclude other books'
  prefaces, summaries and exercise sections, else the model proposes junk at 0.15-0.35.
- Sonnet-class mining cost ~16 cents per 3-target call; 549 targets ≈ $30.
- Running an Opus audit concurrently with an 8-worker Sonnet run tripped the
  subscription session limit; run them sequentially.
- Keep inferred edges out of the canonical merge guards' 'order edge' set only if you
  want same_as merging to ignore them; here they were included, which is stricter.
