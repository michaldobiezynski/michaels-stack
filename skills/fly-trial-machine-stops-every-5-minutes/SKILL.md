---
name: fly-trial-machine-stops-every-5-minutes
description: |
  Fly.io machine keeps stopping on its own roughly every 5 minutes and you
  can't keep a long operation alive. Use when: (1) a `fly deploy`d machine
  goes to STATE=stopped a few minutes after starting, (2) `fly ssh console`
  fails with "app <name> has no started VMs. It may be unhealthy or not have
  been deployed yet", (3) a long `fly ssh console` upload/stream dies with
  "tar: Write error" or a broken pipe partway through, (4) setting
  `auto_stop_machines = "off"` or `fly machine update --autostop=off` does NOT
  stop the stopping, (5) you suspect autostop or OOM but can't find evidence.
  Root cause is the Fly TRIAL limit (no payment method = machines capped at
  5 minutes), not autostop or OOM. Check `fly logs` for "Trial machine stopping".
author: Claude Code
version: 1.0.0
date: 2026-06-19
---

# Fly.io trial machines stop every 5 minutes (misdiagnosed as autostop/OOM)

## Problem

A freshly deployed Fly machine refuses to stay up: it starts, serves briefly,
then goes `stopped` after a few minutes, over and over. Long operations that
need the machine alive (seeding a volume by streaming a tarball over
`fly ssh console`, a long build, a migration) fail partway through. The
symptoms strongly suggest **machine autostop** or an **OOM kill**, so you burn
time disabling autostop and checking memory, and neither helps.

## Context / Trigger conditions

- `fly machine list` shows `STATE = stopped` a few minutes after each start.
- `fly ssh console ...` errors: `app <name> has no started VMs. It may be unhealthy or not have been deployed yet.`
- A piped upload like
  `tar -cf - data/ | fly ssh console -a APP -C "tar -xf - -C /data"`
  dies with `tar: Write error` (the machine disappeared under the stream).
- `auto_stop_machines = "off"` in `fly.toml` and/or
  `fly machine update <id> --autostop=off` make no difference.
- No `oom-kill` / `out of memory` lines in the logs.

## Root cause

The Fly account is on the **free trial with no payment method added**. Trial
machines are **force-stopped after 5 minutes of runtime**, independent of
autostop, health, or memory. The giveaway is in `fly logs`:

```
[warn] Trial machine stopping. To run for longer than 5m0s, add a credit card by visiting https://fly.io/trial.
... Sending signal SIGINT to main child process ...
... reboot: Restarting system
```

It restarts, runs ~5 minutes, stops again, on a loop. Because the stop is a
clean SIGINT (`Main child exited normally with code: 0`), it looks like a
graceful shutdown rather than a limit being hit.

## Solution

1. **Confirm it first** — do not assume autostop:
   ```sh
   fly logs -a <app> --no-tail | grep -i "trial machine stopping"
   ```
   A hit confirms the trial limit.
2. **Add a payment method** at https://fly.io/trial (or Fly dashboard →
   Billing). This converts the trial to pay-as-you-go; machines then run
   continuously. A small always-on `shared-cpu-1x` + a few-GB volume is a few
   dollars a month.
3. **Then redo the interrupted operation.** If you were seeding a volume, the
   partial transfer is incomplete — clear it before re-streaming, e.g.
   `fly ssh console -a <app> -C "rm -rf /data/<partial-dirs>"`, then re-run the
   upload (it will no longer be cut off at 5 minutes), then
   `fly machine restart <id>` so the entrypoint picks up the now-complete data.

There is **no config workaround**: autostop settings, health checks, and
`min_machines_running` cannot override the trial 5-minute cap. Splitting work
into sub-5-minute chunks is fragile and still leaves the actual service unable
to stay up, so billing is required for any always-on app.

## Verification

After adding billing, start the machine and confirm it survives past 5 minutes:

```sh
fly machine start <id> -a <app>
# wait > 5 min, then:
fly machine list -a <app>   # STATE should still be 'started'
```

No more `Trial machine stopping` lines should appear in `fly logs`.

## Notes

- This is distinct from real autostop (`auto_stop_machines`) and real OOM.
  Always `grep` the logs for the trial line before touching autostop or RAM.
- A clean SIGINT + `exited normally with code: 0` in the logs is the trial
  shutdown, not your process crashing.
- Streaming large data over `fly ssh console -C "tar -xf -"` is otherwise fine
  and binary-safe (verify with a 1 MB chunk + `sha256sum` if unsure); the only
  reason it failed here was the 5-minute cap, not the transport.

## References

- Fly.io trial / plans: https://fly.io/trial (and Fly dashboard → Billing)
- Fly machine autostop (the thing this is NOT): https://fly.io/docs/launch/autostop-autostart/
