---
name: cron-runs-working-tree-merge-is-not-activation
description: |
  Avoid silently arming an unsafe code path when merging a PR that changes a
  script run by a cron/launchd job FROM A GIT WORKING TREE. Use when: (1) a
  scheduled job's ProgramArguments / crontab points at a script inside a checked-
  out repo (e.g. ~/proj/scripts/daily_ingest.sh), (2) you are about to merge a PR
  that modifies that script, especially if the change adds an outward-facing /
  irreversible step (a deploy, an upload, a `--live` push, a destructive
  migration) that depends on a SEPARATELY deployed component, (3) you need to
  reason about WHEN merged changes actually take effect on the cron host. Key
  insight: the cron runs the working-tree copy, so the activation point is
  `git pull` ON THE CRON HOST, not the GitHub merge - and pulling can arm the new
  behaviour before its dependency is in place. Fix: merge on the remote, but
  sequence the cutover deliberately - deploy/verify the consumer-side dependency
  FIRST, then pull on the cron host; until then leave local behind origin on
  purpose. Pairs with stale-lock-shell-guard-skips-scheduled-phase.
author: Claude Code
version: 1.0.0
date: 2026-06-24
---

# A cron/launchd job runs the working tree, so merge is not activation

## Problem

A scheduled job (launchd `ProgramArguments`, or a crontab line) executes a script
by PATH inside a checked-out git repo. You merge a PR that changes that script.
It is tempting to think "merged = live". It is not: the job runs whatever bytes
are in the **working tree on the cron host**, which only change when that host
runs `git pull`. Worse, if the merged change adds an **outward-facing or
irreversible step** that needs a separately-deployed component, the first `pull`
silently ARMS that step, and the next scheduled run fires it against the
not-yet-deployed dependency.

## Context / Trigger conditions

- A launchd plist / crontab whose command is a repo-relative script
  (`/Users/.../repo/scripts/job.sh`), not an installed/packaged binary.
- A PR under merge that edits that script - especially adding a deploy, an
  upload/push (`--live`), a `fly deploy`/`fly ssh`, a DB migration, or anything
  that touches production or another service.
- That new step depends on something deployed elsewhere (a new container image /
  entrypoint, a new server route, a new schema) that has NOT shipped yet.
- You are deciding whether to `git pull` on the machine that runs the job.

## Solution

1. **Separate the merge from the cutover.** Merging on GitHub updates `origin`,
   not the cron host's working tree. That is safe and does not change behaviour.
2. **Identify the consumer-side dependency** the new step needs (e.g. a new
   `entrypoint.sh` that promotes a staged corpus; a new server route; a migrated
   schema). The new code is only SAFE to run once that is deployed.
3. **Sequence the cutover deliberately, dependency first:**
   ```
   deploy/verify the dependency      # e.g. fly deploy -a <app>
   git pull            (on the cron host)   # working tree -> new script: ACTIVATION
   first manual run / dry-run         # confirm before the unattended schedule does it
   ```
4. **Until cutover, leave the cron host's local branch BEHIND origin on purpose,**
   and say so explicitly so nobody "tidies up" by pulling. The job keeps running
   the old, safe script meanwhile.
5. Prefer making the new step **self-gating** (dry-run by default; refuse if its
   dependency/precondition is absent) so an accidental early pull degrades to a
   no-op or clean refusal rather than a bad prod action.

## Verification

- After merge, before pull: `git rev-parse HEAD` on the cron host != `origin/master`,
  and the working-tree script is still the old version (`grep` for the new step
  finds nothing). The next scheduled run uses the old behaviour.
- After the dependency deploy + pull: the working-tree script contains the new
  step; a manual dry-run shows the intended plan; only then let the schedule run.

## Example

council-of-thinkers: launchd `com.council.daily-ingest` runs
`repo/scripts/daily_ingest.sh` at 10:00. PR #249 added `push_to_fly.sh --live` as
the final daily step, whose swap only works once a new `deploy/entrypoint.sh`
(promote-on-boot) is deployed to Fly. The PR was merged to `origin/master`, but
the cron host was deliberately NOT pulled (local left at the pre-merge commit) so
the daily job kept running the old, no-push script. Pulling first would have made
the 10:00 run stream 2.1GB to the volume and restart prod while the OLD entrypoint
ignored the `.promote` marker - a daily no-op restart. Cutover order: `fly deploy`
the new entrypoint, THEN `git pull` on the Mac, THEN a manual `--live` push.

## Notes

- This is the inverse footgun to "I edited the script but the cron still does the
  old thing" - same root cause (cron runs the working tree), opposite surprise.
- A packaged/installed job (systemd unit running an installed binary, a container
  image) does not have this gap - activation is the deploy, not a `pull`. The trap
  is specific to running a script straight out of a working tree.
- Make the dangerous step self-gating (dry-run default, precondition refusal) so
  the blast radius of a premature pull is small. See
  stale-lock-shell-guard-skips-scheduled-phase for making gated phases loud rather
  than silent.
