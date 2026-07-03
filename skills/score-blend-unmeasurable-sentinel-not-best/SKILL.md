---
name: score-blend-unmeasurable-sentinel-not-best
description: |
  Catch the bug where a confidence/score that blends several measurements treats
  an UNMEASURABLE input (a None embedding, an inf/NaN distance, a "no data"
  sentinel) as the BEST possible value instead of the worst, so a doubtful item
  silently passes a quality/auto-promote gate. Use when: (1) you compute a score
  as a weighted blend of sub-scores and one sub-score derives from a value that
  can be missing/unmeasurable; (2) a guard exists for one symmetric input (e.g.
  the host side) but not its mirror (e.g. the guest side); (3) an item is
  auto-approved/auto-promoted/auto-merged with surprisingly HIGH confidence and
  NO flags despite missing data; (4) a normaliser like clamp((x - lo)/range)
  receives inf and clamps to 1.0; (5) review/adversarial verification reports
  "unmeasurable separation scored as maximal". Mirror of, but distinct from,
  classifier-failure-vs-negative-bucket (that is about call failures vs genuine
  negatives; this is about a missing NUMBER scoring as the optimum).
author: Claude Code
version: 1.0.0
date: 2026-06-02
---

# Unmeasurable sentinel must score as the worst case, not the best

## Problem

A confidence score blends several sub-scores, e.g.

```python
confidence = 0.30*host_score + 0.30*sep_score + 0.25*dom_score + 0.15*len_score
```

One sub-score comes from a measurement that can be **absent**: an embedding that
came back `None`, a distance set to `float("inf")` because the vector could not
be computed, a `NaN`, or a "could not determine" sentinel. The normaliser maps
that sentinel to the TOP of the range, so "I could not measure this" is rewarded
exactly like "this is perfect". The item then clears the auto-promote / auto-
merge / auto-approve gate with high confidence and no flags. This is the failure
mode the safety gate was built to prevent.

The classic shape: `inf` distance is meant to mean "maximally far / unknown", but

```python
sep_score = clamp((distance - tau) / (1.0 - tau))   # clamp((inf - 0.5)/0.5) -> 1.0
```

turns it into perfect separation, and a guard like `if distance < tau:
flag("WEAK")` never fires because `inf < tau` is `False`.

## Context / Trigger conditions

- You are writing or reviewing a scoring/confidence function that **blends**
  multiple measurements, and at least one can be missing/unmeasurable.
- One input already has a sentinel guard (`and x != float("inf")`) but the
  symmetric input does not. Asymmetric guards are the tell.
- An adversarial review or a surprised user reports an item auto-passed with high
  confidence despite missing data ("un-embeddable cluster auto-promoted",
  "empty field scored as match").
- Any `clamp((value - lo) / span)` / min-max normaliser fed a value that can be
  `inf`/`NaN`.

## Solution

1. **Detect non-finite / missing before normalising.** Use `math.isfinite(x)`
   (catches both `inf` and `nan`) or an explicit `None` check.
2. **Score it as the WORST case**, not via the formula:
   ```python
   sep_measurable = math.isfinite(distance)
   sep_score = clamp((distance - tau) / span) if sep_measurable else 0.0
   ```
3. **Raise a dedicated blocking flag** so it is visible and cannot be promoted:
   ```python
   if not sep_measurable:
       flags.append("GUEST_UNEMBEDDABLE")     # distinct from WEAK_SEPARATION
   BLOCKING_FLAGS = {..., "GUEST_UNEMBEDDABLE"}
   action = "promote" if (not flags & BLOCKING_FLAGS and conf >= thr) else "review"
   ```
4. **Mirror every symmetric guard.** If the host branch guards `inf`, the guest
   branch must too. Grep for the existing sentinel check and apply it to each
   input that shares the sentinel.
5. **Add a unit test on the sentinel path** (it is usually a corner case with no
   coverage): assert the sentinel yields the blocking flag, `sep_score == 0`, and
   `action == "review"` even with `promote=True`.

## Verification

- Construct the inputs with the sentinel (e.g. a cluster with
  `host_distance=float("inf")`) and assert the planner returns `review` /
  `flags != []`, not `promote`/`confidence ~ 0.97`.
- Re-run the auto-gate end to end and confirm the doubtful item is staged, not
  promoted.

## Example (this session)

A voice-sample auto-enrol pipeline scored each diarisation cluster's separation
from the host as `clamp((guest_distance_to_host - tau)/(1-tau))`. When the guest
cluster could not be embedded, `build_cluster_infos` set `host_distance =
float("inf")`. The host sub-score guarded inf (`and host_distance !=
float("inf")`) but the guest separation sub-score did not, so `clamp(inf)=1.0`:
an UNMEASURABLE separation scored as MAXIMAL, yielding confidence ~0.97 with no
flags, and `--promote` would have written a possibly-contaminated reference to
disk. Fix: `math.isfinite` guard, `sep_score = 0.0` when not finite, new
`GUEST_UNEMBEDDABLE` blocking flag, plus a unit test on the inf path.

## Notes

- `x != float("inf")` misses `nan` and `-inf`; prefer `math.isfinite(x)`.
- This is the scoring-layer cousin of treating a CALL FAILURE as a negative
  result (see classifier-failure-vs-negative-bucket): both let a non-answer
  masquerade as a confident answer, just at different layers.
- A fast way to find these: search the scoring function for every sentinel
  (`inf`, `None`, `-1`, `nan`) and check each is guarded symmetrically on every
  input that can carry it.
