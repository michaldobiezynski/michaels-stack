---
name: classifier-failure-vs-negative-bucket
description: |
  Anti-pattern + fix for LLM/heuristic classifier or extractor pipelines that
  fold CALL FAILURES (timeout, non-zero exit, empty/garbage output) or MODEL
  HEDGES ("I cannot determine...") into the SAME output bucket as a genuine
  negative result, making a total outage indistinguishable from a real
  "all-negative" answer. Use when: (1) a batch classify/extract step reports
  every item in one benign bucket (e.g. "0 guests found / 132 'no single
  guest'", "0 matches", "all clean", "0 to enrol"); (2) you are about to write
  `except SomeError: return DEFAULT_CLASS`; (3) a report's count for the
  no-op/negative class equals the total item count; (4) an LLM-from-title /
  from-description extraction silently produced uniform output; (5) model
  refusal prose is being stored as if it were extracted data. Fix: give every
  non-answer its own kind (error / unsure / genuine-negative), surface failures
  loudly, and shape-guard free-text values so hedges can't pass as data.
author: Claude Code
version: 1.0.0
date: 2026-05-30
---

# Don't fold classifier failures into the negative bucket

## Problem

A pipeline classifies or extracts per item by calling an LLM (or a heuristic)
in a subprocess / thread pool, and the handler maps *any* non-positive outcome
to a single benign class:

```python
try:
    guest = call_llm(title)              # subprocess.run(..., check=True)
except (TimeoutExpired, CalledProcessError):
    guest = "UNKNOWN"
...
if guest.upper() in ("NONE", "UNKNOWN", ""):
    no_guest.append(ep)                  # <-- failures land here too
else:
    by_guest[guest].append(ep)
```

Now a **total outage** (rate-limit burst, auth blip, every call timing out)
produces output identical to a real "every item is negative" result. In one
real case all 132 ingested episodes were reported as "no single guest / no
sample needed" — not because none had a guest, but because every LLM call had
failed and been swallowed. The report read as *finished work with nothing to
do*; it was a silent 100% failure.

A second leak: when the model is unsure it often returns a **hedge sentence**
("I cannot identify the guest from the title alone...") instead of your
sentinel. Naive `stdout.splitlines()[0]` parsing stores that whole sentence as
a "value" — a guest name, a category, a filename slug named after a paragraph.

## Context / Trigger conditions

- A batch classify/extract report shows the no-op/negative count == total count
  ("0 positive / N negative", "0 matches", "all clean", "0 to enrol").
- You are writing `except SomeError: return <a normal output value>`.
- LLM extraction over many items produced suspiciously uniform output.
- Free-text model output is being persisted without a shape/format check.
- A "nothing to do" result feels too convenient given the input obviously
  contains positives.

## Solution

1. **Give every non-answer its own kind.** At minimum: `positive` (value),
   `negative` (a *real* none/no/clean), `unsure` (the model answered but
   couldn't decide — distinct from negative), `error` (the call itself failed).
   Return a `(kind, value)` tuple, not an overloaded string.

   ```python
   def classify(item) -> tuple[str, str]:
       try:
           proc = subprocess.run(cmd, ..., check=True, timeout=120)
       except FileNotFoundError:
           return "error", "CLI not on PATH"
       except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
           return "error", str(e)[:200]
       reply = parse(proc.stdout)
       if not reply:                 return "error", "empty reply"
       if reply.upper() == "NONE":   return "negative", ""
       if reply.upper() == "UNKNOWN" or not _looks_like_value(reply):
           return "unsure", ""
       return "positive", reply
   ```

2. **Never map an exception to a normal output value.** `error` is its own
   terminal kind, routed to its own bucket. Retry transient errors, but a
   retried-out failure is still `error`, never `negative`.

3. **Shape-guard free-text values.** Before accepting an LLM string as data,
   check it looks like what you asked for (a name = 1-5 tokens, no `:?()`, not
   ending in a full stop, not starting with "I cannot / I need / Sorry").
   Coerce anything that fails to `unsure`, not to a value.

4. **Surface failures loudly in the output.** Render `error`/`unsure` in their
   own sections with a banner ("N failed — NOT classified, re-run"), so a
   reader can never mistake "we couldn't tell" for "the answer is negative".
   Assert/log that the bucket counts sum to the item count.

5. **Give the model the right escape hatch in the prompt.** Tell it to reply
   with a distinct token when it genuinely can't decide ("reply UNKNOWN") so
   you route hedges to `unsure` instead of guessing or storing prose.

## Verification

- Force a failure (point the CLI at a bad model, kill the network, set a
  1ms timeout) and confirm the item lands in `error`, not the negative bucket,
  and the report warns.
- Feed a known-positive item and confirm it is not swallowed.
- Confirm the report's bucket counts sum to the total and the negative count is
  plausible, not suspiciously equal to the total.

## Notes

- Sibling lesson: the `audit-cheap-output-before-expensive-downstream-step`
  skill — both are about not trusting a stage that "ran successfully" at face
  value. This one is specifically about result-routing: a successful *run* with
  a swallowed *failure* still corrupts the downstream worklist.
- Applies to heuristic classifiers (regex, thresholds, fuzzy match), not just
  LLMs — any code path where "couldn't decide" and "decided no" share a return.
- Real instance: council-of-thinkers `scripts/report_guest_samples.py` (May
  2026), which silently bucketed all ingested 20VC episodes as "no single
  guest" when the `claude -p` calls failed under load. Pairs with the
  `claude-p-subscription-subprocess` skill for the hardened call itself.
