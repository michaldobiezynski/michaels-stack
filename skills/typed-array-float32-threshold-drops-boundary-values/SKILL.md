---
name: typed-array-float32-threshold-drops-boundary-values
description: |
  Fix for values stored in a Float32Array (three.js attributes, WebGL buffers, any typed-array
  data column) silently failing a `>= threshold` test against a JavaScript number literal such
  as 0.7. Use when: (1) a confidence/score/alpha slider set to exactly the value your data uses
  as a floor (0.6, 0.7, ...) hides every item that sits ON that value, (2) counts differ between
  a Python/JSON reference and a JS viewer at the same threshold, (3) items filtered by
  `edgeConfidence[e] < minConfidence` vanish although the JSON says confidence 0.7. Root cause:
  float32(0.7) = 0.699999988 is below the float64 literal 0.7. Fix: round the threshold with
  Math.fround before comparing (or store/compare as integers).
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# Float32 typed arrays drop values that sit exactly on a float64 threshold

## Problem
A three.js graph viewer kept edge confidences in a `Float32Array` for GPU upload and
compared them against a slider value held as a normal JS number. With the slider at 0.7 and
a data pipeline that floors `same_as` edges at exactly 0.7, 971 edges disappeared. The JSON
said `0.7`; the typed array held `0.699999988`; `0.699999988 < 0.7` is true.

## Context / Trigger Conditions
- Data written by Python/JSON with round decimals (0.6, 0.7, 0.85) and read into a
  `Float32Array` (three.js `BufferAttribute`, WebGL, WebGPU, `Float32Array.from(json)`).
- Any filter of the form `value < threshold` / `value >= threshold` where threshold comes
  from UI state, config or a literal.
- Symptom: counts at the default threshold are lower than the reference implementation;
  nudging the slider down by 0.01 brings the missing items back.

## Solution
Round the threshold to float32 precision before every comparison:

```js
export function confidenceThreshold(value) {
  return Math.fround(value);   // float32(0.7) === Float32Array value for 0.7
}
const floor = confidenceThreshold(state.minConfidence);
if (!Number.isNaN(c) && c < floor) continue;   // c is from a Float32Array
```

Apply it everywhere the same threshold is used (render pass, BFS/path logic, counts) so
all code paths agree. Alternatives: store confidences as `Uint8Array` percentages
(0-100) and compare integers, or keep a parallel `Float64Array` for logic and use the
`Float32Array` only for the GPU upload.

## Verification
Count items passing the filter at threshold 0.7 in the JS viewer and in the reference
(Python/JSON): the numbers must match. Before the fix they differed by exactly the number
of items whose stored value equalled the threshold.

## Example
maths-kg viewer (`viz/src/data.js`): emit floors were same_as >= 0.7, broader/narrower
>= 0.6; the slider default 0.7 hid all 0.7 edges until `Math.fround` was applied. The
Python reference (`mathskg.graph.load(min_conf=...)`) compares float64 to float64 and had
no such loss, which is what made the mismatch visible.

## Notes
- `Math.fround(x)` returns the nearest float32 as a float64 number; comparing a
  `Float32Array` element (already float32) to it is exact.
- The same trap applies to `Float32Array` equality checks and to histogram bin edges.
- Half-float (`Float16Array`, `DataView.getFloat16`) has the same problem with far coarser
  precision.
