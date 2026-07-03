---
name: rag-honesty-flag-for-default-labelled-data
description: |
  Pattern for RAG / citation / quote systems whose corpus contains records labelled
  with a DEFAULT or placeholder attribute that is often wrong, where re-labelling the
  data is expensive or a separate effort. Use when: (1) a consumer (an LLM answer, a
  UI, a citation) asserts a stored label as fact and it is wrong - e.g. every chunk of
  an interview show is labelled the HOST because per-speaker diarisation never ran, so
  guests' words are attributed to the host; (2) you are tempted to re-process/re-label
  the whole corpus to fix attribution but cannot do it now; (3) you need the system to
  stop over-claiming without losing the records. Covers surfacing a per-record
  reliability flag derived from signals you ALREADY have, the critical gate that stops
  it over-flagging the correct majority, wiring it through every citation path, and
  telling the model to hedge. Verified on the council-of-thinkers / Sapiens Locus MCP.
author: Claude Code
version: 1.0.0
date: 2026-06-23
---

# RAG honesty flag for default-labelled data

## Problem

Part of a retrieval corpus is labelled with a DEFAULT value that is frequently wrong:
an interview channel ingested without per-speaker diarisation labels EVERY chunk the
host, so a guest's words carry the host's name. A downstream consumer - an LLM writing
an answer, or a UI rendering a citation - then asserts that label as fact ("Harry
Stebbings said X") when it was actually a guest. Re-labelling the data correctly
(re-diarising) is expensive and a separate effort.

The wrong instinct is to block on fixing the data. The right move is to make the system
HONEST about what it does not know, at the presentation layer, using signals already on
each record.

## Context / Trigger conditions

- A stored attribute (speaker, author, source, category) was assigned by a default/config
  rule rather than verified, and you can tell verified-vs-default per record.
- Citations / answers confidently state that attribute and users report misattribution.
- The "obvious" fix (reprocess the corpus) is out of scope for the current change.
- You already have, on each record, a verification-status signal (e.g.
  `attribution_method in {config, diarized}`, a confidence score, a `verified` bool) -
  it is just not surfaced to the citation layer.

## Solution

1. **Derive a small, consumer-facing reliability enum** from signals already present -
   do NOT re-process data. e.g. `speaker_attribution in {verified, default-suspect, default-ok}`.

2. **GATE it so it only fires on the genuinely-unreliable subset** (the key, non-obvious
   step). "Un-verified" alone OVER-FLAGS: a single-speaker source assigned by config is
   un-verified but correct. Combine the verification-status signal with a second signal
   that isolates the FAILURE MODE:
   - verified (e.g. diarised) -> trust, regardless of anything else.
   - un-verified AND the default label is one that only makes sense for a multi-party
     source (e.g. the label is a declared *host*) -> `default-suspect` (unreliable).
   - un-verified AND the label is the sole/expected speaker (solo feed) -> `default-ok`
     (reliable; NOT flagged).
   This gate is what keeps you from crying wolf on the correct majority.

3. **Compute it in ONE canonical projection** and wire it through EVERY path that emits
   a citation. Audit them all: the search path (usually carries all columns), any
   column-whitelist fetch path (the easy one to miss - add the raw signal to the
   whitelist), and any projected->raw shim that feeds a second builder (forward the raw
   signal so the second builder re-derives identically).

4. **Instruct the consumer to hedge.** Update tool/prompt docstrings: "if the flag is
   `default-suspect`, attribute the quote to the SHOW, not the named person, unless
   independently certain." A flag nothing acts on is dead weight.

5. **Keep it additive.** The new field on the citation/payload shape should be additive so
   existing consumers and persisted records tolerate it.

## Verification

- A default-labelled record on a multi-party source comes back `default-suspect`.
- A verified record comes back `verified` regardless of role.
- A solo / sole-speaker un-verified record comes back `default-ok` (NOT flagged) - prove
  this explicitly, it is the over-flagging guard.
- A partial record missing the verification signal defaults to the SAFE (suspect) value.
- The flag is present on outputs from every citation tool, including the by-id fetch path.

## Example (council-of-thinkers / Sapiens Locus)

20VC (host: Harry Stebbings) was ingested with every chunk labelled the host, no
diarisation. Chunks already carried `attribution_method` (`config` un-diarised ->
`diarized` after diarisation) and `speaker_id`; `speakers.yaml` declares `role: host`.

```python
def speaker_attribution(attribution_method, speaker_id, *, host_ids):
    if (attribution_method or "config").lower() == "diarized":
        return "diarised"                  # verified -> trust
    if speaker_id and speaker_id in host_ids:
        return "channel-default"           # un-diarised host label -> suspect
    return "config"                        # un-diarised solo speaker -> reliable
```

Wired through the single `_project_chunk` projection, `build_clips_dict`, the
`_projected_to_raw` shim (forward BOTH the derived flag and the raw `attribution_method`),
and `_CHUNK_PROJECT_COLS` (the by-id whitelist). Tool docstrings tell the model to
attribute `channel-default` quotes to the show, not the host. Result: guest quotes stop
being asserted as the host's, while Naval's solo clips (config, non-host) are NOT
over-flagged.

## Notes

- The over-flagging gate (step 2) is the whole game. Without the second signal you flag
  everything un-verified and the warning becomes noise users learn to ignore.
- Surfacing a raw signal alongside the derived flag (here `attribution_method`) lets the
  second builder re-derive identically and keeps the flag honest if the derived value is
  ever absent.
- Test the projected->raw forwarding NON-tautologically: pick a forwarded value that
  DIVERGES from what re-derivation would produce, so removing the forwarding line goes
  RED. See [[atdd-regression-test-tautology-detection]].
- This complements [[url-base-env-derivation-traps]] (same PR): both are "make the edge
  case honest instead of silently wrong".
- The clean fix is presentation-layer; the data-level fix (re-labelling) remains a
  separate, trackable effort - file it, don't conflate it.
