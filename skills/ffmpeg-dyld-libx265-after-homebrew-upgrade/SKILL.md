---
name: ffmpeg-dyld-libx265-after-homebrew-upgrade
description: |
  Diagnose and fix Homebrew ffmpeg crashing on launch with
  "dyld: Library not loaded: /opt/homebrew/opt/x265/lib/libx265.NNN.dylib"
  while `which ffmpeg` still returns the binary path. Use when:
  (1) yt-dlp reports "ffmpeg is not installed" despite ffmpeg being on PATH,
  (2) ffmpeg's `-version` output is empty and exit code is -6 (SIGABRT),
  (3) audio extraction or merge steps in yt-dlp silently fail without
  producing the merged file, (4) any tool that shells out to ffmpeg behaves
  as if ffmpeg is missing. Caused by Homebrew upgrading the x265 formula
  (or any dependency) to a new ABI version without relinking ffmpeg.
author: Claude Code
version: 1.0.0
date: 2026-05-09
---

# ffmpeg dyld libx265 mismatch after Homebrew upgrade

## Problem

ffmpeg appears installed but is broken in a way that hides itself from casual
diagnostics:

- `which ffmpeg` returns `/opt/homebrew/bin/ffmpeg` (looks fine)
- `ffmpeg -version` produces no output and exits with code -6 (SIGABRT)
- `yt-dlp` warns "ffmpeg is not installed" or "you have requested merging of
  multiple formats but ffmpeg is not installed"
- Tools that try to invoke ffmpeg silently fail; no error message reaches the
  user-facing log

The actual error is only visible by running ffmpeg directly with stderr
captured, where you'll see something like:

```
dyld[2155]: Library not loaded: /opt/homebrew/opt/x265/lib/libx265.215.dylib
  Referenced from: /opt/homebrew/Cellar/ffmpeg/8.1/bin/ffmpeg
  Reason: tried: '/opt/homebrew/opt/x265/lib/libx265.215.dylib' (no such file),
  ... (no such file), '/opt/homebrew/Cellar/x265/4.2/lib/libx265.215.dylib'
  (no such file), ...
```

## Context / Trigger conditions

Suspect this when ALL apply:

- macOS with Homebrew (Apple Silicon: `/opt/homebrew/...`; Intel: `/usr/local/...`)
- A tool you trust to be installed (ffmpeg, librsvg, opencv, etc.) acts as if
  it's missing
- `which TOOL` returns a path but `TOOL --version` produces no output
- You recently ran `brew upgrade` (or another formula's upgrade pulled in a
  new x265/x264/libvpx/etc. version)

The Homebrew x265 formula bumped `.dylib` SO version (`libx265.215.dylib`
→ `libx265.216.dylib`) without re-pouring or relinking ffmpeg. ffmpeg's
binary is still linked against the old SO name, but only the new SO file
is on disk.

## Diagnosis

The fastest reliable check:

```bash
ffmpeg -version 2>&1 | head -3
```

- Output starts with "ffmpeg version X.Y" → fine
- Output is empty AND exit code is non-zero → broken; check `dyld` errors

To get the actual dyld error:

```bash
/opt/homebrew/bin/ffmpeg -version 2>&1
# or via Python subprocess to bypass any shell function overrides
python3 -c "import subprocess; r=subprocess.run(['ffmpeg','-version'],capture_output=True,text=True); print('rc:',r.returncode); print('stderr:',r.stderr[:1000])"
```

The dyld error names the missing dylib and the formula it comes from.

## Solution

Reinstall the broken consumer (ffmpeg in the typical case):

```bash
brew reinstall ffmpeg
```

This re-pours the bottle, which is now built against the current ABI of
its dependencies. Verify:

```bash
ffmpeg -version 2>&1 | head -3
# expect: ffmpeg version 8.1 Copyright (c) ...
```

If `brew reinstall` itself fails because OTHER dependents are broken too
(common: openai-whisper, opencv), Homebrew will try to upgrade them and may
hit `brew link` symlink conflicts. Either let it skip those (the ffmpeg
fix is independent of pytorch/opencv) or run:

```bash
brew link --overwrite <formula>
```

for each conflicting dependent, after reading what files it would overwrite.

## Verification

```bash
# 1. ffmpeg launches
ffmpeg -version 2>&1 | head -3

# 2. yt-dlp finds it
yt-dlp --check-config 2>&1 | grep -i ffmpeg

# 3. End-to-end: a download that needs merge actually merges
yt-dlp -f "bestvideo+bestaudio" --merge-output-format mp4 -o /tmp/test.mp4 \
  "https://www.youtube.com/watch?v=jNQXAC9IVRw"
ls -lh /tmp/test.mp4
```

A successful merge produces a single MP4 file. The broken state leaves the
two source streams as `.f398.mp4` + `.f140.m4a` next to each other with no
merged output.

## Notes

- The same pattern hits other Homebrew binaries: imagemagick after libpng
  bumps, opencv after numpy bumps, etc. Symptom is always identical:
  `which` succeeds, `--version` is empty, `dyld` error in stderr only.
- `brew doctor` does not detect this; it only reports ABI breakage for
  formulae you've already attempted to load.
- yt-dlp's "ffmpeg is not installed" warning is misleading: it actually
  means "ffmpeg failed to launch", not "ffmpeg binary not found".
- Audio-only operations through yt-dlp (e.g., `-x --audio-format opus`) ALSO
  require ffmpeg, so a broken ffmpeg breaks more than just merging. Caption
  download (`--write-sub`) does NOT need ffmpeg, which can hide the problem
  if your pipeline only fetches subs.
- Setting `HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1` skips the cascading
  upgrade-of-dependents step. Useful when you want to fix ffmpeg without
  touching your Python ML stack.

## References

- [Homebrew formula linking docs](https://docs.brew.sh/FAQ#why-does-brew-not-symlink) -
  explains why a formula can be installed but not linked
- [yt-dlp ffmpeg integration notes](https://github.com/yt-dlp/yt-dlp#dependencies) -
  documents what yt-dlp needs ffmpeg for and how it detects it
- Apple's [dyld documentation](https://developer.apple.com/documentation/xcode/configuring-your-app-to-use-dynamic-libraries) -
  background on macOS dynamic library loading
