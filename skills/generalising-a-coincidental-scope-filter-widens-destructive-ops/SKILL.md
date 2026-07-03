---
name: generalising-a-coincidental-scope-filter-widens-destructive-ops
description: |
  When you GENERALISE code by removing a hardcoded scope filter (e.g. `WHERE name
  LIKE '20VC%'`, `== {"some_specific_id"}`, `if channel == "X"`), audit what the
  now-broader predicate ADMITS into any downstream destructive or unattended
  path - the narrow filter was often silently enforcing a precondition you didn't
  realise. Use when: (1) a PR/diff replaces a literal-scoped query or condition
  with a general one ("works for any host/tenant/type, not just the hardcoded
  one"), (2) the generalised set feeds an irreversible op (hard delete, overwrite,
  relabel, migration) OR an unattended one (cron/daily job), (3) reviewing such a
  change, ask "what new rows does this now match that the old literal excluded,
  and is each safe for the downstream action?". Root cause: a coincidental filter
  (added for a different reason, e.g. perf or the-only-data-that-existed) doubles
  as a guard; removing it for generalisation drops the guard. Fix: re-establish
  the REAL precondition explicitly in the predicate (not the incidental literal),
  and add a regression test for the now-admitted-but-unsafe case.
author: Claude Code
version: 1.0.0
date: 2026-06-25
---

# Generalising a hardcoded scope filter can silently widen a destructive op

## Problem

You make a 20VC-only tool work for any channel by removing its hardcoded scope:
`episode_id LIKE '20VC%'` and `ep_speakers == {"harry_stebbings"}` become
`ep_speakers == {x["expected"]}` (keyed on each row's own host). Looks like a
clean generalisation. But the OLD filter was also, by accident, the only thing
keeping a whole class of rows OUT of a downstream **hard delete**: episodes from
OTHER speakers that are `multi_speaker:true` with an EMPTY candidate/allowlist.
For those, no reference matches the non-host audio, every cluster resolves to
"unknown", and the relabel path falls through to `table.delete(...)` - run
unattended by a daily cron, with the corpus backup deliberately skipped on the
now-false assumption "this only ever relabels, never drops".

## Context / Trigger conditions

- A diff that removes a literal scope (`LIKE 'X%'`, `== {"specific"}`,
  `if k == "hardcoded"`) to "generalise" / "support any <thing>".
- The selected set feeds: a hard delete / overwrite / destructive migration /
  in-place relabel, OR an unattended path (cron, daily job, batch).
- An adjacent comment or skipped safeguard justifies itself on an assumption the
  old narrow scope guaranteed ("only relabels", "only our data", "always has X").
- Symptom in review: the generalised predicate's intent (per commit messages) is
  about ONE new well-formed case, but the predicate also admits malformed/empty/
  edge rows that were previously filtered out incidentally.

## Solution

1. **Diff the admitted SET, not just the code.** Run the old vs new predicate
   against real data and list exactly the rows the new one ADDS. (Here: 13 -> 34
   pending; the 21 added included 6 empty-allowlist episodes the `'20VC%'` filter
   had excluded.)
2. **For each newly-admitted row, trace it to the downstream action.** Is it safe
   to hard-delete / overwrite / relabel? Empty-allowlist -> drop was not.
3. **Re-establish the REAL precondition explicitly.** The literal was a proxy;
   name the actual requirement. Here: an episode is safe for unattended relabel
   only if it has an enrolled guest -> add `len(allowlist) > 1` to the predicate
   (factor it into a tested pure function, e.g. `is_host_only_pending`).
4. **Regression-test the now-excluded unsafe case** (empty allowlist -> not
   pending) AND the backward-compat case (the original literal's rows still
   selected). A new guard test must be seen to matter.
5. **Re-read any safeguard the old scope justified** (the skipped backup, a
   "can't happen" branch) and update its rationale or restore it.

## Verification

- old-predicate set vs new-predicate set diff is the intended additions ONLY;
  every addition is safe for the downstream op.
- A unit test asserts the unsafe class is excluded and the original class retained.
- The destructive/unattended path can no longer reach the unsafe rows.

## Example

council-of-thinkers PR #254: generalising `diarize_pending.py` from
`LIKE '20VC%'` + `== {'harry_stebbings'}` to per-episode `== {expected}` made the
daily cron able to diarise any host - but also admitted munger/sutherland
empty-`multi_speaker_candidates` episodes whose guest clusters resolve to None and
hit `lance.relabel_and_drop_episode`'s hard `table.delete` (~361 chunks),
unattended, backup-skipped. Two-round review caught it (HIGH). Fix:
`is_host_only_pending(expected, ep_speakers, allowlist)` adds `len(allowlist) > 1`;
live-data diff confirmed 0 empty-allowlist episodes admitted while all 28 intended
(13 harry_stebbings + 14 david_senra_host + 1 other) were retained; regression
test added.

## Notes

- The tell: the removed filter was added "for a different reason" (perf, or it was
  the only data that existed). Coincidental filters silently encode invariants.
- Highest stakes when the downstream op is BOTH irreversible AND unattended; a
  dry-run / human gate that the generalisation bypasses (here the daily uses the
  live driver, not the `--dry-run`-first one) removes the last backstop.
- Pair with adversarial review against REAL data, not just unit fixtures - the
  6 dangerous episodes only show up when you run the predicate over the corpus.
