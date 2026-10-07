---
name: open-maths-curriculum-data-sources-2026
description: |
  Where the machine-readable, openly licensed maths curriculum and prerequisite-graph data
  ACTUALLY lives (verified 10-11/09/2026), with the licence traps. Use when: (1) building a
  knowledge graph / learning-path engine from open curricula (primary to university),
  (2) a GitHub repo is CC0/CC BY but the data you need is not in it, (3) deciding whether
  OpenStax, Khan, EngageNY, Illustrative Mathematics, ACARA, Oak, Coherence Map, os-taxonomy,
  K12-KGraph, Metacademy or mathlib can be merged under one licence, (4) an 'official RDF
  feed' is login-gated or stale. Covers exact download locations, per-source licence
  (NC vs SA vs CC0), the CC BY-SA / BY-NC-SA incompatibility, and id-normalisation gotchas.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Open maths curriculum data sources (state as of September 2026)

## Problem
Curriculum data is advertised in one place and served from another, and the licences do
not compose. A day of agent investigation produced the map below; reuse it instead.

## Context / Trigger Conditions
- You need nodes (topics/standards) AND prerequisite edges for maths across school stages.
- You plan to merge several sources into one graph and distribute or sell it.
- You hit: Scootle login wall (ACARA), Coherence Map repo with no data files, OpenStax
  repos whose LICENSE says NC, Oak API refusing without a key.

## Solution: source map

| Source | What | Where the data really is | Licence (verified) |
|---|---|---|---|
| os-taxonomy (Marble) | 1,590 primary micro-topics, 3,221 prereq edges with reasons, CCSS + England NC codes | github.com/withmarbleapp/os-taxonomy `data/*.json` | ODbL (db) + CC BY-SA 4.0 (content) |
| Coherence Map (Achieve the Core) | 480 CCSS maths standards K-HS, 757 directed + 283 undirected prereq edges | NOT the repo tables: fetch `https://achievethecore.org/coherence-map/data.js` (`window.cc = {standards, clusters, domains, edges, nd_edges}`); the CC0 repo only embeds a 2015 542-row `EdgeSet` in `spreadsheet.js` | app source CC0; live data terms unverified |
| K12-KGraph | Chinese PEP textbooks K1-12, 2,711 maths nodes, 853 prereqs; 100% Chinese; two edge shapes (`target` vs `target_name_to_ids[]`) | HF `lhpku20010120/K12-KGraph`, repo haolpku/K12-Dataset | CC BY-NC-SA 4.0 (code MIT) |
| OpenStax | Prealgebra..Calculus, Algebra 1 (IM-derived lesson fragments), Statistics | github.com/openstax/osbooks-* (CNXML; sparse-clone `collections modules META-INF`) | CC BY-NC-SA 4.0 for 6 of 7 maths repos; only `osbooks-statistics` is CC BY 4.0 |
| Metacademy | 393 ML/maths concepts, reasoned prereqs | github.com/metacademy/metacademy-content; tags use hyphens where dirs use underscores (338 of 359 'dangling' deps fixed by `tag.replace('-','_')`) | CC BY-SA 3.0 (dormant 2017) |
| mathlib | undergraduate syllabus | `docs/undergrad.yaml` (562 leaves, 130 gaps) + `docs/overview.yaml`; declaration deps without a Lean build from HF `phanerozoic/Lean4-Mathlib` parquet (232k decls, `deps` list resolves 99.9%) | Apache 2.0 |
| ACARA v9 maths | 240 content descriptions F-10 | the 'machine-readable' RDF/JSON-LD is behind Scootle login and the public rdf endpoint serves stale v8.4; use the public `.../ac-version-9/downloads/curriculum-workbook.xlsx`. No separate 10A level in v9 | CC BY 4.0 |
| Oak National Academy | England KS1-4 lessons/units/threads | open-api.thenational.academy, free API key required; only post-Sept-2022 content is OGL | OGL v3 |
| Not usable open | Khan (proprietary), EngageNY/Eureka (BY-NC-SA), CK-12 (custom), IM current edition (BY-NC; 1st ed BY 4.0 HTML only), Cambridge Maths Framework (closed), DLM maps (no public data) | | |

## Licence rule that decides the architecture
CC BY-SA 4.0 adaptations must stay BY-SA; CC BY-NC-SA 4.0 adaptations must stay BY-NC-SA;
no compatible bridge exists, and translation counts as adaptation. So one merged graph
containing both os-taxonomy and K12-KGraph/OpenStax is NOT distributable. Options: keep
it private; or ship an open core (os-taxonomy, Coherence Map, Metacademy, mathlib, ACARA,
OpenStax Statistics) with the NC material as a separate layer. Tag every node with its
source licence from day one so the open subset can be cut later.

## Id-normalisation gotchas
- os-taxonomy writes CCSS sub-standards dotted for K-2 (`K.CC.4.a`) but undotted for 6-7
  (`6.EE.2a`); Coherence Map ids are undotted. Normalise with `re.sub(r"\.([a-z])$", r"\1", code)`.
- Both sources omit the cluster letter (`K.OA.2`, not `K.OA.A.2`), so they join on the string.
- K12 ids encode the book: `math_<1a..9b|bx1|bx2|xzxbx1..3>_rjb_<type><n>`; 23 prereq edges
  point from a later grade to an earlier one.

## Verification
`gh api repos/<org>/<repo>` for licence/activity; `head -1 LICENSE` and `grep md:license
collections/*.xml` inside OpenStax clones; `curl` the Coherence Map `data.js` and parse
after slicing from the first `{`.

## Notes
Built into ~/development/projects/maths-kg (private repo) with a per-source ingester each;
see that repo's `mathskg/ingest/*.py` for working parsers of every format above.
