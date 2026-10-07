---
name: caffeinate-s-refused-on-battery-overnight-stall
description: |
  Diagnose a long-running macOS job (overnight ingest, batch transcode, model
  training, backfill loop) that silently stops making progress after the
  interactive session goes quiet, despite being launched under
  `nohup caffeinate -i -s`. Use when: (1) logs end mid-task with NO error, no
  traceback and no exit code, and the last line is hours old, (2) a worker log
  contains "Failed to create PreventUserIdleSystemSleep assertion", (3)
  `pmset -g assertions` shows PreventSystemSleep 0 while you believe caffeinate
  is running, (4) work resumes or dies the moment you touch the machine in the
  morning, (5) a job survives ~20-30 minutes past the last interaction, then
  freezes. Root cause: macOS REFUSES the caffeinate -s (prevent system sleep)
  assertion on battery power; it only succeeds on AC. Processes are SUSPENDED,
  not killed, so liveness checks lie.
author: Claude Code
version: 1.0.0
date: 2026-08-16
---

# `caffeinate -s` is refused on battery, so overnight jobs suspend mid-task

## Problem

You launch a multi-hour job detached and shielded from sleep:

```sh
nohup caffeinate -i -s uv run python long_job.py > job.log 2>&1 &
```

It runs fine while you are working, then stops making progress roughly 20-30
minutes after you stop interacting with the machine. In the morning the log
ends mid-task: no exception, no exit code, no "killed" message — just silence.
The process may still exist. Nothing looks like a crash because nothing
crashed.

## Context / Trigger conditions

- macOS laptop **running on battery** (the decisive variable).
- Startup lines in the job log that are easy to scroll past:
  ```
  Failed to create PreventUserIdleSystemSleep assertion
  ```
- `pmset -g assertions` shows:
  ```
  PreventSystemSleep             0
  PreventUserIdleSystemSleep     0
  ```
- `pmset -g log | grep "Entering Sleep"` shows an idle/maintenance sleep at
  about the time the log went quiet.
- Restarted workers write one or two lines and stop again (they launched during
  a brief DarkWake and were re-suspended).

## Solution

**`caffeinate -s` only takes effect on AC power.** From the man page: "-s
Prevent the system from sleeping. This assertion is valid only when system is
running on AC power." On battery the assertion is refused, caffeinate prints
the failure and keeps running as a no-op wrapper, so the command *looks* right.

1. **Plug the machine in.** This is the actual fix; verify it took:
   ```sh
   pmset -g batt | head -1          # expect: Now drawing from 'AC Power'
   ```
2. **Verify the assertion is really held** rather than assuming:
   ```sh
   nohup caffeinate -i -s <cmd> > job.log 2>&1 &
   sleep 5
   grep -c "Failed to create" job.log          # MUST be 0
   pmset -g assertions | grep -E "PreventSystemSleep|caffeinate"
   ```
3. **If the job must survive on battery**, `-s` cannot help. Either:
   - `sudo pmset -b disablesleep 1` (blunt; remember to undo it), or
   - drop `-s` and accept that only idle *display* sleep is deferred, or
   - restructure so the work is resumable and simply continues after wake.

Make the check part of launching a long job, not part of debugging it: a
one-line `grep -c "Failed to create"` at startup turns a silent nine-hour loss
into an immediate, actionable message.

## Verification

```sh
pmset -g batt | head -1                     # 'AC Power'
grep -c "Failed to create" job.log          # 0
pmset -g assertions | grep caffeinate       # shows the held assertion
# and later, the decisive one:
pmset -g log | grep "Entering Sleep" | tail -3   # no sleep during the run
```

## Example

An overnight ingest (~650 videos: download, ASR, LLM calls) launched at 21:31
under `nohup caffeinate -i -s`. Timeline:

```
21:31  launched, 3 shards + extractor, all healthy
22:08  last interactive check; ~57 episodes done, no errors
22:35  ledger stops advancing; extractor's last cycle logged
22:41  watchdog starts a fresh wave; shards log "batch of 191 pending" ...
       ... and nothing more. Log files 228 bytes, mtime 22:41.
07:50  discovered: +9 episodes in 9 hours
```

Every shard log began with `Failed to create PreventUserIdleSystemSleep
assertion`. The machine was on battery at 96%. Relaunching the identical
command on AC produced 0 such failures and normal throughput resumed.

## Notes

- **Processes are suspended, not killed.** `pgrep` reports them alive, so a
  liveness probe is not evidence of progress. Check that the *artefact* is
  advancing (row count, output files, log mtime), never just the PID. This is
  the same "clean-looking non-progress" trap as a job that exits 0 having done
  nothing.
- `caffeinate -i` (prevent *idle* sleep) and `-d` (display) are NOT restricted
  to AC; only `-s` is. So the command partially works, which is why the failure
  is easy to misread as something else.
- A closing lid still sleeps the machine regardless of caffeinate unless
  `disablesleep` is set or an external display is attached.
- Suspicion heuristic: work stopping ~20-30 min after the last human
  interaction, on a laptop, with no error, is idle sleep until proven otherwise.
  Check `pmset -g log` before hunting application bugs.
- launchd does not solve this: a launchd-managed job is also suspended by
  system sleep. Power state is the variable, not process ownership.

## References

- `man caffeinate` (the `-s` AC-power restriction)
- Apple pmset / power assertions:
  https://developer.apple.com/library/archive/documentation/Performance/Conceptual/power_efficiency_guidelines_osx/AboutPowerAssertions.html
