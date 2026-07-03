---
name: stale-lock-shell-guard-skips-scheduled-phase
description: |
  Diagnose and fix a scheduled job (launchd/cron) that SILENTLY skips its most
  important gated phase for days because an outer shell guard is cruder than the
  inner lock logic it gates. Use when: (1) a daily/periodic job's log shows the
  same "<X> writer active -> skip" (or "locked -> skip") line every run while the
  work never actually happens, (2) the lockfile holds a PID that is dead
  (`ps -p <pid>` / `kill -0 <pid>` fail) and no matching writer process is
  running, (3) the job still exits 0 so nothing alerts and the partial-completion
  hides for days/weeks, (4) a shell wrapper tests `[ -f some.lock ]` to decide
  whether to skip, but the program it launches already auto-clears a stale lock
  on open. Root cause: TWO layers guard the same resource and the outer/cruder
  one (mere file existence) defeats the inner self-healing one (PID-aware) before
  it can run. Fix: make the shell guard PID-aware to match the layer it gates,
  AND make gated phases record per-phase outcomes + exit non-zero / notify so a
  silent skip cannot recur. Distinct from council-mcp-over-http-and-ladybug-writer-lock
  (a LIVE writer blocking graph READS) and embedded-db-crash-shadow-wal-blocks-reopen
  (shadow/WAL temps blocking DB REOPEN).
author: Claude Code
version: 1.0.0
date: 2026-06-24
---

# Stale lock + a cruder outer guard silently skips a scheduled phase

## Problem

A scheduled job runs fine, exits 0 every time, and yet one of its phases has not
actually executed for days. The phase is gated behind a lockfile check so it
won't collide with a concurrent writer. A previous writer crashed and left a
**stale lockfile** (it just holds a PID). The job's guard tests only whether the
file *exists*, so it skips the phase on every fire - even though no writer is
running and the PID in the lock is long dead. Because the job still exits 0, no
alert fires and the silent partial-completion goes unnoticed.

The trap is a **two-layer guard mismatch**: the program the job launches is
already smart about stale locks (it reads the PID, checks liveness, and
auto-clears a dead-PID lock on open), but the **outer shell guard never lets it
run** - it short-circuits on `[ -f lock ]` first. The cruder outer guard defeats
the self-healing inner one.

## Context / Trigger conditions

- A periodic job (launchd `StartCalendarInterval`, cron) whose log shows the same
  skip line every run, e.g. `--- graph writer active -> skip ... ---`, while the
  downstream artefact (graph, index, export) never updates.
- The lockfile holds a PID and `ps -p <pid>` / `kill -0 <pid>` show it is **dead**;
  `pgrep -f <writer>` finds **no** running writer.
- The job exits 0 (the skip is a "successful" no-op), so monitoring/alerts stay
  quiet and the gap persists for days.
- The guard is a shell `if ... || [ -f "$LOCKFILE" ]; then skip; fi` while the
  launched program (Python/Go/etc.) already has PID-aware lock acquisition that
  auto-clears stale locks.

## Solution

### 1. Confirm it's a stale lock, not a live writer
```sh
cat path/to/resource.lock            # the PID
ps -p <pid> || echo "DEAD (stale)"   # dead => stale
pgrep -fl '<writer-process-pattern>' || echo "(no writer running)"
grep -c 'skip' logs/job-*.log        # how many consecutive runs skipped
```

### 2. Recover now (one-off)
Remove the stale lock so the next run proceeds. If the resource is a DB with a
sidecar WAL, do a clean open/close so the WAL is replayed/checkpointed rather
than deleting it blind (see embedded-db-crash-shadow-wal-blocks-reopen). Back up
first if the artefact is irreplaceable.

### 3. Make the outer guard as smart as the inner one (prevent recurrence)
Replace `[ -f lock ]` with a PID-aware check that mirrors the program's own lock
logic, so a stale lock no longer skips the phase (the program then auto-clears it
on open):
```sh
# succeeds only if the lock exists AND holds a live PID
lock_is_live() {
  _l=$1
  [ -f "$_l" ] || return 1
  _p=$(tr -d '[:space:]' < "$_l" 2>/dev/null)
  case "$_p" in ''|*[!0-9]*) return 1 ;; esac   # empty/non-numeric -> stale
  [ "$_p" -gt 0 ] 2>/dev/null || return 1
  kill -0 "$_p" 2>/dev/null || ps -p "$_p" >/dev/null 2>&1  # ps -p covers EPERM
}
# skip ONLY on a real running writer OR a live-PID lock; a stale lock proceeds.
if writer_running || lock_is_live "$LOCKFILE"; then skip; else run_phase; fi
```

### 4. Make a silent skip impossible to miss
A gated phase that no-ops quietly is worse than one that fails loudly. Add:
- per-phase outcome tracking (`ran` / `skipped(reason)` / `failed`) and a final
  STATUS SUMMARY in the log;
- a non-zero exit when a phase genuinely fails (not when it legitimately skips for
  a live writer);
- an alert on failure or on stale-lock-clear (e.g. macOS
  `osascript -e 'display notification ...'`, guarded by `command -v osascript`).

## Verification

- After clearing the lock, the next manual/scheduled run executes the phase (the
  log shows the phase body, not the skip line) and the artefact updates.
- Unit-test the PID-aware guard: missing / empty / non-numeric / dead-PID lock ->
  not live (phase proceeds); live PID -> live (phase skips). A dead PID for tests:
  `( exit 0 ) & p=$!; wait "$p"` then `$p` is reaped/dead.
- Confirm the job now exits non-zero (and notifies) on an injected phase failure.

## Example

council-of-thinkers `scripts/daily_ingest.sh` (launchd 10:00). The phase-4 graph
build was guarded by:
```sh
if pgrep -f '...writer...' >/dev/null || [ -f "$PROJ/ladybugdb/council.cot.lock" ]; then
  echo "--- graph writer active -> skip ... ---"; else ...graph phase...; fi
```
A writer crashed on 18 Jun leaving `council.cot.lock` (PID 35299, dead). For 6
days every 10:00 run logged `graph writer active -> skip` and skipped diarise +
concept-extract, while steps 1-3 (download/embed) kept running - so new 20VC
episodes were searchable text but never entered the concept graph, and the job
exited 0 the whole time. The Python `concept_graph._acquire_lockfile` *already*
auto-clears a dead-PID lock, but the shell skipped before Python ran. Fix:
`graph_lock_is_live()` (PID-aware, `kill -0`/`ps -p`) replaced `[ -f lock ]`, plus
a STATUS SUMMARY, non-zero exit on failure, and an osascript alert on
failure/stale-lock-clear.

## Notes

- **Generalisable principle**: when two layers guard the same resource, audit the
  OUTER/cruder one - it can silently defeat an inner self-healing layer. Keep the
  outer guard's staleness logic at least as smart as the inner one, or drop the
  outer file-existence test entirely and let the inner layer arbitrate.
- A launchd job with `RunAtLoad=false` + `StartCalendarInterval` and no
  `KeepAlive` will not relaunch when you kill a wedged chain; it next runs at its
  scheduled time, so manual recovery is safe.
- `kill -0` fails with EPERM for a live process owned by another user; fall back
  to `ps -p` so you err on "alive" (don't clear someone else's lock). Mirror
  whatever the inner layer does (e.g. Python `os.kill(pid, 0)` treating
  PermissionError as alive).
- Related: council-mcp-over-http-and-ladybug-writer-lock (manual removal when a
  LIVE writer blocks graph reads); embedded-db-crash-shadow-wal-blocks-reopen
  (shadow/WAL temps blocking DB reopen); pipe-masks-exit-code-in-gated-chains
  (another "job exits 0 while a step failed" trap).
