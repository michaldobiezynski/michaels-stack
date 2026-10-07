---
name: mastery-scheduler-simulate-before-content
description: |
  Build and test a Math-Academy-style mastery-learning scheduler (graph-bisection diagnostic,
  frontier lessons, spaced repetition, fractional implicit repetition, remediation) against a
  SIMULATED learner before writing any lessons or UI. Use when: (1) starting an adaptive
  learning product on a prerequisite knowledge graph, (2) a diagnostic 'uses its whole budget
  and places almost nothing' or a learner 'stalls with the day full of reviews', (3) you need
  to show fractional implicit repetition actually reduces review load. Covers the three traps
  found: a sparse slice (most topics without prerequisites) makes bisection and implicit credit
  worthless, so author direct prerequisites within the slice first; a simulator whose lessons
  never teach makes every lesson fail; a reviews-first policy without a daily share cap starves
  lessons, and with the cap you must measure review load with an uncapped budget to see FIRe's
  effect.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Mastery scheduler: simulate before content

## Problem
Building lessons for hundreds of topics costs money and time; the scheduler is where an
adaptive product succeeds or fails, and it can be tested for free with a simulated learner.

## Context / Trigger Conditions
- A topic graph with prerequisite edges and a chosen course slice.
- No learners yet.

## Solution
1. **Slice**: goal course topics plus source-asserted prerequisite ancestors above a mastery
   floor, restricted to courses no later than the goal. Exclude heuristic/structural links.
   Check the root count: 236 of 326 roots here meant the graph was unusable for placement.
2. **Densify** the slice with a stronger model authoring DIRECT prerequisites (candidates =
   other slice topics by embedding kNN; 0-5 per target; floor 0.6; cycle-guarded emit).
   $12 for 326 topics took roots 236 -> 34 and edges 208 -> 619.
3. **Scheduler**: diagnostic = pick the undecided topic whose correct/wrong outcomes split the
   undecided set most evenly (correct marks ancestors known, wrong marks descendants
   unknown), cap ~60 questions; stagger first due dates of diagnosed topics; next task =
   due reviews first but at most ~60% of the daily budget, else the frontier topic that
   unlocks the most; intervals 1,3,7,14,30,60,120,240 days, reset on fail; passing a topic
   sends credit weight x 0.5 per hop to prerequisites, a full credit reschedules them;
   failing a lesson schedules the weakest prerequisite now.
4. **Simulator**: hidden known set closed under prerequisites; stability grows on practice;
   p(recall) = exp(-days/stability); a LESSON must teach (raise stability with prob ~0.85)
   before the practice score is drawn, else every lesson fails and the learner stalls.
5. **Metrics**: placement precision/recall vs hidden state; lessons/reviews per day; days to
   master the goal; reviews with FIRe on vs off using an UNCAPPED budget (capped runs hide
   the difference). Observed: recall 0.20 -> 0.48 after densifying; FIRe cut reviews 26%.

## Verification
Unit tests on a 4-node chain for bisection propagation, frontier order, credit arithmetic,
review-before-lesson when overdue, and remediation on a failed lesson.

## Notes
- Content step that followed: one schema-constrained Opus call per topic (lesson 150-300
  words with LaTeX, 2 worked examples, 6 gradeable questions typed numeric/expression/
  multiple_choice) at ~$0.15-0.29/topic; then a blind re-solve of every question by a cheaper
  model, graded with the same sympy checker; 95.5% agreement, the rest excluded from tasks
  rather than trusted. Grade leniently (commas, %, 'x =', implicit multiplication).
- The scheduler's parameters (decay 0.5, hop cap 3, intervals) are guesses to tune with
  real data; keep them in one place.
- Report 'initially known' separately from the end state: learning grows the hidden set.

## Addendum (12/09/2026): goals for any course, content on demand
- Make the GOAL a (course, floor) pair chosen in the app and cut the slice per pair; keep
  mastery per topic id so goals share progress, and count the diagnostic budget only over
  the current slice's topics or a second goal inherits a spent budget.
- 'Author as you go': author a course's direct prerequisites once (per-course work dir with a
  done.json marker; 27 targets cost $1.85 on Opus, 327 cost $11.56) and fold the authored raw
  edges into the slice by mapping head ids -> canonical ids so no graph rebuild is needed.
- Generate lessons just ahead of the scheduler with a small worker pool fed an ORDERED wanted
  list. Prefetch both branches of the next diagnostic question (compute the pick after a
  hypothetical correct/incorrect answer without recording it) while the learner answers; after
  the diagnostic, prefetch due reviews then the frontier by unlocks. First lesson lands in
  about a minute; later waits are hidden.
- Queue a second course chosen mid-run behind the running authoring job; filter stale failures
  to the current slice; hold one lock across the slice cut so a goal change cannot interleave.
