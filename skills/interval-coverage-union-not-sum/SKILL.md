---
name: interval-coverage-union-not-sum
description: |
  When computing how much of a window [start,end] is "covered" by a set of
  labelled time/space intervals (diarisation segments, VAD spans, calendar
  busy-blocks, schedule occupancy, 1-D bounding boxes), accumulate the UNION
  of merged intervals per label, never the raw sum of overlaps. Use when:
  (1) building a "dominant speaker / dominant label by coverage fraction"
  decision, (2) a coverage/overlap fraction can exceed 1.0 in tests or prod,
  (3) intervals with the SAME label can overlap each other (pyannote emits
  repeated/overlapping same-speaker turns; VAD can emit adjacent merged spans),
  (4) a threshold like "keep if dominant covers >= 60% of the window" silently
  passes on a window that is mostly silence or contested. The additive bug is
  invisible on clean non-overlapping inputs and only bites on overlap, so unit
  tests with tidy fixtures miss it. Fix: clip each interval to the window,
  bucket by label, merge overlapping intervals per bucket, sum merged lengths;
  compute silence as window minus the union of ALL intervals.
author: Claude Code
version: 1.0.0
date: 2026-05-28
---

# Interval coverage = union of merged intervals, not sum of overlaps

## Problem

You have a window `[start, end]` and a list of labelled intervals
`(seg_start, seg_end, label)`, and you want, per label, "how many seconds of
the window does this label cover?" — then a decision like "the label covering
>= 60% of the window wins; otherwise drop."

The obvious implementation is wrong:

```python
cover = {}
for s, e, label in segments:
    ov = max(0.0, min(end, e) - max(start, s))   # overlap with the window
    if ov > 0:
        cover[label] = cover.get(label, 0.0) + ov  # BUG: additive
dom_frac = max(cover.values()) / (end - start)
```

If two intervals with the **same label** overlap each other, their overlap is
counted twice. `cover[label]` can exceed the window length, so `dom_frac` can
exceed `1.0`, and a window that is actually mostly silence (or contested by
another speaker) sails past a coverage threshold and gets wrongly kept /
attributed. Silence computed as `window - sum(cover.values())` is correspondingly
understated (and can go negative before clamping).

This is invisible on clean fixtures (non-overlapping segments sum correctly), so
hand-written unit tests usually miss it. It surfaces only on real overlapping
input — exactly what diarisers and VADs produce.

## Context / trigger conditions

- Diarisation post-processing: "dominant speaker for this chunk by overlap"
  (pyannote can emit several overlapping turns for the same speaker, and
  simultaneous-speech overlaps across speakers).
- VAD / activity spans, calendar busy-time, schedule occupancy, 1-D box IoU,
  any "fraction of a window covered by these (possibly overlapping) ranges".
- Symptom: a coverage/overlap fraction `> 1.0` in a test or log; a keep/accept
  threshold passing on input that is mostly empty or contested.

## Solution

Merge before summing. Clip to the window, bucket by label, union each bucket:

```python
def merged_length(intervals):
    """Total length of the UNION of [(start, end)] intervals."""
    ivs = sorted(intervals)
    if not ivs:
        return 0.0
    total, cur_s, cur_e = 0.0, ivs[0][0], ivs[0][1]
    for a, b in ivs[1:]:
        if a <= cur_e:
            cur_e = max(cur_e, b)          # overlap/adjacent: extend
        else:
            total += cur_e - cur_s          # gap: close the run
            cur_s, cur_e = a, b
    return total + (cur_e - cur_s)

from collections import defaultdict
clipped, all_clipped = defaultdict(list), []
for s, e, label in segments:
    cs, ce = max(start, s), min(end, e)     # clip to the window
    if ce > cs:
        clipped[label].append((cs, ce))
        all_clipped.append((cs, ce))
cover = {label: merged_length(ivs) for label, ivs in clipped.items()}
silence = max(0.0, (end - start) - merged_length(all_clipped))  # union of ALL
```

Now every label's coverage is `<= window length`, `dom_frac <= 1.0`, and silence
is the window minus the union of all speech (so simultaneous speech does not
over-reduce it).

## Verification

Two regression cases that the additive version fails and the union version passes:

```python
# Same-label overlap: union is [0,5.5]=5.5 (0.55), NOT 4+3.5=7.5 (0.75).
cover_frac(0, 10, [(0, 4, "a"), (2, 5.5, "a")]) == 0.55     # -> below 0.60 -> drop

# Fractions must never exceed 1.0 even with duplicates + a second label.
result = attribute(0, 10, [(0,10,"a"), (0,10,"b"), (0,10,"a")])
assert result["dom_frac"] <= 1.0 and result["second_best_frac"] <= 1.0
```

Always include at least one OVERLAPPING-interval fixture; a suite with only
tidy non-overlapping segments will pass the buggy code.

## Notes

- This bit a real diarisation attribution pass (council-of-thinkers #100). The
  additive code passed every clean test; an adversarial review reproduced
  `dom_frac = 2.0` on overlapping same-label segments. Add the overlapping
  fixture proactively.
- A "margin guard" (dominant must beat runner-up by X% of the window) inherits
  the same corruption if it reads the additive seconds — fix the coverage maths
  and the guard becomes sound automatically.
- Do NOT "fix" this by switching to a diariser's *exclusive* (non-overlapping)
  output if a downstream step needs to SEE contention (e.g. to drop chunks where
  two people talk at once). Keep the overlapping view and merge correctly.
