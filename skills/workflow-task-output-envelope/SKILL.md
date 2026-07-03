---
name: workflow-task-output-envelope
description: |
  How to programmatically read a Claude Code Workflow's result from its
  task-notification output file. Use when: (1) a <task-notification> for a
  Workflow points at an .output file and you need the returned data in a
  script (jq/python), (2) your parse "succeeds" but yields 0 records or dict
  keys instead of rows, (3) you grabbed the first list in the file and got
  `logs` entries instead of results, (4) some entries are null. The file is
  NOT the workflow's return value: it is an envelope
  {summary, agentCount, logs, result} — read ["result"], and filter nulls
  (each failed parallel slot resolves to null).
author: Claude Code
version: 1.0.0
date: 2026-06-10
---

# Workflow task-output files are envelopes, not return values

## Problem
A background Workflow completes and the harness writes its outcome to the
path in `<task-notification><output-file>`. Loading that file and treating it
as the workflow's return value silently mis-parses: iterating it walks the
envelope's dict keys; heuristically taking "the first list value" returns
`logs` (narrator lines), not data. Both failure modes look like "the workflow
returned nothing" when it actually returned 1,600+ records.

## Context / Trigger conditions
- `json.load(f)` gives a dict with keys `summary`, `agentCount`, `logs`,
  `result` instead of your expected array/object.
- A loop over "rows" produces counts of 0, or rows like strings from `logs`.
- Your workflow used `parallel()` and one slot failed: the notification shows
  a `<failures>` block AND the corresponding entry inside `result` is `null`
  (a flattened batch contributes nothing; a top-level slot contributes a
  literal null).

## Solution
```python
import json
env = json.load(open(output_file))      # the ENVELOPE
data = env["result"]                     # the workflow's actual return value
rows = [r for r in data if isinstance(r, dict)]   # drop failed-slot nulls
```
With jq: `jq '.result' file` (and `jq '.result | map(select(. != null))'`).

Reconcile counts afterwards: `len(rows)` vs the expected item count tells you
exactly how many items the failed slot(s) dropped; recover those by re-running
only the missing inputs (diff against your original input list by id), not the
whole workflow.

## Verification
`jq -r 'keys' <file>` shows the envelope keys; `jq '.result | length'` matches
the workflow's logical return size (plus nulls for failed slots).

## Example
A 22-batch classification workflow returned 1,681 entries in `result` (1,680
dicts + 1 null from the one batch whose agent never called StructuredOutput).
First parse iterated the envelope dict (0 rows); second took the first list
value, which was `logs` (len 2). Correct parse: `env["result"]`, filter dicts,
diff ids against the input manifest -> 36 missing -> reclassified just those.

## Notes
- The `<result>` block inline in the task-notification is a TRUNCATED preview
  of the same data; for anything large, always read the output file.
- Synchronous Workflow tool-results (not backgrounded) return the value
  directly; the envelope applies to the background/task path.
- Related: large Bash outputs are similarly persisted to a file with a
  "persisted-output" notice; same discipline — probe structure before parsing.
