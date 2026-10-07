---
name: pgrep-f-self-match-in-agent-sessions
description: |
  pgrep -f matching the WATCHER instead of the target inside agent/automation
  sessions. Use when: (1) a wait-loop like `until ! pgrep -f X` never exits or
  a tripwire never fires, (2) a liveness check reports a process "running"
  that is actually your own monitor/tripwire shell, (3) a guard (mutual
  exclusion, writer-exclusion) blocks or fails-open mysteriously while agent
  monitors are armed, (4) you are about to kill a PID found via pgrep -f.
  Cause: pgrep -f scans FULL command lines, and monitoring shells, tripwires,
  grep filters, and Claude-session snapshot wrappers all CONTAIN the target
  string in their own cmdline. Fix: anchor the pattern to the executable path
  end (scripts/foo\.sh$), and verify parentage (ps -o ppid,args) before kill.
author: Claude Code
version: 1.0.0
date: 2026-07-04
---

# pgrep -f self-match in agent sessions

## Problem

`pgrep -f PATTERN` matches ANY process whose full command line contains the
pattern - including the very shell that is running the check. In an agent
session this is endemic: tripwires (`until ! pgrep -f daily_ingest.sh`),
monitors (`tail -f log | grep -E "daily_ingest|..."`), and zsh snapshot
wrappers all carry the target string in their own argv.

Three real failures in one day (council-of-thinkers, 2026-07-03/04):
1. A tripwire `until ! pgrep -f daily_ingest.sh; do sleep; done` DEADLOCKED
   forever: its own zsh cmdline contains "daily_ingest.sh".
2. A "is my job up?" check matched the tripwire's cmdline, reporting a dead
   driver as running (empty log was the tell).
3. A production guard (`pgrep -f 'daily_ingest.sh|bulk_process_loop.py'`)
   would have blocked/stopped a batch driver whenever ANY monitor shell was
   armed in the session.
Related, same family: killing a process identified only by pattern killed
work owned by a DIFFERENT job (a scheduled daily's claude call mistaken for
the experiment's; separately, a pkill pattern list missed the actual lock
holder because the child script had a different name).

## Rules

1. Anchor to the end of the executable path: `pgrep -f "scripts/daily_ingest\.sh$"`.
   Watchers' cmdlines mention the name mid-string (followed by pipes, flags,
   `>/dev/null`), so a `$` anchor excludes them; the real process's argv ends
   with the script path (or use one trailing-arg-aware anchor per known form).
2. Before ANY kill of a pgrep-found PID: `ps -o pid,ppid,etime,args -p <pid>`
   and check the parent chain. A matching cmdline is a hypothesis, not an
   identification.
3. Wait-loops that watch for a process to EXIT must use the anchored form or
   they deadlock on themselves when run as background tasks.
4. "Process up" claims need a second signal (its log file growing, its output
   artefact appearing), not just pgrep - the empty-log-but-"running" combo
   means you matched a watcher.
5. When a guard uses pgrep -f patterns (writer exclusion, cron mutexes),
   audit it against the strings your OWN session tooling puts into argv.

## Variant: wrapper processes share the argv tail (self-suicide loops)

`caffeinate ... python -m pkg.mod --execute`, `nohup`, `timeout`, and shell
wrappers all carry the SAME anchored argv tail as the real process, as
PARENT processes. A duplicate-instance guard that counts them makes every
scheduler-fired instance see its own wrapper and exit as a "duplicate" -
a silent zero-progress loop (observed: 26 quiet exits overnight, 2026-07-05).
Guards must also filter by executable identity: after pgrep, check each
pid's `ps -o comm=` is actually the target interpreter/binary, and exclude
os.getpid() AND os.getppid().

## Verification

`pgrep -fl <pattern>` and read every match's full args. If any match is a
zsh/bash wrapper sourcing a shell snapshot, or contains your grep/monitor
pipeline, the pattern is too loose.
