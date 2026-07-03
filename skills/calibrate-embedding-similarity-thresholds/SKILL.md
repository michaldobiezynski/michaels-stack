---
name: calibrate-embedding-similarity-thresholds
description: |
  Before setting ANY embedding cosine-similarity threshold (fuzzy match, dedup,
  near-duplicate detection, retrieval cutoff, "resolve vs suggest" tiers),
  measure your embedder's ACTUAL cosine distribution first — do not copy
  abstract thresholds like 0.85/0.70/0.50 from intuition, a spec, a blog, or a
  different embedder. Use when: (1) a task/issue specifies a cosine threshold
  and you're about to implement it; (2) a similarity-gated feature "never fires"
  or "fires on everything"; (3) you're deduping/merging/matching via embeddings;
  (4) you need a high-precision discrete decision (auto-merge, auto-resolve)
  from similarity. Many production embedders (Voyage, OpenAI, Cohere) have
  COMPRESSED, non-zero-baseline cosine ranges where even identical short text
  scores ~0.6, so 0.85 is physically unreachable.
author: Claude Code
version: 1.0.0
date: 2026-05-29
---

# Calibrate embedding-similarity thresholds to the actual distribution

## Problem

A spec/issue/blog says "resolve when cosine >= 0.85, suggest at 0.50". You wire
it up over your embedder and the feature is dead: nothing reaches 0.85, the
"suggest" tier barely fires, and the whole thing silently returns nothing — or
the opposite, everything matches because the baseline similarity is high.

The root cause: **cosine-similarity scales are embedder-specific and often
compressed with a high non-zero baseline.** A threshold that's meaningful for
one model (or for normalized name-vs-name) is meaningless for another (or for
query-vs-document, or short-vs-long text). Abstract thresholds do not transfer.

Concrete measurement that motivated this skill — Voyage `voyage-4-large`,
1024-d, query-input vs document-input cosines (2026-05-29):

| pair | cosine |
|---|---|
| identical short text ("inversion" vs "inversion") | ~0.61 |
| clearly related ("risk" vs "tail risk"; "first principles" vs "first principles thinking") | ~0.32–0.46 |
| unrelated ("banana" vs "tail risk") | ~0.20–0.22 |

So the spec's 0.85 auto-resolve bar was **physically unreachable** (max ~0.61
even for identical text), and 0.50 sat above most "related" pairs. The usable
signal lived in a narrow 0.22→0.61 band, and there was no single cosine cut that
separated "should auto-resolve" (e.g. "first principles"→"first principles
thinking", 0.46) from "should not" (e.g. "risk"→"risk preference tradeoff",
0.44).

## Context / Trigger Conditions

Apply this skill when:

- An issue/spec/PR hands you a cosine threshold to implement (`>= 0.85`, etc.).
- A similarity-gated path "never matches" or "matches everything" in practice.
- You're building embedding dedup, canonicalisation/merge, fuzzy lookup,
  near-duplicate detection, semantic search cutoffs, or clustering.
- You need a **binary high-stakes decision** (auto-merge two records,
  auto-resolve a query to one canonical entity) from a similarity score.
- You switch embedders or change the input type (`query` vs `document`) or text
  length — the old thresholds are now invalid.

## Solution

1. **Measure before you threshold.** Embed a handful of labelled pairs with
   YOUR embedder and input types, and print cosines for three buckets:
   - identical / paraphrase (the upper bound you'll ever see),
   - genuinely related (the band you want to "catch"),
   - clearly unrelated (the noise floor / baseline).
   This takes a few API calls and minutes. Do it first.

2. **Set thresholds from the observed bands, not from intuition.** Put the
   "offer candidates / suggest" floor between the related and unrelated bands
   (e.g. if related ~0.40 and unrelated ~0.22, a ~0.33–0.36 floor). Document the
   measured numbers next to the constant so the next person (or a model swap)
   can recalibrate.

3. **For high-precision discrete decisions, do NOT rely on the cosine cut.**
   When the cost of a wrong auto-merge/auto-resolve is high and the bands
   overlap (as above), gate the decision on a **deterministic text/structural
   signal** and use the embedding only to RANK candidates:
   - token-subset / sub-phrase containment ("first principles" ⊆ "first
     principles thinking"),
   - normalized exact match / alias match,
   - edit distance / token Jaccard with a hard floor,
   - guard against degenerate cases (a single generic token that is a substring
     of many names — require multi-token or whole-name equality).
   This gives high precision the compressed cosine can't, while the embedding
   still surfaces the candidate set for a "did you mean?" suggestion tier.

4. **Make the threshold an env/config knob** so it can be retuned without a code
   change when the embedder or corpus changes.

## Verification

- Re-run the labelled pairs after wiring the threshold: related pairs land in
  the intended tier, unrelated below it, identical at/above.
- The feature actually fires on a live sample (not "always nothing" / "always
  everything").
- For the discrete-decision path: a known good near-match resolves, and a known
  trap (generic word inside a longer name, plural mismatch) does NOT.

## Example

Spec: `compare_speakers(topic="risk")` should fuzzy-resolve to the concept
"tail risk" at cosine >= 0.85, else suggest at >= 0.50.

What worked instead, after measuring Voyage's range:
- Kept embedding-NN to find the top-N nearest concepts (ranking only).
- **Auto-resolve gated on text overlap**, not cosine: resolve only when the
  topic's tokens are a sub-phrase of a candidate's name AND the topic is
  multi-word (or equals the whole name) — so "first principles" →
  "first principles thinking" resolves, but bare "risk" does not auto-resolve
  to "risk preference tradeoff".
- **Suggest tier** keyed to a measured floor (`>= 0.35`) so non-resolving topics
  still return ranked "did you mean?" candidates instead of a silent zero.

Result: topics that previously returned nothing now surface useful candidates;
auto-resolution is high-precision; no magic 0.85 that never fires.

## Notes

- The same compression applies to OpenAI `text-embedding-3-*`, Cohere, and many
  sentence-transformers models — each has its own baseline and scale; always
  measure per model.
- Input asymmetry matters: `query` vs `document` embeddings (and short vs long
  text) shift cosines noticeably. Measure with the SAME input types you'll use
  at runtime.
- Normalizing/centering embeddings (subtracting a corpus mean) can widen the
  usable band, but measuring + a structural gate is usually faster and safer.
- Related discipline: this is "verify library/model behaviour empirically before
  relying on it" applied to embedding similarity scales.
