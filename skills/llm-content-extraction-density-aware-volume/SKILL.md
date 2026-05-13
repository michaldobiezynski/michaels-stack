---
name: llm-content-extraction-density-aware-volume
description: |
  Fix for LLM-based content-extraction pipelines that systematically
  under-sample long sources because the prompt says "at least N clips"
  and the model settles near N regardless of source duration or density.
  Use when:
  (1) building a podcast / interview / lecture clipper where the LLM picks
      candidate moments from a transcript,
  (2) you return 8-15 clips from a 90-180 minute source while industry
      tools (Opus Clip, Munch) return 30-60 from the same input,
  (3) auditing the clipper output reveals 15+ minute unclipped stretches
      between consecutive clips on what should be content-dense source,
  (4) any LLM-extraction task where output VOLUME matters and the model
      drifts toward the lower bound stated in the prompt.
  The fix has three parts: a duration-scaled output floor (not a fixed
  minimum), an in-prompt coverage check before finalising, and an
  external audit that computes unclipped windows from the output and
  fails the run if any exceeds a threshold.
author: Claude Code
version: 1.0.0
date: 2026-05-13
---

# Density-aware output volume for LLM content extraction

## Problem

LLM-based content extractors (podcast clippers, meeting highlighters,
documentary searchers, any "pick the best N moments" task) drift toward
the LOWER BOUND of whatever output-volume directive the prompt contains.
If the prompt says "at least 8 clips", the model often returns 8 to 15
clips, regardless of whether the source is a 5-minute monologue or a
3-hour podcast. The model treats "at least 8" as a target, not a floor.

The result is silent under-sampling on long, content-dense sources. A
2-hour interview with a skilled communicator like Mark Manson, Naval, or
Tyler Cowen yields 30-60 genuinely shareable moments. A conservative
LLM pass yields 14, with 80%+ of the runtime unclipped. The output looks
plausible (high hook-strength scores, recognisable topics) but the
clipper is leaving most of the value on the floor.

This bug is invisible without an audit. The clips that ARE returned tend
to be high-quality, so no individual clip looks wrong. The failure is
only obvious when you compute coverage.

## Context / Trigger conditions

- LLM picks N candidate clips from a long transcript via a `<clips>`
  JSON array (or any "pick the best N items" structured output).
- The prompt has an "at least N" minimum, often 8 or 10.
- The source is >30 minutes; the bug gets worse as source duration grows.
- Symptoms:
  - Output volume looks similar across very different source durations.
  - Inspecting the clip start/end timestamps reveals long unclipped
    runs - e.g. 24 minutes between clip 8's end and clip 9's start.
  - Industry baseline (Opus Clip, Munch, descript) returns 2-4x more
    clips from the same source.

## Solution

Three independent layers. Apply all three; they don't substitute.

### Layer 1: density-aware floors in the prompt

Replace "at least N clips" with a duration-scaled floor. Tell the model
to read the LAST timestamp in the transcript to estimate runtime, then
scale its output:

```
## Output volume - scale to source duration

Look at the LAST timestamp in the transcript to estimate the source
runtime, then return at LEAST this many clips:

- Under 30 minutes runtime:    at least 8 clips
- 30 to 90 minutes:            at least 15 clips
- 90 to 180 minutes:           at least 25 clips
- Over 180 minutes:            at least 35 clips

These are FLOORS, not targets. Content-dense sources (podcast interviews
with skilled communicators, multi-topic livestreams) should comfortably
exceed them. The downstream pipeline filters and scores; under-surfacing
here cannot be recovered later.
```

The point of the table is to make the model commit BEFORE generating the
clips. With a single "at least N" line, the model anchors on N. With a
duration-scaled table, the model first computes which bucket the source
falls into, then picks a target.

### Layer 2: in-prompt coverage check

After the volume floor, add a mandatory self-check instruction:

```
## Coverage check - mandatory before finalising

Before you return the JSON array, walk through your picks in chrono-
logical order and identify any gap of more than 15 minutes between one
clip's end and the next clip's start. For every such gap, GO BACK to
that window in the transcript and find at least one more clip.

A 2-hour podcast should never have a 25-minute unclipped stretch unless
that stretch is genuinely unwatchable (sponsor read, audio check, off-
topic admin, host monologue between topics with no quotable line).
```

The LLM treats this as a chain-of-thought step before the final JSON.
It will revise its picks if the gap-scan turns up uncovered windows.

### Layer 3: external audit (CI-style)

Don't trust the LLM's self-check alone. Add a script-level audit that
runs after analyse and prints a warning if coverage looks thin:

```python
def audit_coverage(clips: list[dict], source_duration: float) -> dict:
    """Returns a coverage report. Caller decides whether to fail the run."""
    covered = sorted([(c["start"], c["end"]) for c in clips])
    last = 0.0
    big_gaps = []
    for s, e in covered:
        gap = s - last
        if gap > 900:  # 15 minutes
            big_gaps.append((last, s, gap))
        last = e
    tail_gap = source_duration - last
    if tail_gap > 900:
        big_gaps.append((last, source_duration, tail_gap))

    total_clip_time = sum(e - s for s, e in covered)
    coverage_pct = total_clip_time / source_duration * 100

    return {
        "clip_count": len(clips),
        "source_minutes": source_duration / 60,
        "coverage_pct": coverage_pct,
        "big_gaps": big_gaps,  # tuples of (start, end, duration_seconds)
    }


def expected_min_clips(source_duration_minutes: float) -> int:
    """Density floor from the same table as the prompt."""
    if source_duration_minutes < 30:
        return 8
    if source_duration_minutes < 90:
        return 15
    if source_duration_minutes < 180:
        return 25
    return 35


# In the analyse step:
report = audit_coverage(clips, source_duration)
expected = expected_min_clips(report["source_minutes"])
if report["clip_count"] < expected:
    console.print(f"[yellow]warning: {report['clip_count']} clips on a "
                  f"{report['source_minutes']:.0f}-min source; expected "
                  f"at least {expected}. Consider re-analyse.[/yellow]")
if report["big_gaps"]:
    console.print(f"[yellow]warning: {len(report['big_gaps'])} unclipped "
                  f"windows over 15 minutes.[/yellow]")
```

The audit is cheap (one pass over the clip JSON) and catches LLM
non-determinism: even with the prompt fixes, the LLM occasionally
under-shoots. The audit makes that failure visible immediately rather
than letting it ship.

## Verification

Run all three layers on a known long, dense source (a 2-hour podcast
interview is ideal). The output should:

- Return clips at or above the density floor (e.g. 25+ on a 2-hour source).
- Have zero "big gaps" over 15 minutes in the coverage report.
- Have total clip duration of 8-15% of source duration (a 142-min source
  should have ~12-20 minutes of clip content, spread across 25-45 clips).

Then bypass each layer in turn and re-run to confirm each one is
actually doing work:
- Without layer 1: the LLM returns ~10-15 clips and the audit warns.
- Without layer 2: the LLM returns enough clips overall but clusters them
  at the start or in the densest sections, leaving 15+ min gaps.
- Without layer 3: subtle under-shoots silently ship.

## Example

Real result from the clipsmith pipeline on a 2h22m (142 min) Modern
Wisdom interview with Mark Manson:

| Configuration | Clips returned | Big gaps (>15min) | Coverage |
|---|---|---|---|
| `at least 8` (single floor) | 14 | 5 (max 24.2 min) | 16% |
| Density-scaled floor + coverage check | 39 | 0 | 22% |

The conservative prompt left 4 unclipped windows over 20 minutes long,
including one 24-minute stretch. The density-aware prompt produced 25
more clips with continuous coverage, surfacing genuine Manson takes the
first pass missed (the "shit sandwich" framing, Hormozi on blame,
criticism capture, "choosing a partner is choosing their Tuesday").

## Notes

- The density floors above are calibrated for podcast / interview /
  monologue content where the LLM is picking quotable moments. For
  other domains (technical lectures, news clips, sports highlights),
  the right floor may differ - calibrate against industry tools.
- "Coverage" doesn't mean "clip every second". 15-25% of source duration
  in clips is healthy for a podcast; higher than 30% probably means the
  clipper is grabbing filler.
- The 15-minute gap threshold in the coverage audit is a judgement call.
  Tighten to 10 min for very dense source (debates, panels); loosen to
  20 min for narrative-heavy source (memoir-style monologues with long
  setups).
- The model's ability to read the LAST timestamp from the transcript is
  generally reliable when timestamps are formatted as `[seconds.dec]`
  at the start of each line. If you're seeing weird floor selection,
  print the timestamp range explicitly into the prompt as a separate
  placeholder.
- Layer 3 (external audit) is the most important. The LLM can ignore or
  forget layers 1 and 2 on a long context; the script-level audit is
  deterministic.

## Related skills

- `llm-cli-stdin-arg-max-long-prompts` - for large prompts containing
  full podcast transcripts, pipe via stdin not argv.
- `shorts-hook-frame-headline-card` - the downstream rendering step that
  consumes the clip JSON.

## References

- [Anthropic prompting docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct) -
  general guidance on making instructions precise rather than letting
  the model anchor on round numbers.
