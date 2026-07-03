---
name: fly-seed-volume-via-ssh-tar-stream
description: |
  Seed a large data corpus (hundreds of MB to several GB) onto a Fly.io
  persistent volume from your local machine, without baking it into the Docker
  image or running a separate upload service. Use when: (1) deploying a
  data-heavy app to Fly where the data lives on a [[mounts]] volume, not in the
  image, (2) you need to copy a local directory tree to /data on a Fly machine,
  (3) you want corpus updates to be a re-upload, not an image rebuild, (4) a
  `fly ssh console` data transfer dies with "tar: Write error" partway. Covers
  the binary-safe `tar | fly ssh console -C "tar -xf -"` stream, the 1 MB
  checksum pre-check, the `.seeded` marker gate that stops a half-finished
  upload from crash-looping the server, and the slim-image gotchas (no ps/curl,
  fly ssh issue --agent needed). Pairs with [[fly-trial-machine-stops-every-5-minutes]].
author: Claude Code
version: 1.0.0
date: 2026-06-20
---

# Seed a Fly.io volume by streaming a tar over `fly ssh console`

## Problem

You're deploying a data-heavy app to Fly.io. The corpus (a vector DB, a graph
DB, sqlite files — say ~2 GB) is too big and too frequently-updated to bake
into the Docker image, so it lives on a Fly **persistent volume** mounted at
`/data`. You need a reliable, repeatable way to get the local data onto that
volume, and to make the app boot a placeholder (not crash) until the data is
present.

## Context / Trigger conditions

- `fly.toml` has a `[[mounts]]` block (volume → `/data`) and the image does NOT
  contain the data.
- App code resolves DB paths relative to its source dir (PROJECT_ROOT-style),
  not via env vars — so you symlink the volume into the expected locations at
  startup rather than changing code.
- You want "update the corpus" to mean "re-upload to the volume + restart", not
  "rebuild and redeploy a multi-GB image".
- Symptom that brings you here: a `fly ssh console` transfer dies with
  `tar: Write error` (usually the machine stopped mid-stream — see Notes).

## Solution

**1. Entrypoint: symlink the volume in, gate real start on a marker.**
Because app DB paths are relative to the code, symlink `/data/*` into place, and
serve a trivial placeholder until an explicit `/data/.seeded` marker exists.
Gating on the marker (not on the data files merely existing) prevents a
truncated/partial upload from booting the real server onto corrupt data and
crash-looping:

```sh
#!/bin/sh
set -e
PORT="${PORT:-8080}"
ln -sfn /data/lancedb /app/lancedb        # etc. for each data dir/file
cd /app
if [ ! -f /data/.seeded ]; then
  echo "[entrypoint] not seeded; serving placeholder on :$PORT"
  exec python -m http.server "$PORT"      # keeps the machine healthy for upload
fi
exec python -m your_app.server
```

**2. Create the volume and deploy once** (boots to placeholder):
```sh
fly volumes create my_data --region <r> --size <GB> -a <app> --yes
fly deploy --ha=false -a <app>            # --ha=false = single machine (matches one volume)
```

**3. Get an SSH cert** (non-interactive needs the org slug explicitly):
```sh
fly ssh issue --agent personal            # or your org slug; bare `--agent` errors non-interactively
```

**4. Verify the transport is binary-safe before the big transfer.** `fly ssh
console` can mangle bytes; prove it doesn't with a 1 MB checksum round-trip:
```sh
head -c 1048576 <some-binary-file> > /tmp/probe
shasum -a 256 /tmp/probe
cat /tmp/probe | fly ssh console -a <app> -C "sh -lc 'cat > /tmp/p; sha256sum /tmp/p; rm /tmp/p'"
# the two hashes must match
```

**5. Stream the corpus** (no intermediate tarball; extract on the fly):
```sh
tar -cf - dir1 dir2 file1.db file2.db \
  | fly ssh console -a <app> -C "tar -xf - -C /data"
```

**6. Verify integrity, set the marker, restart into the real app:**
```sh
# checksum the biggest file on the volume vs local
fly ssh console -a <app> -C "sha256sum /data/<big-file>"
shasum -a 256 <big-file>                  # compare
fly ssh console -a <app> -C "touch /data/.seeded"
fly machine restart <machine-id> -a <app>
```

## Verification

- `curl https://<app>.fly.dev/healthz` returns the **real** app's health body
  (a placeholder `python -m http.server` would 404 on `/healthz`).
- Remote checksum of the largest data file equals the local checksum.
- After restart, logs show the real start branch, not the placeholder branch.

## Notes

- **`tar: Write error` mid-stream = the machine stopped under the transfer.**
  The most common cause is the **Fly trial 5-minute cap** (no payment method) —
  see [[fly-trial-machine-stops-every-5-minutes]]. Add billing, clear the
  partial (`fly ssh console -C "rm -rf /data/<partial>"`), and re-stream.
- **Slim images lack `ps`, `curl`, sometimes `ss`.** To inspect a process,
  read `/proc/1/status`, `/proc/1/cmdline`, `/proc/1/wchan` instead of `ps`.
  Use `python -m http.server` (Python is present) rather than assuming `nc`.
- **Cold start can be minutes** if the app loads a large DB into memory on boot
  (e.g. a 1.6 GB graph on a shared CPU); expect 502s during that window after
  every restart. Bump the VM for faster restarts if it matters.
- **Single writer / single machine:** if a data engine is single-writer (e.g.
  an embedded graph DB), run exactly one machine (`--ha=false`,
  `min_machines_running = 1`, `auto_stop_machines = "off"`).
- **Quiesce local writers before copying** a single-writer DB, or you can ship a
  torn write; copy any sidecar WAL alongside the main file, and don't copy lock
  files (`*.lock`).
- **macOS `tar` -> Linux `tar` injects AppleDouble `._*` sidecar files.** macOS
  bsdtar carries each file's `com.apple.provenance` (and other) xattrs; GNU tar on
  the Fly box can't apply them and MATERIALISES them as real `._<name>` files
  (you'll see `tar: Ignoring unknown extended header keyword
  'LIBARCHIVE.xattr.com.apple.provenance'` during extraction). Effect: the remote
  file set is inflated by hundreds/thousands of `._*` files, which (a) breaks any
  per-file integrity manifest (file-count + content mismatch) and (b) pollutes the
  volume/promoted corpus. `COPYFILE_DISABLE=1` and `--no-xattrs` only REDUCE the
  sidecars (verified: raw-stream xattr headers 4317 -> 2878, `._lancedb` still
  present), so don't rely on them. Reliable fix on the RECEIVING side: after
  extraction run `fly ssh console -C "sh -c 'find <dir> -type f -name ._* -delete'"`,
  and exclude `! -name '._*'` from the manifest `find` on both sides. (council-of-thinkers
  push_to_fly.sh #253.)
- Re-uploading later (after refreshing the corpus locally) is just steps 4–6
  again — no image rebuild.

## References

- Fly volumes: https://fly.io/docs/volumes/overview/
- Fly `[[mounts]]` in fly.toml: https://fly.io/docs/reference/configuration/#the-mounts-section
- `fly ssh console` / `fly ssh issue`: https://fly.io/docs/flyctl/ssh-console/
