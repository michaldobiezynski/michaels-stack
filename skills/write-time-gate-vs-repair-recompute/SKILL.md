---
name: write-time-gate-vs-repair-recompute
description: |
  When adding a write-time gate/filter that makes a derived value (denormalised
  counter, aggregate edge, cached strength) deliberately diverge from a raw
  recount of its source data, audit EVERY repair/reconcile/sync/backfill path
  that recomputes that value from raw counts - they silently undo the gate.
  Use when: (1) implementing any rule of the form "only bump X when condition C"
  while X also has a "heal drift" / "reconcile counters" / "sync edges" job,
  (2) a gated/suppressed value mysteriously reappears or re-inflates after a
  maintenance run, (3) reviewing a PR that gates writes but only adds docstring
  WARNINGs to repair helpers, (4) a no-op invocation of a propagation/repair
  function creates edges or counters that extraction deliberately withheld.
  Covers the audit recipe, the guard pattern (skip + loud warning + skip
  counters + injectable id set), and why docstring warnings alone fail.
author: Claude Code
version: 1.0.0
date: 2026-06-11
---

# Write-Time Gates Are Silently Undone by Repair-Path Recomputes

## Problem

A write-time gate makes a derived value deliberately diverge from "count of
raw records". But systems with denormalised values almost always also have
repair paths (reconcile counters, sync edges, propagate changes, heal drift)
whose entire job is to force derived == raw recount. After the gate ships,
those paths stop being repairs and become corruption: they re-inflate or
re-create exactly what the gate withheld, silently, under the banner of
routine maintenance.

Before the gate, `derived == recount(raw)` was the system invariant the
repair paths correctly enforced. The gate CHANGES the invariant (derived ==
recount(raw WHERE condition)) - so every enforcer of the old invariant is now
wrong, not just "something to warn about".

## Context / Trigger Conditions

- You are gating a counter/edge/aggregate bump on a condition (role, stance,
  status, quality tier) while the raw records (mentions, events, rows) are
  still written unconditionally.
- The codebase contains functions named like `reconcile_*`, `sync_*`,
  `heal_*`, `propagate_*`, `backfill_*`, or scripts described as
  "idempotent: re-runs over consistent data fix nothing".
- A gated value reappears after a maintenance run that "shouldn't have
  changed anything" (the canonical reproduction: a NO-OP call to the
  propagation function re-creates the withheld edges).
- Code review shows the gate PR added only docstring WARNINGs to the repair
  helpers.

## Solution

1. **Find every recompute site**: grep for the derived field name being SET
   or CREATEd outside the gated write path (e.g. `strength =`, `count =`,
   `CREATE ...{strength:`). Check helpers AND the operator-facing entry
   points that compose them (the entry point is what runbooks tell people to
   run; warning only the internal helper protects nobody).
2. **Prove the failure empirically** before fixing: in a test fixture, do a
   gated write, then run each repair path (including a no-op invocation of
   the composite entry point) and assert the gated state survives. Watch it
   fail.
3. **Add a runtime guard, not a docstring**: the repair functions take an
   injectable exclusion set (e.g. `host_ids: set[str] | None = None`)
   defaulting to a lazy lookup of the gate's config; they SKIP excluded
   pairs, count skips in the returned stats, and `logger.warning` when the
   skip count is non-zero. Operator scripts print the skip count.
4. **Mind the asymmetry**: deletes of zero-raw-count derived values usually
   remain correct for gated entities (no raw records means no value
   regardless of the gate); creates and strength-resets are what must skip.
5. **Skipping is conservative, not complete**: a skipped pair can no longer
   be healed for GENUINE drift either. File a follow-up to persist the gate
   decision on the raw records (a flag on each record/edge) so repair can
   recompute `derived = count(raw WHERE flagged)` instead of skipping; until
   then the gate decision exists only in code + config, indistinguishable
   from drift. ACTUALLY FILE IT - a "follow-up issue" promised in a PR body
   and never filed is a classic adversarial-review finding.
6. **Update the operator surface**: any log message or runbook that says
   "run the reconciliation pass to fix" must mention the gate caveat, and
   exact-shape test assertions on the repair functions' return dicts need
   the new skip counters.

## Verification

Characterisation tests: (1) gated write -> run each repair path -> gated
state unchanged, skip counters correct; (2) non-gated entity with manually
injected drift -> repair still heals it; (3) no-op invocation of the
composite entry point -> nothing resurrected; (4) the exclusion set's
default resolves from the gate's real config (monkeypatch the config
loader).

## Example

council-of-thinkers #147: ESPOUSES strength bumps were gated for host-role
speakers (only first-person commitments count), but MENTIONS edges are
written unconditionally. `reconcile_counters` and
`_sync_espouses_create_delete` recompute strength = MENTIONS count, and
`propagate_diarisation_to_graph` (the documented "$0" diarisation runbook
step) composes both - so a no-op propagate call re-created every withheld
host edge at full raw count. Fixed with `host_ids` skip-and-warn guards in
all three (PR #205), persistence follow-up filed as #207.

## Notes

- The same trap applies beyond graphs/counters: cache rebuilds vs
  invalidation rules, search-index rebuilds vs suppression flags, ETL
  backfills vs filtered loads.
- "Idempotent" claims in repair-script docstrings are invariant statements;
  re-check them whenever the invariant changes.
