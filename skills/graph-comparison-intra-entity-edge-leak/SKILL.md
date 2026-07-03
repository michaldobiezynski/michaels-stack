---
name: graph-comparison-intra-entity-edge-leak
description: |
  Silent-correctness bug pattern in cross-entity comparison tools built over
  knowledge / concept / RAG graphs. Use when: (1) building a tool like
  compare_speakers, compare_authors, compare_products, compare_candidates,
  compare_competitors, or any `*_vs_*` / `diff_*` / `versus_*` query that
  takes a set of entities plus a topic and surfaces relation edges
  (CONTRADICTS, RELATES_TO, COMPETES_WITH, ALIGNS_WITH, DISAGREES_WITH,
  SUPPORTS, DERIVES_FROM, REFUTES) between concepts; (2) the tool returns
  populated, well-formed edges but spot-checks reveal that the edges are
  intra-entity (e.g. Munger-vs-Munger when the query asked for
  Naval-vs-Munger; same author on both endpoints when the query was author-A
  versus author-B); (3) the return shape and per-entity-balanced chunk
  retrieval make the bug invisible to callers and to unit tests that only
  check `edges_non_empty`; (4) you discovered the leak by feeding a known
  intra-entity contradiction into a multi-entity comparison query and the
  tool reported it as cross-entity; (5) you are reviewing a comparison
  tool's SQL/Cypher and the WHERE clause filters edges by the topic
  concept_id but not by both endpoints' owning-entity sets. The structural
  fix is a cartesian-product filter on espousing/owning-entity sets at the
  edge layer (not just at the chunk-retrieval layer). Also covers the
  verification technique of probing a returned edge with a single-entity
  tool to confirm endpoints actually span the queried set, before accepting
  the comparison as valid.
author: Claude Code
version: 1.0.0
date: 2026-05-26
---

# Graph comparison tool: intra-entity edge leak through cross-entity query

## Problem

You build a tool that compares two or more entities on a topic by traversing
a knowledge / concept graph. The natural shape:

```
compare(entities=[A, B], topic="...", mode="comparative")
  -> {
       concept: { id, canonical_name },
       chunks: { per_entity: [...top_k each...] },
       relations: [ { source_concept, type: CONTRADICTS, target_concept }, ... ]
     }
```

You filter the chunk layer by entity (top-k per entity, gets you balanced
retrieval). You filter the relation layer by the resolved topic concept
(get all CONTRADICTS edges touching it).

You assume the relation edges describe a cross-entity tension because the
caller asked for `[A, B]`. **They don't.** Any CONTRADICTS edge that
touches the topic concept passes through, including edges where both
endpoint concepts are espoused exclusively by the same entity (intra-A or
intra-B).

The return is well-formed JSON. Chunks look balanced. Relations look
populated. The bug is invisible to the caller. Tests checking
`assert len(result.contradicts) > 0` pass.

## Context / trigger conditions

**Build-time triggers:**
- Designing a `compare_*`, `*_versus_*`, `diff_*` tool over a graph.
- Tool signature takes a list of entities (`speakers`, `authors`, `users`,
  `products`, `parties`) plus a `topic` / `concept` / `keyword`.
- Underlying graph has ownership/authorship edges (`ESPOUSES`, `HOLDS`,
  `PREFERS`, `WROTE`, `OWNS`, `STATES`) **separate** from the relation
  edges (`CONTRADICTS`, `RELATES_TO`, `COMPETES_WITH`, `ALIGNS_WITH`,
  `SUPPORTS`, `DERIVES_FROM`, `REFUTES`).
- You are tempted to filter only by the topic concept_id at the relation
  layer because that's the easy join.

**Diagnostic triggers (the bug is already live):**
- `compare_X(entities=[A, B], topic="...")` returns a populated relations
  array, but a domain expert says "those aren't actually A-vs-B".
- Spot-check via a single-entity tool (`explore_concept` / `who_espouses`
  / `get_owners`) reveals at least one returned edge has the same entity
  on both endpoints.
- Unit tests pass; integration tests pass; only narrative review catches
  the discrepancy.

**Generalised statement:** if your response shape has multiple layers
(`chunks`, `relations`, `aggregates`, `citations`) and the query carries
an entity-set scope, **every layer must be filtered by that scope**. The
bug appears when one layer (chunks) is correctly scoped and another layer
(relations) is filtered only by the topic, not by the entity scope.

## Solution

### Structural fix: cartesian-product edge filter

For each candidate edge `(source_concept, type, target_concept)` that
touched the topic, compute the espousing-entity sets:

```python
source_owners = espousing_entities(source_concept)   # set
target_owners = espousing_entities(target_concept)   # set
queried       = set(entities)                        # set
```

Keep the edge **only if both endpoints are reachable from the queried
set AND the reachable entities differ between endpoints**:

```python
src_match = source_owners & queried
tgt_match = target_owners & queried
keep = (
    src_match and tgt_match              # both endpoints touch the query
    and (src_match - tgt_match           # AND there is at least one queried
         or tgt_match - src_match)       # entity on one side that is not
)                                        # on the other (so it spans the set)
```

If both endpoints have the same single queried entity in their
intersection (`src_match == tgt_match == {A}`), the edge is intra-A;
drop it.

If one endpoint touches the queried set but the other doesn't, the edge
crosses the query boundary into a non-queried entity; this is a design
choice (keep with a flag, or drop). Defaulting to "drop and surface in
`notes`" is the safest.

### Response shape: surface the verification metadata

Add a field to each returned edge so the caller can audit the filter
without a second round-trip:

```json
{
  "source_concept": "...",
  "type": "CONTRADICTS",
  "target_concept": "...",
  "source_espoused_by": ["naval"],
  "target_espoused_by": ["munger"],
  "spans_queried_set": true
}
```

Even when the edge passes the filter, surface `*_espoused_by` so the
caller can verify visually.

### Notes field for transparency

If the filter drops edges, say so:

```json
"notes": [
  "filtered 3 of 4 candidate edges as intra-entity for queried set {naval, munger}; 1 edge spans the set"
]
```

### SQL / Cypher / KQL pattern

In LadybugDB / Kuzu / Neo4j the join needs both endpoint-side ESPOUSES
checks AND a "different queried entity per endpoint" predicate. Pseudocode:

```cypher
MATCH (c:Concept {id: $topic})-[:CONTRADICTS]-(other:Concept)
MATCH (a:Entity)-[:ESPOUSES]->(c)
MATCH (b:Entity)-[:ESPOUSES]->(other)
WHERE a.id IN $queried_entities
  AND b.id IN $queried_entities
  AND a.id <> b.id
RETURN c, other, a, b
```

Note the **`a.id <> b.id`** predicate. That single condition is the fix.

## Verification

### Single-edge probe pattern

After any cross-entity comparison returns relation edges, before reporting
the result as valid, probe one edge with a single-entity tool:

```
1. Pick the first returned edge.
2. Call explore_concept(edge.source_concept). Note its espousing entities.
3. Call explore_concept(edge.target_concept). Note its espousing entities.
4. Confirm the two espousing sets each intersect the queried entity set.
5. Confirm the intersections are not identical (i.e. the edge spans the set).
```

This is a cheap (2 extra calls), unambiguous catch. If any returned edge
fails this probe, the tool has the bug.

### Synthetic test fixture

Add an integration test with a deliberately seeded intra-entity
contradiction:

```python
# Setup
graph.add_concept("low_expectations", espoused_by=["munger"])
graph.add_concept("self_defeating_expectations", espoused_by=["munger"])
graph.add_edge("low_expectations", "CONTRADICTS", "self_defeating_expectations")

# Test
result = compare_speakers(
    topic="low expectations",
    speakers=["naval", "munger"],
    mode="comparative",
)
assert result.contradicts == []  # intra-Munger edge must be filtered
assert "filtered" in " ".join(result.notes)  # filter event surfaced
```

Without the fix, this test fails (the edge leaks).

## Example: council-of-thinkers, 2026-05-26

Discovery during Phase 2 exit-criteria validation. Proposed as
follow-up issue (`michaldobiezynski/council-of-thinkers`, sibling of
the resolved #108 fuzzy-resolution issue).

**Query:**
```
compare_speakers(
  mode="comparative",
  topic="low expectations",
  speakers=["naval", "munger"]
)
```

**Returned:**
- `concept.concept_id = "concept:low-expectations"` (resolved correctly)
- `chunks = {naval: 10, munger: 10}` (balanced as designed)
- `contradicts = [{
    source: "concept:low-expectations",
    target: "concept:self-defeating-expectations",
    type: "CONTRADICTS"
  }]`

**Probe (verification technique applied):**
```
explore_concept("concept:low-expectations")
  -> espousing_speakers: ["munger"]
explore_concept("concept:self-defeating-expectations")
  -> espousing_speakers: ["munger"]
```

Both endpoints Munger-only. The edge is intra-Munger
(his "low expectations are the first rule of a happy life" vs the
"bird bashing its wings on the cage" tension within his own corpus),
**not** a Naval-vs-Munger contradiction. The tool reported it as if
it were cross-speaker because the comparative-mode SQL filtered
CONTRADICTS edges by topic concept_id only, not by both endpoints'
ESPOUSES + queried speaker set.

## Notes

### This is a layer-scoping bug, not a graph-modelling bug

The graph is correct. The relations are correct. The bug is that the
comparison tool only applies the query's entity scope to the chunk
retrieval layer, not to the relation layer. Same shape bug can appear in:

- **Multi-tenant retrieval**: rows correctly filtered by tenant_id at the
  primary query, but joined metadata (tags, mentions, citations) bleeds
  in from other tenants.
- **ACL-filtered search**: search results correctly filtered by ACL, but
  result snippets or "related items" leak unauthorised content.
- **Time-windowed analytics**: rows correctly windowed, but aggregates
  joined across them include out-of-window data.
- **Per-user recommendation diff**: "what's new for user A vs user B" can
  surface items that are new for *neither* if the diff filter is applied
  only to one side.

The general rule: **every layer of a multi-layer response shape must be
filtered by the query's entity / tenancy / time scope, not just the
layer where the filter is cheapest.**

### Extending to N entities

The cartesian-product filter generalises. For `entities = [A, B, C, ...]`,
keep an edge iff:

```
source_owners ∩ queried != ∅
target_owners ∩ queried != ∅
(source_owners ∩ queried) ≠ (target_owners ∩ queried)
```

The last condition (`≠`, not just `∩ = ∅`) is what catches the
intra-entity case (when both intersections are the same single entity).

### Related but distinct: silent-degradation when concept doesn't resolve

If your comparison tool fuzzy-resolves the topic to a concept and you
build that, also handle the case where resolution fails. See council-of-
thinkers issue #108 for the parallel "silent degradation" pattern (free
text doesn't match a canonical concept name, tool returns chunks but no
edges, looks like a healthy result). The two bugs compound: a tool that
silently degrades on missing concepts AND silently leaks intra-entity
relations on resolved ones gives the caller no way to trust any
comparison output.

### Why naive unit tests miss this

Tests of comparison tools typically assert:
- response shape valid
- `len(chunks_per_entity) > 0` per entity
- `len(relations) >= 0`
- known-topic concept resolves to non-empty concept_id

None of those catch the leak. The test that catches it is:

```python
assert all(
    edge.source_espoused_by ∩ queried != edge.target_espoused_by ∩ queried
    for edge in result.relations
)
```

Make this assertion a standard part of cross-entity comparison test
suites.

## References

- Council-of-thinkers issue [#108](https://github.com/michaldobiezynski/council-of-thinkers/issues/108) — fuzzy concept resolution (the
  silent-degradation parallel).
- Council-of-thinkers issue [#110](https://github.com/michaldobiezynski/council-of-thinkers/issues/110) — this bug (filed 2026-05-26 during
  Phase 2 exit-criteria validation; sibling follow-up to #108).
- Related skill: `council-of-thinkers-compare-speakers-needs-resolved-concept`
  covers the concept-resolution side of the same tool family. This skill
  covers the edge-filtering side.
