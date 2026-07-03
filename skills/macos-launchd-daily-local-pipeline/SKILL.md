---
name: macos-launchd-daily-local-pipeline
description: |
  Schedule a recurring LOCAL pipeline on macOS (one that needs the user's own
  disk, GPU/ML runtime, large local data, or a CLI authed via the login
  keychain) to run daily at a fixed time. Use when: (1) the user asks to "run X
  every day at 10am" / "schedule this nightly" and X depends on local machine
  resources; (2) you're tempted to use Claude Code's `/schedule` but the job
  can't run in the cloud; (3) a launchd job "doesn't run" / "command not found"
  because of the minimal PATH; (4) you need a daily yt-dlp/ffmpeg/whisper/etc
  pipeline that also avoids stacking overlapping long runs. Key facts: Claude's
  `/schedule` runs CLOUD remote agents with no access to the local Mac, so it
  CANNOT run local-resource jobs -- use a launchd LaunchAgent instead. Covers
  the minimal-PATH trap, keychain/OAuth availability, an overlap guard for
  run-until-done jobs, the plist, and bootstrap/verify commands.
author: Claude Code
version: 1.0.0
date: 2026-06-01
---

# Daily local pipeline on macOS via launchd

## Problem

You want a job to run every day at a fixed local time. The job needs the user's
own machine: local disk (tens of GB of media), a local ML runtime (Whisper/MLX
on the GPU), a local DB, or a CLI that bills the user's subscription via the
login keychain (e.g. `claude -p`).

**Do NOT reach for Claude Code's `/schedule`.** That creates *cloud* remote
agents (routines). They have no access to the user's local filesystem, GPU, or
keychain, so they cannot run this kind of job. The right tool is a macOS
**LaunchAgent** (`launchd`), which runs a script locally, as the user, on a
calendar schedule, even with no terminal open.

## Solution

### 1. A wrapper script (handles the launchd-minimal-PATH trap)

launchd hands jobs a bare `PATH` (`/usr/bin:/bin:...`) -- NOT your shell's. So
Homebrew tools, ffmpeg, and CLIs in `~/.local/bin` are "command not found"
unless you export PATH yourself. Find the real paths first (`which uv claude
ffmpeg`) and export them:

```sh
#!/bin/zsh
set -u
PROJ="/abs/path/to/project"; PY="$PROJ/.venv/bin/python"
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/ffmpeg-full/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$PROJ/logs"; cd "$PROJ" || exit 1
exec >>"$PROJ/logs/job-$(date +%Y%m%d).log" 2>&1
echo "===== start $(date) ====="

# Overlap guard: a run-until-done job can exceed 24h; don't stack a 2nd copy.
if pgrep -f my_long_loop.py >/dev/null; then echo "already running; skip"; exit 0; fi

"$PY" scripts/refresh.py            # phase 1 (e.g. yt-dlp new items)
"$PY" scripts/my_long_loop.py       # phase 2 (process)
echo "===== done $(date) ====="
```

`chmod +x` it.

### 2. The LaunchAgent plist (`~/Library/LaunchAgents/<label>.plist`)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.you.daily-job</string>
  <key>ProgramArguments</key>
  <array><string>/bin/zsh</string><string>/abs/path/scripts/daily.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>/abs/path/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>/abs/path/logs/launchd.err</string>
</dict></plist>
```

### 3. Lint, load, verify

```sh
plutil -lint ~/Library/LaunchAgents/com.you.daily-job.plist        # must say OK
UID_=$(id -u)
launchctl bootout   "gui/$UID_/com.you.daily-job" 2>/dev/null      # idempotent re-load
launchctl bootstrap "gui/$UID_" ~/Library/LaunchAgents/com.you.daily-job.plist
launchctl print     "gui/$UID_/com.you.daily-job" | grep -E "state|path"
launchctl list | grep daily-job        # "- 0 com.you.daily-job" = loaded, last exit 0
launchctl kickstart "gui/$UID_/com.you.daily-job"   # OPTIONAL: run once now to test
```

Use the modern `bootstrap gui/<uid>` form, not the deprecated `launchctl load`.

## Verification

- `launchctl list | grep <label>` shows the label (col1 `-` = not currently
  running, col2 = last exit code; `0` is healthy).
- `kickstart` once and tail the dated log to confirm the wrapper runs end to end
  under the launchd PATH (this is where the PATH trap shows up).

## Notes

- **Keychain / OAuth**: a LaunchAgent runs in the user's GUI (Aqua) session, so
  the login keychain is available while the user is logged in (even with the
  screen locked) -- `claude -p` subscription auth works. A LaunchDaemon (root,
  pre-login) would NOT have it; use a LaunchAgent.
- **Asleep at fire time**: with `StartCalendarInterval`, launchd runs the job
  once on the next wake if the Mac was asleep at the scheduled minute (it
  coalesces, it does not run N times). Powered fully off -> next boot+login.
- **Overlap guard is essential** for "run until done" jobs that can exceed the
  schedule interval; without it, each fire stacks another copy.
- **Logs**: redirect inside the wrapper (`exec >>logfile 2>&1`) for dated app
  logs; the plist's StandardOut/ErrorPath only catch launchd-level breakage
  (e.g. bad interpreter), which is the first place to look if nothing happens.
- Real instance: council-of-thinkers `scripts/daily_ingest.sh` +
  `com.council.daily-ingest` (2026-06-01): daily 20VC yt-dlp refresh + ingestion
  loop; ffmpeg lived at `/opt/homebrew/opt/ffmpeg-full/bin` (not `/opt/homebrew/bin`).
