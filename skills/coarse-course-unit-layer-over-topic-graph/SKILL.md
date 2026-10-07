---
name: coarse-course-unit-layer-over-topic-graph
description: |
  Build a readable coarse layer (COURSES made of UNITS) above a fine-grained topic knowledge
  graph so that 'what do I need for course X' returns tens of nodes instead of thousands.
  Use when: (1) clicking a goal lights up thousands of topics, (2) topics already carry a
  course label and an embedding, (3) you need unit-level prerequisite plans that read like a
  syllabus. Method: per-course k-means on topic embeddings (k = clamp(sqrt(n/3), 3, 10)),
  LLM names each cluster from its most central members, unit edges = aggregated
  SOURCE-ASSERTED prerequisite edges between members (exclude structural/inferred filler;
  keep the net direction; prune to top-1 incoming or weight >= 1.5), plans use course order
  as the strong prior (prerequisite course never later than the goal course; assumed-mastery
  floor) and unit edges only for ordering within a course.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Coarse course/unit layer over a topic graph

## Problem
A 6.5k-topic canonical graph answers 'what precedes university statistics' with hundreds of
topics. Learners think in courses and units. The first attempt at a unit-level plan was
polluted (abstract algebra before intro statistics) and interleaved courses arbitrarily.

## Solution
1. **Units**: for each course, k-means on the topics' embedding vectors (Voyage of the head
   member), k = clamp(round(sqrt(n/3)), 3, 10). Record members ordered by cosine to the
   centroid; the top 12 name the unit.
2. **Names**: one LLM call per course with all its clusters (id, size, central topics) ->
   2-5 word unit names plus one-line descriptions; enforce distinct names per course.
   22 courses cost ~$1.
3. **Edges**: sum weights of canonical prerequisite/formal edges (and source-asserted next
   at 0.4) between members of different units. EXCLUDE structural/derived filler edges: they
   are fine for reachability but sum up under aggregation and invent course links. Keep the
   dominant direction discounted by the counter-flow; keep an edge if weight >= 1.5 or it is
   the unit's strongest incoming.
4. **Plan** for a goal course: eligible units satisfy floor < course < goal in curricular
   order (a prerequisite is never a later course; courses at or below the assumed mastery
   floor are omitted); closest-first, strongest-first selection over unit edges; present
   grouped by course order, ordered within a course by a topological sort of unit edges
   (SCC-condensed), then the goal course's own units in order.
5. Export units (with centroid positions and age spans), unit edges and course edges next to
   the topic data so a viewer can switch granularity without recomputation.

## Verification
Write the plan for two courses to files and require the viewer to reproduce them line for
line. A unit test with 6 synthetic units checks the floor, the course-order exclusion and the
within-course ordering.

## Notes
- 3-D 'tornado' layout that reads as a progression: vertical = course band in a curated
  DISPLAY order (not the taxonomy's list order: applied mechanics next to A level, not above
  ML) + within-course depth rank (longest path over the SCC condensation of ordered edges),
  so no two nodes share a height; radius = f(height) funnel (narrow at basics) x normalised
  semantic radius^0.8, angle twisted with height; label rings by the dominant course at that
  height. Pure depth rank as the axis puts long primary chains above shallow formal-library
  topics; pure age stacks hundreds at one height. Compact layouts need edge alpha ~0.05 and
  low bloom or additive edges wash the core white.
- To make horizontal distance mean 'related', do not twist the funnel with height (it
  separates a topic from its prerequisites) and, after the semantic UMAP, run a few
  iterations of Laplacian smoothing (pos <- 0.5 pos + 0.5 weighted mean of linked
  neighbours; equivalences weighted 2x, prerequisites 1x, containment/order 0.5x). Verify
  with mean plane distance of linked pairs vs random pairs (here 0.12 -> 0.08 before the
  funnel compression; 6x closer in final coordinates).
- Course order among university courses is a linearisation; document it, expect a few
  arguable placements (multivariable calculus before probability theory).
- WebGL caps line width at 1px on desktop; encode unit-edge weight as alpha.
