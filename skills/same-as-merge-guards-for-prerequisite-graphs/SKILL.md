---
name: same-as-merge-guards-for-prerequisite-graphs
description: |
  How to collapse LLM- or embedding-derived same_as / equivalence edges into canonical
  nodes in a knowledge graph that ALSO has ordering edges (prerequisite, depends_on,
  next), without creating self-loops, cycles or merged progression steps. Use when:
  (1) union-find over same_as chains merges 'X (age 8+)' with 'X (age 9+)' or any two
  nodes that have a prerequisite edge between them, (2) transitive same_as chains drift
  into giant clusters, (3) after merging, the prerequisite projection has cycles,
  (4) you need a ranked, pruned learning path over the merged graph. Verified on a
  7-source maths curriculum graph (7,315 -> 5,513 canonical topics, 25 cycle edges).
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Guarded same_as merging for graphs with ordering edges

## Problem
Equivalence edges from an LLM/embedding alignment are locally right but globally
transitive: A=B and B=C merge A with C even when A is a prerequisite of C (curriculum
'progression variants' of the same skill), or when A and C are years apart. Naive
union-find then produces prerequisite self-loops, cycles and 50-node hairballs.

## Context / Trigger Conditions
- Nodes carry an age/level and ordering edges (prerequisite, formal_dependency, next).
- same_as edges have confidences; some sources duplicate a topic across levels.
- Symptom after merging: `nx.is_directed_acyclic_graph` false, or clusters containing
  both '(age 8+)' and '(age 9+)' variants, or a cluster spanning primary and graduate.

## Solution
Process same_as edges in descending confidence; before each union check:
1. **Order guard**: reject if any member of cluster A has an ordering edge (either
   direction, including `next`) to any member of cluster B.
2. **Level guard**: reject if merged min/max age_min spread exceeds N years (3 worked).
3. **Size cap**: reject if |A|+|B| > cap (12 worked); count rejections by reason.
4. Restrict merging to comparable kinds (topics, standards), not containers.
Then project ordering edges onto canonical ids with a `support` count (number of
source edges), drop self-loops, and break residual cycles by removing the lowest-
support edge per cycle (report the count; 25 of 4,500 was the observed scale).
Name the canonical node from a priority list of sources (native-language first).

Ranked path over the merged graph: closure = ancestors within depth; prune nodes whose
age_max < assumed mastery age; score = unlocks (descendants within closure) *
(1 + log support); take top-K; order with `nx.lexicographical_topological_sort` keyed
by (-hop, age_min) so foundations precede dependants even without a direct edge.

## Verification
Unit test with: a 3-node merge, a same_as blocked by a prerequisite edge, a same_as
blocked by age gap, a non-mergeable kind, and two source edges projecting to one
canonical edge with support 2. Rejection counts must match exactly.

## Notes
- Do NOT break cycles when loading the merged graph for ancestry/closure queries: deleting
  the weakest edges of each cycle severed ~1,200 ancestor chains here. Keep every edge;
  for ordering, condense strongly connected components (`nx.condensation`) and order
  members within a component by the same key. Depth for layouts: longest path over the
  condensation.
- Ranking learning steps by 'unlocks' picks the deepest foundations once the graph is well
  connected (algebraic notation for eigenvalues). Select CLOSEST-FIRST from the goal,
  strongest edge first, and prune by the midpoint of a topic's age band; keep unlocks and
  support as displayed info only.
- When deriving structural links to reconnect projected nodes, follow ordered and free hops
  only (never nesting) and require the source to be no older than the target, else
  'broader' neighbours and later topics become prerequisites.
- Keep a `members.jsonl` map so any raw node id resolves to its canonical id.
- Textbook `next` edges re-introduce cycles after merging across books; drop the
  weakest `next` edge per cycle at load time rather than in the build.
- A stronger-model recheck of a same_as sample gives the precision figure that sets
  the merge threshold; 0.8 was used after a 71-81% exact-label rate at 0.7.
