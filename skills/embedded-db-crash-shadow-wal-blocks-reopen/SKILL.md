---
name: embedded-db-crash-shadow-wal-blocks-reopen
description: |
  Recover an embedded analytical DB (Kuzu/ladybug, DuckDB, LMDB-style) whose
  on-disk temp files block reopen after a hard kill / OS sleep, AND fix the
  related cross-process reopen failure. Use when: (1) opening the DB raises
  "Database ID for temporary file '<db>.shadow' does not match the current
  database" or "Cannot open file '<db>.shadow': No such file or directory" or a
  WAL/checkpoint replay error; (2) a resumable writer loop wedges with the count
  frozen and every read returns an error after a crash/sleep; (3) a process that
  reopens the DB repeatedly (per-batch writer, init-schema-then-write) dies on
  its SECOND open while a single long-lived connection (a server) works fine.
  CHECK THE max_db_size CAP FIRST: in Kuzu/ladybug the poison-shadow + a SIGSEGV
  writer + "Buffer manager exception: No more frame groups can be added to the
  allocator" are usually SYMPTOMS of the database outgrowing the default
  max_db_size (ladybug 0.16.x defaults to 1 GiB / 2**30). Covers: the size-cap
  root cause, which temp files form the recovery SET, why deleting the shadow
  alone makes it worse, and proving data is durable in the main file.
author: Claude Code
version: 1.0.0
date: 2026-06-14
---

# Embedded-DB crash: shadow/WAL temps block reopen

## Problem

An embedded analytical database (Kuzu, its fork **ladybug**, DuckDB, etc.) keeps
crash-recovery temp files next to the main DB file: typically `<db>.wal`,
`<db>.wal.checkpoint`, and a shadow-paging file `<db>.shadow`. Two failure modes
appear after a hard kill, `SIGKILL` mid-checkpoint, or an OS sleep that suspends
a process mid-write:

1. **Won't open at all.** `"Database ID for temporary file '<db>.shadow' does
   not match the current database. This file may have been left behind from a
   previous database... please delete this file and restart."` A whole resumable
   loop can wedge here: every count/read returns an error, the loop's
   `before < 0` branch sleeps forever, and progress freezes (looks like a quota
   outage or corruption - it is neither).

2. **Cross-process reopen mismatch.** Even with no crash, a *write/DDL* close
   leaves a `<db>.shadow` tagged with the **writing process's** database ID. The
   NEXT process (or the next `Database()` construction in the same process) gets
   a different ID and refuses to open with the same error. A **single long-lived
   connection** (a server) never hits this; a process that **reopens repeatedly**
   (init-schema-then-write, or one open per batch) dies on its second open - and
   if it crashes *before* writing, it can burn expensive work (LLM calls, etc.)
   and persist nothing.

## Context / Trigger conditions

- The exact strings above on `Database()` / `connect()` / open.
- A `--skip-existing` / ledger-gated writer loop frozen at a count after a
  crash, sleep, or watchdog `SIGKILL`.
- "Works for a server but not for my batch script" asymmetry.
- You are tempted to "just delete the shadow" (the error tells you to) - and it
  then fails *worse* with "Cannot open file '<db>.shadow': No such file".

## Solution

### 0. FIRST: check the database isn't outgrowing `max_db_size` (the usual real cause)

Kuzu/ladybug reserve a fixed virtual address space for the DB file via
`max_db_size` (ladybug 0.16.x default = **1 GiB**, `2**30 = 1073741824`). When
the main file approaches that cap, the next growth-requiring write fails its
checkpoint with **"Buffer manager exception: No more frame groups can be added
to the allocator"**, and that *failed checkpoint* is what leaves the mismatched
shadow (poison-shadow errors) and SIGSEGVs writers. The tell: it "worked for
hours/days then suddenly broke" — that is the file crossing the cap. Check it:

```bash
stat -f%z <db>/<main-file>     # compare to 1073741824 (1 GiB)
```

Fix = open with a generous power-of-two `max_db_size` (a virtual mmap ceiling,
NOT a disk/RAM pre-allocation), applied to EVERY opener (a long-lived server
hits the same wall as the file grows):

```python
ladybug.Database(path, max_db_size=1 << 37)   # 128 GiB headroom
```

You can reopen an existing DB with a LARGER cap (verified). This is the ROOT
fix; it restores normal WAL crash-recovery and makes the shadow-purge workaround
(steps below) unnecessary. Only fall through to the purge for a one-time
recovery of a DB already wedged by a stale shadow.

### 1. Treat the temp files as a SET, never delete the shadow alone
`<db>.shadow` and `<db>.wal.checkpoint` are paired: the checkpoint replay
references the shadow. Deleting only the shadow flips the error to *"Cannot open
file ...shadow: No such file or directory"*. Recover by moving/removing **all of**
`<db>.shadow`, `<db>.wal`, `<db>.wal.checkpoint` together, then open - the DB
then recovers from the last durable checkpoint in the main file. Quarantine
(move aside) rather than `rm` the first time, so you can restore if wrong.

### 2. PROVE the main file is durable before trusting the delete
Before relying on "remove temps -> open from main", verify a write survives it:
open, write a uniquely-named **marker** row, close, remove all temps, reopen, and
confirm the marker is present. If it survives, a clean close flushes everything
into the main file and the temps are redundant (safe to remove). If it does NOT,
the temps hold uncheckpointed commits - do not delete; replay/repair instead.
(Verified true for ladybug 0.16.1: marker survived.)

### 3. Lock-guarded purge-before-open as the durable workaround
For the cross-process / repeated-reopen case, purge a stale shadow set **inside**
the open path, but ONLY while holding the exclusive writer lock:
```python
_acquire_lockfile(db_path)          # exclusive: no concurrent writer
if PURGE_FLAG:                      # gate it; leave the server's default path unchanged
    for suffix in (".shadow", ".wal", ".wal.checkpoint"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
db = Database(str(db_path))         # now opens from the durable main file
```
The held lock guarantees no concurrent writer, and a prior writer checkpoints
into the main file *before* releasing the lock, so the temps carry nothing not
already persisted. **Gate it behind an env var / flag** so the long-lived server
path is unchanged and only the multi-open writer opts in. Durability nuance: a
writer killed mid-checkpoint loses only its uncommitted in-flight unit, which a
`--skip-existing` resume re-does.

### 4. Make the loop self-heal and survive sleep
- On persistent unreadable-graph, attempt the temp-quarantine recovery instead
  of sleeping forever; only give up after N attempts.
- Launch long writer loops under `caffeinate -i -s` (macOS) so an idle/system
  sleep cannot suspend a process mid-checkpoint and create the poison shadow in
  the first place.

## Verification

- After the set-quarantine: the DB opens and the row counts match pre-crash.
- After the lock-guarded purge: a process doing open(DDL)->close->open(write)
  ->close->open(read) in sequence succeeds and the written row persists across
  the reopens (this is the exact pattern that failed before).
- Control: with the purge flag OFF, the second open still fails - proves the
  fix, not a coincidence.

## Example

council-of-thinkers (#218): the 20VC host concept-extraction backlog wedged
overnight after a Mac sleep left a `council.shadow`. The loop's reads returned
-1 forever. Quarantining `council.{shadow,wal,wal.checkpoint}` recovered the
graph (data fully intact, 14,091/17,307 chunks, 121,403 mentions). But every new
cycle then died `rc=1` at the driver's batch-write open: the driver opens once
for `init_schema` (DDL write) then once per batch, and the init_schema close left
a poison shadow that the batch open rejected - 25 chunks extracted via `claude -p`
(~\$0.30) and zero saved, each cycle. A marker-survival test proved the main file
was durable; the fix was a `COT_PURGE_STALE_SHADOW`-gated purge in `open_database`
under the writer lock. Driver then cleared the write-open and persisted
batch-over-batch. The MCP server (one long-lived connection) was never affected.

## Notes

- Diagnose with a CONTROLLED experiment on a **copy** of the main file
  (`cp <db> /tmp/test`): if open(write)->reopen fails on the copy too, it is a
  DB-version behaviour, not corrupted lineage - so "rebuild the file" won't help
  and you need the purge/version fix.
- This is distinct from a circuit-breaker mis-abort or a no-output hang in the
  same pipeline; don't conflate them (sibling issues #212/#213).
- Upstream cure: a DB point-release that cleans the shadow on close, or reads a
  stable DB ID from the main file across opens. Test the schema path if the
  project pins the version for other reasons (e.g. ALTER support).
