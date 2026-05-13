---
name: appimage-qemu-emulation-fix
description: |
  Fix AppImage creation failures when building inside Docker linux/amd64
  containers on Apple Silicon (arm64) Macs under QEMU emulation. Use when:
  (1) appimagetool self-extraction silently fails with "cannot execute binary
  file: Exec format error" inside a --platform linux/amd64 container,
  (2) `./appimagetool-x86_64.AppImage --appimage-extract` produces no
  squashfs-root directory despite the file being a valid ELF, (3) the
  Tauri v2 release flow for Linux AppImages breaks on M1/M2/M3/M4 Macs,
  (4) other x86_64 static binaries like ripgrep run fine under the same
  container but AppImages do not. Workaround: bypass appimagetool entirely
  and build the AppImage using mksquashfs + the standalone type2-runtime
  binary (which is PIE and works under emulation).
author: Claude Code
version: 1.1.0
date: 2026-04-15
---

# AppImage Build Fix for Docker QEMU Emulation on Apple Silicon

## Problem

Building an AppImage inside a `linux/amd64` Docker container on an arm64 Mac
(Apple Silicon) using `appimagetool-x86_64.AppImage --appimage-extract` fails
with `Exec format error`, even though Docker explicitly runs the container
under `--platform linux/amd64` and other static x86_64 binaries (ripgrep, ls,
etc.) execute fine under the same emulation.

This breaks Tauri v2 release scripts that download appimagetool to
`/root/.cache/tauri`, chmod +x it, and try to self-extract.

## Context / Trigger Conditions

All of the following must be true:
- Host: Apple Silicon Mac (arm64)
- Docker Desktop (any recent version) with Rosetta 2 for Linux or QEMU emulation
- Container: `--platform linux/amd64`
- Trying to execute `appimagetool-x86_64.AppImage` (any version: continuous, 1.9.0, v13…)

Symptoms:
- `file appimagetool-x86_64.AppImage` reports `ELF 64-bit LSB executable, x86-64, ..., statically linked`
- `readelf -h` shows `Type: EXEC (Executable file)` — the critical detail
- `./appimagetool-x86_64.AppImage --appimage-extract` silently produces nothing, no `squashfs-root` directory
- Running the binary explicitly prints: `bash: ./appimagetool-x86_64.AppImage: cannot execute binary file: Exec format error`
- Meanwhile, other static x86_64 binaries like ripgrep (`rg`) **run fine**
  in the same container. `readelf -h` on those shows `Type: DYN
  (Position-Independent Executable file)` — they are PIE, not EXEC.

The root cause is that Docker Desktop's QEMU/Rosetta emulation for amd64 on
arm64 hosts can execute position-independent (`DYN`/PIE) static binaries
but refuses traditional `EXEC`-type static binaries. `appimagetool` is
released as a traditional EXEC binary, so it can never run under this
emulation setup regardless of chmod, platform flags, or apt packages.

## Solution

Bypass `appimagetool` entirely. An AppImage is structurally just:

```
[runtime ELF][squashfs image of AppDir]
```

So you can build one with only two ingredients:

1. **A squashfs image** built with `mksquashfs` (a standard Debian/Ubuntu
   tool, pure C, ships as a PIE binary, runs fine under emulation)
2. **The AppImage type2 runtime binary** downloaded separately from
   https://github.com/AppImage/type2-runtime/releases — this runtime is
   distributed as a **static-PIE** binary and runs fine under emulation

Concatenating them produces a valid, executable AppImage.

### Step-by-step

Inside the container (install the tools first):

```bash
apt-get update -qq
apt-get install -qq -y squashfs-tools wget
```

Build your AppDir the normal way (binary + .desktop + icon + AppRun), then:

```bash
cd /path/to/bundle/appimage

# 1. Create squashfs from the AppDir
mksquashfs YourApp.AppDir app.squashfs \
  -root-owned -noappend -no-xattrs -comp zstd \
  -mkfs-time 0 -all-time 0 -quiet

# 2. Download the PIE runtime
wget -q https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 -O runtime

# 3. Concatenate = valid AppImage
cat runtime app.squashfs > YourApp_x.y.z_amd64.AppImage
chmod +x YourApp_x.y.z_amd64.AppImage

# 4. Clean up intermediates
rm -f runtime app.squashfs
```

The resulting AppImage is identical in format to one produced by
`appimagetool` — same runtime, same squashfs body — and users on real Linux
x86_64 systems can run it normally.

## Verification

1. Check the runtime is PIE before using:
   ```bash
   readelf -h runtime-x86_64 | grep Type
   # Should show: Type: DYN (Position-Independent Executable file)
   ```

2. Confirm the resulting file is recognised as an AppImage:
   ```bash
   file YourApp_x.y.z_amd64.AppImage
   # Should show: ELF 64-bit LSB pie executable, x86-64, ...
   ```

3. On a real amd64 Linux machine (or a proper Linux VM, not Docker under
   QEMU), `./YourApp_x.y.z_amd64.AppImage` should launch the app.

4. Check file size is reasonable:
   - Runtime is ~944 KB
   - Your squashfs will be a few MB to ~15 MB for typical apps
   - Total AppImage ~15 MB for a Tauri app

## Diagnostic: is this actually your bug?

Run this inside the container to prove the root cause:

```bash
apt-get install -qq -y file wget > /dev/null 2>&1
wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
wget -q https://github.com/BurntSushi/ripgrep/releases/download/14.1.0/ripgrep-14.1.0-x86_64-unknown-linux-musl.tar.gz
tar xzf ripgrep-*.tar.gz

chmod +x appimagetool-x86_64.AppImage
readelf -h appimagetool-x86_64.AppImage | grep Type   # EXEC (Executable file)
readelf -h ripgrep-*/rg | grep Type                   # DYN (Position-Independent Executable file)

./appimagetool-x86_64.AppImage --version 2>&1         # "cannot execute binary file"
./ripgrep-*/rg --version 2>&1                         # "ripgrep 14.1.0" — works fine
```

If you see EXEC + "Exec format error" for appimagetool AND DYN + working
execution for ripgrep, your diagnosis is confirmed.

## Example: pawn-au-chocolat local-release.sh fix

The project's `scripts/local-release.sh` originally used this failing
pattern inside a Docker container:

```bash
wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
./appimagetool-x86_64.AppImage --appimage-extract > /dev/null 2>&1
mv squashfs-root appimagetool
# ...
ARCH=x86_64 /root/.cache/tauri/appimagetool/AppRun YourApp.AppDir YourApp.AppImage
```

Replace the entire block with:

```bash
mksquashfs YourApp.AppDir app.squashfs \
  -root-owned -noappend -no-xattrs -comp zstd -mkfs-time 0 -all-time 0 -quiet
wget -q https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 -O runtime
cat runtime app.squashfs > YourApp_$VERSION_amd64.AppImage
chmod +x YourApp_$VERSION_amd64.AppImage
rm -f runtime app.squashfs
```

## Red herrings — things that look like fixes but aren't

- **`APPIMAGE_EXTRACT_AND_RUN=1`** — commonly suggested online as "the fix"
  for AppImage extraction issues. It does NOT help here. That env var tells
  the AppImage to self-extract before running, but the extraction step
  itself requires executing the appimagetool binary, which is what QEMU
  refuses to do. You can verify: with or without the env var, you still
  get `cannot execute binary file: Exec format error`. Don't waste a
  commit on it.
- **Re-chmodding, adding FUSE, installing libfuse2** — the failure is not
  permissions, not FUSE, not missing deps. It's that the binary format
  (`EXEC` not `DYN`) is incompatible with the emulator. No userspace
  change can fix it.
- **Switching to `--platform linux/arm64`** — defeats the purpose (you'd
  produce an arm64 AppImage, not an amd64 one) and also loses access to
  the x86_64 type2 runtime you need to ship to users.

## Notes

- This issue is specific to running appimagetool **under emulation**. On
  a native linux/amd64 host (GitHub Actions Ubuntu runners, physical x86
  Linux, a real amd64 VM) the original appimagetool approach works fine.
- The fix does NOT require `FUSE` or `libfuse` in the container — neither
  mksquashfs nor prepending a runtime needs mounting.
- `-comp zstd` requires squashfs-tools ≥4.4 (Ubuntu 22.04+ has it). Use
  `-comp xz` or omit for older versions.
- If you need to produce a non-amd64 AppImage (arm64 Linux), download
  `runtime-aarch64` from the same type2-runtime release page.
- The symptom is not specific to AppImage versions. Tried 1.9.0, 13, and
  continuous — all fail the same way for the same reason.
- Do NOT enable Rosetta 2 for Linux in Docker Desktop as a fix — it has
  its own set of issues and is not a drop-in replacement.

## References

- [AppImage type2-runtime releases](https://github.com/AppImage/type2-runtime/releases) — where the PIE runtime binary comes from
- [AppImage format spec](https://github.com/AppImage/AppImageSpec/blob/master/draft.md) — "runtime + squashfs" structure
- [Docker QEMU emulation on macOS](https://docs.docker.com/desktop/features/rosetta/) — background on why some x86 binaries fail
- ELF `EXEC` vs `DYN`: https://refspecs.linuxfoundation.org/elf/elf.pdf (section on e_type)
- Related skill: `release-download-link-verification` (verify all
  download URLs return HTTP 200 after upload)
