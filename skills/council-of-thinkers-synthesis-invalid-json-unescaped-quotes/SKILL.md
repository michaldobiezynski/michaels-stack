---
name: council-of-thinkers-synthesis-invalid-json-unescaped-quotes
description: |
  Fix/triage for the council-of-thinkers `synthesise_council` MCP tool
  failing with "claude -p result is not valid JSON, even via regex
  fallback (Expecting ',' delimiter: line N column M (char K))". Use
  when: (1) `mcp__council-of-thinkers__synthesise_council` raises this
  RuntimeError while `query_council` on the same topic works fine,
  (2) the error's "First 500 chars" preview shows a `{"type":"p",
  "html":"..."}` block whose prose contains straight double-quotes
  around an inner quotation (e.g. forward reasoning — "this is true and
  therefore" — but...), (3) you need synthesis output now and want the
  reliable workaround, or (4) you want to harden the pipeline so it stops
  recurring. Root cause: `claude -p` emits an `html` field value with
  UNescaped inner double-quotes; `json.loads` breaks at the first one,
  and the regex fallback in `_parse_blocks_with_fallback`
  (council_mcp/llm.py) only strips preamble/trailing prose, so it cannot
  repair malformed content inside the array. Verified workaround: retry
  once. Does NOT cover the synthesis share_url 404 issue (separate skill)
  or rate-limit errors.
author: Claude Code
version: 1.0.0
date: 2026-05-26
---

# Council synthesis: invalid JSON from `claude -p` (unescaped inner quotes)

## Problem

`mcp__council-of-thinkers__synthesise_council` intermittently fails with:

```
Error calling tool 'synthesise_council': claude -p result is not valid
JSON, even via regex fallback (Expecting ',' delimiter: line 3 column 142
(char 205)). First 500 chars: '[\n  {"type": "h2", "text": "..."},\n
{"type": "p", "html": "Rory Sutherland ... forward reasoning — "this is
true and therefore" — but ...'
```

The same topic retrieved via `query_council` succeeds, so retrieval is
fine; only the synthesis step (which runs the LLM through `claude -p`,
Pattern 2 subscription billing) blows up.

## Context / trigger conditions

- The tool returns a `RuntimeError`, not a synthesis payload.
- The error text contains `not valid JSON, even via regex fallback` and a
  `json.JSONDecodeError`-style position (`Expecting ',' delimiter`,
  `Expecting property name`, `Unterminated string`, etc.).
- The `First 500 chars:` preview shows a block of shape
  `{"type": "p", "html": "... "inner quote" ..."}` where the inner
  quotation marks are plain `"` and are **not** escaped as `\"`.

## Root cause

The synthesis prompt asks `claude -p` for a JSON array of block dicts,
some carrying an `html` field of rendered prose. The model sometimes
writes in-prose quotations with straight ASCII double-quotes and forgets
to escape them, e.g.:

```json
{"type": "p", "html": "He argues that society prizes "forward reasoning" but ..."}
```

That closes the string early, so `json.loads` fails at the inner quote.

The fallback does not save it. In `council_mcp/llm.py`,
`_parse_blocks_with_fallback` (around line 176):

1. tries `json.loads(cleaned)` — fails;
2. extracts the outermost `[...]` with a greedy DOTALL regex
   (`_JSON_ARRAY_RE`) — this was added for issue #8 to strip model
   preamble (`Here's the answer: [...]`) and trailing prose
   (`[...]\nHope that helps!`);
3. tries `json.loads` on that slice — **still fails**, because the regex
   only removes text *around* the array; it cannot repair invalid content
   *inside* it.

So the fallback is solving a different problem (surrounding prose), not
unescaped quotes, and re-raises with the 500-char preview.

## Solution

### Immediate (verified)

Call `synthesise_council` again with the same arguments. The failure is
per-generation: on retry the model usually re-emits the quotation as
escaped `\"` (or as typographic quotes), producing valid JSON. Observed
directly — a call that failed at `char 205` succeeded on the very next
attempt, with the passage rendered as `\"this is true and therefore\"`.
One retry is normally enough; cap at 2 to avoid loops.

### Durable fixes (suggested, ranked — not yet verified in code)

1. **Prompt-side (highest leverage).** In the synthesis prompt that
   builds the `html` blocks, instruct the model to write in-prose
   quotations with typographic quotes (`"` `"`, i.e. `“`/`”`)
   or the HTML entity `&quot;`, and to reserve straight `"` for JSON
   structure only. Both render correctly in HTML *and* are valid inside a
   JSON string, so the ambiguity disappears at the source.
2. **Self-heal in the tool.** Wrap the synthesis `claude -p` call
   (`claude_p_llm_fn` in `council_mcp/llm.py`) in a bounded retry (up to
   ~2 attempts) on `RuntimeError`/`JSONDecodeError` before surfacing the
   error, so the MCP tool recovers without the caller re-invoking.
3. **Parser hardening (partial).** Replace the regex fallback with a
   tolerant repair such as the `json-repair` PyPI package. Caveat:
   mid-string unescaped quotes are genuinely ambiguous (the parser cannot
   know where the string was meant to end), so repair libraries only
   partially mitigate this class; prefer fix #1.

## Verification

- Re-run the tool; a valid payload returns with `id`, `share_url`, and
  `blocks`, and the offending passage now shows escaped or typographic
  quotes.
- If you applied fix #1, run several syntheses on quote-heavy topics
  (Sutherland "think backwards", Munger "invert") and confirm no
  `not valid JSON` errors recur.

## Notes

- Separate from `council-of-thinkers-synthesis-share-url-404` (that is a
  rendering 404 *after* a successful synthesis); here synthesis never
  returns a payload at all.
- A retry changes which chunks the synthesis reranks/cites, so the cited
  speaker set can differ run to run. If you are auditing speaker
  diversity, trust `query_council` (raw retrieval) for the canonical
  set, not a single synthesis run — they use different `top_k` and query
  phrasing and can cite different subsets.
- Distinct from the `claude -p envelope is not valid JSON` error, which
  is about the CLI's own `--output-format json` envelope (`proc.stdout`),
  not the model's inner content.
