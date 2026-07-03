---
name: council-of-thinkers-compare-speakers-needs-resolved-concept
description: |
  Council-of-thinkers concept-graph workflow + gotchas for the
  compare_speakers / explore_concept / explore_speaker MCP tools. Use
  when: (1) `mcp__council-of-thinkers__compare_speakers` returns an empty
  `contradicts: []` (comparative mode) or `path.kind: "disconnected"`
  (cross_reference mode) and you expected edges, (2) the response shows
  `concept.concept_id: ""` and a `notes` entry like "topic 'X' did not
  resolve to any concept in the graph; chunk results may still be
  useful", (3) you passed a free-text topic such as "risk" instead of a
  canonical concept name, (4) you want CONTRADICTS edges or a structural
  path between two speakers' concepts, (5) you need to interpret whether
  a returned CONTRADICTS edge actually represents a clash BETWEEN the two
  speakers queried. Root cause: these tools resolve `topic` against
  Concept.canonical_name then aliases; unresolved free text silently
  degrades to chunk-only retrieval while still returning balanced
  per-speaker chunks, so the call LOOKS successful. Fix: discover real
  concept names via explore_speaker, confirm edges via explore_concept,
  then call compare_speakers with the canonical name. Also covers the
  ~525K-char output spilling to a tool-results file (extract with jq) and
  the concept_count-vs-strength-vs-chunk-count distinction. Does NOT
  cover the synthesis JSON/share-url issues (separate skills).
author: Claude Code
version: 1.1.0
date: 2026-05-26
---

# Council compare_speakers: resolve the concept before expecting edges

## Problem

`compare_speakers` looks like it worked but returns no graph edges:

- `mode="comparative"` → `contradicts: []` (zero edges)
- `mode="cross_reference"` → `path.kind: "disconnected"`

…even though per-speaker chunks came back fine. The graph layer is dark
because the `topic` never resolved to a concept node.

## Context / trigger conditions

- The response contains `concept.concept_id: ""` (or `concept_a`/
  `concept_b` with empty `concept_id` in cross_reference).
- `notes` contains `"topic 'X' did not resolve to any concept in the
  graph; chunk results may still be useful"` (comparative) or
  `"topic_a/topic_b 'X' did not resolve to any concept"` (cross_reference).
- You passed free text (e.g. `"risk"`, `"leverage and luck"`) rather than
  a canonical concept name.
- `speaker_a.chunks` and `speaker_b.chunks` are still populated (usually a
  balanced `top_k` each), which masks the failure.

## Solution

The graph tools resolve `topic` against `Concept.canonical_name` first,
then against each concept's `aliases`. Free text that matches neither
yields the empty/disconnected result above. To get edges, feed a name
that exists in the graph:

1. **Discover valid concept names** with `explore_speaker`:

   ```
   explore_speaker(speaker_id="munger", top_n=50)
   ```

   Returns `top_concepts_overall` (each with `concept_id`,
   `canonical_name`, `domain`, `strength`) and an `observed_domains`
   rollup. If the response has **no** `notes` field, the graph IS
   populated for that speaker. (A `notes` field means concept extraction
   has not been run; fall back to `query_speaker` for chunk-level work.)

2. **Confirm a concept actually has edges** with `explore_concept`, using
   a small `top_n` so you don't pull 20 sample chunks you don't need:

   ```
   explore_concept(canonical_name="low expectations", top_n=1)
   ```

   Read its `contradicts`, `related_concepts`, `parent_concepts`,
   `sub_concepts`, and `espousing_speakers`. Pick the concept with the
   edges you want.

3. **Call compare_speakers with the canonical name**:

   ```
   compare_speakers(mode="comparative", speaker_a="naval",
                    speaker_b="munger", topic="low expectations")
   ```

   Now `concept.concept_id` is non-empty, `notes` is `[]`, and
   `contradicts` is populated.

### #110 auto-filters edges to genuine cross-speaker tension

As of commit `26306ed` (#110), comparative mode applies a
**cartesian-product filter**: it returns only CONTRADICTS edges that
genuinely *span* the queried pair, and accounts for the rest in `notes`.
You no longer hand-check espousers for surviving edges — the tool does it:

- A **surviving** edge carries `topic_espoused_by`, `other_espoused_by`,
  and `spans_queried_set: true`. Its endpoints are espoused by *different*
  speakers across the pair — a real cross-speaker clash.
- **Dropped** edges appear only as counts in `notes`:
  - `"filtered N CONTRADICTS edge(s) with identical espousing-speakers
    across the queried pair {a, b} (no asymmetry …)"` → intra-entity
    (both endpoints espoused by the same single queried speaker, e.g.
    `low-expectations ↔ self-defeating-expectations`, both Munger).
  - `"filtered M boundary-crossing CONTRADICTS edge(s) (at least one
    endpoint outside queried set {a, b})"` → an endpoint is espoused by a
    speaker *outside* the pair.

**Empty `contradicts` + a "filtered …" note** means edges exist but none
span *this* pair. Two different rescues, depending on the note:

- A **boundary-crossing** drop CAN be rescued by re-running with the pair
  that includes the outside speaker (e.g. `{naval, munger}` →
  `{munger, sutherland}`).
- A **non-resolution** note (`"… did not resolve to any concept"`) CANNOT
  be rescued by swapping speakers — resolution happens *before* the
  speaker filter, so an unresolved topic stays unresolved for every pair.
  Fix the concept name instead (see Solution). Note also that everyday
  domain words ("behavioural economics", "risk") are usually *domain*
  labels, not concept `canonical_name`s, so they will not resolve.

(Pre-#110 the tool returned raw edges and the caller had to check
`espousing_speakers` by hand; that manual step is now unnecessary for
surviving edges.)

### Other gotchas

- **Balanced chunks mean nothing.** `compare_speakers` returns a balanced
  `top_k` per speaker (e.g. 10/10) regardless of whether the concept
  resolved or how relevant it is to each speaker. Do not read relevance
  into the counts.
- **Big output spills to a file.** `compare_speakers` output is ~525K
  chars and is saved to a `tool-results/*.txt` file instead of returned
  inline. Extract only what you need with `jq`, in **separate**
  expressions:

  ```bash
  jq -c '{mode, topic, concept}' "$F"
  jq -c '{a:.speaker_a.speaker_id, a_chunks:(.speaker_a.chunks|length),
          b:.speaker_b.speaker_id, b_chunks:(.speaker_b.chunks|length)}' "$F"
  jq -c '.contradicts' "$F"
  jq -c '.notes' "$F"
  ```

  Beware the jq object-construction trap: `{k: (.x | keys?)}` collapses
  the WHOLE object to *no output* when the inner stream is empty (e.g.
  `.contradicts[0] | keys?` on an empty array). Keep risky sub-queries in
  their own `jq` call.

- **Two count fields, neither is chunk count.** `explore_speaker`'s
  `observed_domains[].concept_count` = number of distinct concepts in
  that domain; per-concept `strength` = ESPOUSES/mention weight. There is
  **no** chunk-count field — use `query_speaker` for chunk-level counts.
  The two rankings can diverge sharply (e.g. a domain with one
  high-strength concept outranks, by strength, a domain with several weak
  ones).

## Verification

A resolved call shows all three:

```json
"concept": { "concept_id": "concept:low-expectations",
             "canonical_name": "low expectations", "aliases": [] },
"notes": [],
"contradicts": [ { "concept_id": "concept:self-defeating-expectations",
                   "canonical_name": "self-defeating expectations",
                   "evidence_chunk_id": "Yahoo Finance:8RxLj9OVqLo#0055" } ]
```

Non-empty `concept_id` + empty `notes` = the topic resolved.

## Example (verified 2026-05-26)

Goal: find CONTRADICTS edges for a Munger concept via Naval/Munger compare.

- `explore_speaker("munger")` → candidate concepts incl. `low
  expectations` (psychology, strength 7), `innate talent ceiling`,
  `macro epistemic humility`.
- `explore_concept` on each (`top_n=1`): `low expectations` → **1**
  contradicts edge; the other two → **0**.
- `compare_speakers(comparative, naval, munger, topic="low expectations")`
  → `concept_id="concept:low-expectations"`, `notes=[]`, chunks 10/10,
  `contradicts=[low-expectations ⟷ self-defeating-expectations]`.
- Followed up: `explore_concept("self-defeating expectations")` →
  `espousing_speakers=[munger]`. So the edge is **intra-Munger**, not a
  Naval-vs-Munger clash. (Contrast: free-text `"risk"` the same day gave
  `concept_id=""`, `notes=["… did not resolve …"]`, `contradicts=[]`.)

## Notes

- The concept graph is populated per speaker but only with concepts that
  the extraction pass actually produced; everyday words ("risk",
  "leverage") often are NOT canonical concept names. Always discover
  names via `explore_speaker`/`explore_concept` rather than guessing.
- `explore_concept` resolution also matches `aliases`, so a surface form
  like "thinking backwards" can resolve to canonical "inversion" if a
  canonicalisation pass merged them.
- Related skills: `council-of-thinkers-synthesis-invalid-json-unescaped-quotes`,
  `council-of-thinkers-synthesis-share-url-404`,
  `council-of-thinkers-local-dev`.
