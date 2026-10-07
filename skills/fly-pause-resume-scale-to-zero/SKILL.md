---
name: fly-pause-resume-scale-to-zero
description: |
  Pause a Fly.io app to stop paying for compute while keeping its volume, secrets and
  hostname, then bring it back reliably. Use when: (1) a user wants to stop Fly billing
  for an idle app "but be able to bring it back easily", (2) an app scaled to zero came
  back by itself after a GitHub Actions `flyctl deploy` (deploy recreates machines in
  empty process groups), (3) `fly scale count 1` or `fly deploy` fails with
  "failed_precondition: insufficient resources to create new machine with existing
  volume 'vol_...'", (4) the usual fix (`fly volumes fork` + `fly machines clone
  --attach-volume`) is impossible because no machine is left to clone, (5) two
  same-name unattached volumes exist after a restore and the stale one could be
  attached. Verified against flyctl v0.4.59 source and a live pause/resume round trip.
author: Claude Code
version: 1.0.0
date: 2026-10-03
---

# Pause and resume a Fly.io app (scale to zero, keep the volume)

## Problem

"Stop paying for this Fly app but keep it restorable" looks like `fly scale count 0` /
`fly scale count 1`. Three things make that naive version unreliable:

1. **CI un-pauses it.** `flyctl deploy` launches a new machine for any process group in
   `fly.toml` that has zero machines (flyctl `resolveProcessGroupChanges` ->
   `deployCreateMachinesForGroups`, "No machines in group app, launching a new machine").
   A deploy-on-push workflow therefore silently restarts billing on the next merge.
2. **The volume can be stranded.** A Fly volume lives on one physical host. Once the
   machine is destroyed its slot is released, and that host may refuse new machines
   (full or draining). Resume then fails with
   `Error: failed to launch VM: failed_precondition: insufficient resources to create new machine with existing volume 'vol_...'`
   and retrying does not help.
3. **Duplicate volumes attach the wrong data.** `fly scale count 1` picks the first
   unattached volume with the mount's name in the region. After a restore leaves two
   same-name volumes, it can attach the stale one.

## Context / Trigger Conditions

- App with a `[[mounts]]` volume, typically one always-on machine
  (`auto_stop_machines = "off"`, `min_machines_running = 1`).
- A CI workflow running `flyctl deploy` on push.
- Goal: minimal residual cost and a scripted, reliable bring-back.

## Solution

### Pause (order matters)

1. **Disable CI deploys first**, so nothing can recreate the machine:
   `gh api -X PUT "repos/{owner}/{repo}/actions/workflows/<file>.yml/disable"`
   (state via `gh api repos/{owner}/{repo}/actions/workflows/<file>.yml --jq .state`:
   `active` / `disabled_manually`). Do not scale down if this fails. Disabling does
   not stop a run that is already queued or in progress, and its deploy would recreate
   the machine after the scale-down. So also refuse while
   `gh api "repos/{owner}/{repo}/actions/workflows/<file>.yml/runs?per_page=20" --jq '[.workflow_runs[] | select(.status != "completed")] | length'`
   is above 0. That REST call works on a disabled workflow.
2. `fly scale count 0 -a <app> --yes`. This destroys machines and **never deletes volumes**.
   Prefer it to `fly machine stop`: stopped machines are still billed for rootfs, and with
   `auto_start_machines = true` any request to the hostname restarts them.
3. Verify: `fly machines list -a <app> --json` prints `[]`; `fly volumes list` shows the
   volume `created` with an empty ATTACHED VM column.

The app, its secrets, the `*.fly.dev` hostname and the shared IPv4/IPv6 stay, at no cost.

### Resume

1. **Guard: exactly one volume with the mount name, and its `host_status` is `ok`.**
   Zero means `fly scale count` would create a new EMPTY volume (flyctl
   `CreateVolumeRequest`); more than one means it may attach a stale copy. A host that
   is not `ok` is skipped by `PopAvailableVolumes`, which also produces a new empty
   volume. The machine then boots onto no data, and "keep the newest volume" advice
   would point at the empty one.
2. `fly scale count 1 -a <app> --region <the volume's region> --yes`. flyctl reuses the
   unattached same-name volume (`PopAvailableVolumes`, which requires `host_status == ok`)
   and the latest release's image. In a live run this took 24 s from paused to healthy.
3. **If it fails with `insufficient resources ... existing volume`**, move the data to a
   host with room:
   ```sh
   before=$(fly volumes snapshots list <vol_id> -a <app> --json) || exit 1   # must succeed
   fly volumes snapshots create <vol_id> -a <app>   # prints only "Scheduled to snapshot volume <vol_id>"
   # poll: fly volumes snapshots list <vol_id> -a <app> --json
   #   until a snapshot with status "created" appears whose id is NOT in $before
   fly scale count 1 -a <app> --region <region> --with-new-volumes --from-snapshot <new_snapshot_id> --yes
   ```
   Identify the new snapshot by set difference against a listing that must succeed.
   If you compare against "the previous newest id" and that listing fails, the old daily
   snapshot passes for the fresh one: stale data is restored, and you are then told to
   delete the volume that holds the current data.
   Snapshot first, because the scheduled daily snapshot can be up to a day old; the
   unattached volume is quiescent, so this one is consistent. flyctl's
   `CreateVolumeRequest` sends `ComputeRequirements` + `ComputeImage`, so Fly places the
   new volume on a host that can run the machine. Live: about 13 minutes for a 16 GB volume
   (14 GiB stored).
4. Wait for a real health endpoint (not just "machine started"), then re-enable CI
   (`.../enable`). Re-enable last, so a failed resume leaves CI disabled.
5. After a fallback, **verify the new volume's data, then delete the old volume**
   (`fly volumes destroy <old_id> -a <app> --yes`; `--yes` is required
   non-interactively). Otherwise it keeps billing and sets up trap 3. Fly documents
   restoring a deleted volume from its snapshots, and default retention is 5 days.

### Costs (docs.fly.io, October 2026)

- Volumes: $0.15/GB-month of **provisioned** size, attached or not. Volumes cannot be shrunk.
- Snapshots: $0.08/GB-month, first 10 GB free (billed since 01/01/2026). Daily automatic
  snapshots keep a full base, so stored size is roughly the blocks ever written.
- Stopped or suspended machines: $0.15/GB-month of rootfs.
- So a paused 16 GB-volume app costs about $2.70/month. $0 requires deleting the volume,
  after backing up and later re-seeding it (see [[fly-seed-volume-via-ssh-tar-stream]]).
  The empty app itself costs nothing and keeps the name and secrets, so `fly apps destroy`
  gains nothing.

## Verification

- Paused: `machines list --json` is `[]`, the volume is unattached, the workflow state is
  `disabled_manually`, and the hostname no longer answers (curl exit 35).
- Resumed: the health route returns 200, `fly machines list` shows the machine mounting the
  expected volume id, a record created just before the pause is still served (proves
  fresh data), and authenticated clients (for example an OAuth MCP connector) still work.

## Example

council-of-thinkers (`sapiens-locus`) has `scripts/fly_pause.sh` and
`scripts/fly_resume.sh`, plus mock-driven tests in `tests/shell/test_fly_pause_resume.sh`
(stub `fly`/`gh`/`curl` on PATH log the call order). The live round trip: pause ->
resume failed (host full) -> snapshot fallback onto a new volume -> old volume deleted ->
pause -> resume via plain reattach in 24 s -> pause.

## Notes

- flyctl can report `no access token available` while `~/.fly/config.yml` holds
  `access_token:`; export `FLY_API_TOKEN` from that file in scripts.
- Merges made while paused are not deployed. After resume, the machine runs the last
  released image until the next qualifying push.
- Paths used by the deploy workflow's `paths:` filter decide whether merging the pause
  scripts themselves would trigger a deploy. Check them before relying on "merging is safe".
- Related: [[fly-trial-machine-stops-every-5-minutes]], [[fly-secrets-append-without-clobber]].

## References

- Fly pricing: https://docs.fly.io/about/pricing
- Fly billing (stopped machines, unattached volumes, snapshots): https://docs.fly.io/about/billing
- Volume snapshots (retention, `--scheduled-snapshots`, restore incl. deleted volumes): https://docs.fly.io/volumes/snapshots
- flyctl v0.4.59 source: `internal/command/deploy/machines_deploymachinesapp.go`,
  `internal/command/deploy/machines.go` (`setVolumes`), `internal/command/scale/count_machines.go`,
  `internal/command/scale/machine_defaults.go`, `internal/command/volumes/snapshots/create.go`
- Community threads on the error (fork + clone fix, needs an existing machine):
  https://community.fly.io/t/insufficient-resources-to-create-new-machine-with-existing-volume/21378 and
  https://community.fly.io/t/how-to-restore-a-volume-where-a-machine-cant-be-provisioned-due-to-low-capacity/25169
