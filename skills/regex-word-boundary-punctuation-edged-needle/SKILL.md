---
name: regex-word-boundary-punctuation-edged-needle
description: |
  A regex built as \b + re.escape(needle) + \b can NEVER match when the
  needle's first or last character is a non-word character (trailing ./?/!,
  wrapping quotes, parentheses, leading #/@) - \b requires a word-char/
  non-word-char transition, and escape makes the edge char part of the
  pattern, so the boundary sits between two non-word chars and fails. Use
  when: (1) upgrading a substring find() to word-bounded matching for
  precision and matches silently disappear for some needles, (2) needles
  come from model/LLM output, user text, or scraped spans (they routinely
  carry punctuation edges - measured 18.7% of stored extraction spans),
  (3) a fallback path (whole-text match, broader heuristic) is silently
  taken instead and behaviour degrades without errors, (4) tests pass
  because fixtures only use clean alphanumeric needles. Fix: strip non-word
  edges from the needle (re.sub(r'^\W+|\W+$', '', needle)) before wrapping,
  skip if empty; or use lookarounds (?<!\w)...(?!\w) when the edge chars
  must be kept.
author: Claude Code
version: 1.0.0
date: 2026-06-11
---

# `\b` + Escaped Needle Silently Never Matches Punctuation-Edged Needles

## Problem

Replacing `text.find(needle)` with `re.search(r"\b" + re.escape(needle) +
r"\b", text)` to stop substring false-positives ('ai' matching inside
'said') introduces the OPPOSITE silent failure: any needle whose first or
last character is a non-word character can never match anything. `\b`
asserts a `\w`/`\W` transition; with `needle = 'imposed from the outside.'`
the trailing `\b` must sit between `.` and whatever follows - two non-word
characters - so the assertion fails everywhere, even when the needle is
verbatim in the text.

The failure is invisible: no exception, just zero matches, and the code's
fallback branch (whole-text heuristic, broader window, "not found")
silently takes over.

## Context / Trigger Conditions

- Needles originate from LLM-emitted spans, user input, titles, or scraped
  text - these routinely end in `.`, `?`, `!`, or arrive quote-wrapped.
  In the motivating case, 18.7% of 49,815 stored extraction spans had a
  non-word edge char (5,136 trailing `.`, 3,423 quote-wrapped, 649 `?`).
- A precision fix (boundary matching) was just added and a downstream
  metric quietly regressed only for some inputs.
- The full test suite stays green because fixtures use clean needles
  ('leverage', 'crypto') - the bug class only fires on dirty real data.

## Solution

Strip non-word edges from the needle before wrapping, and treat an
all-punctuation needle as unmatchable:

```python
probe = re.sub(r"^\W+|\W+$", "", needle)
if probe:
    matches = re.finditer(r"\b" + re.escape(probe) + r"\b", text, re.I)
```

Stripping also rescues quote-wrapped needles (the inner text is the part
that is verbatim in the source). If the edge punctuation is semantically
required, use explicit lookarounds instead of `\b`:
`(?<!\w)` + re.escape(needle) + `(?!\w)` - these assert "no word char
adjacent" rather than "transition", so they hold next to punctuation.

## Verification

Unit-test the dirty shapes explicitly (trailing stop, wrapping quotes,
trailing question mark) and, when a corpus exists, MEASURE the edge-char
rate over real needles (`SELECT span ... ; count non-word-edge spans`) -
the 18.7% figure is what turned this from a hypothetical into a blocker.

## Example

council-of-thinkers PR #205: `_stance_for_mention` located a concept's
mention with `\b`-wrapped probes; punctuation-edged model spans never
matched, the function fell back to whole-chunk stance, and ~2.3% of the
host's espousal-gate decisions flipped to false-pass. Caught by an
adversarial review agent that measured the live span corpus; fixed by the
edge-strip above with regression tests for all three edge shapes.

## Notes

- The same trap exists in grep (`grep -w`), JavaScript (`\b` in RegExp),
  and SQL regex dialects.
- The dual failure pair is worth remembering as one lesson: bare
  substring -> false positives inside words; naive `\b` wrapping -> false
  negatives on punctuation edges. Precision fixes need dirty-input tests.
