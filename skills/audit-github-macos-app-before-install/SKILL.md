---
name: audit-github-macos-app-before-install
description: |
  Static safety audit of a GitHub-hosted macOS app before installing it, answering
  "is it safe to install https://github.com/<owner>/<repo>?". Use when: (1) the user
  pastes a GitHub URL for a native Mac app (.app / Swift / Tauri / Electron) and asks
  if it is safe, trustworthy, or malware, (2) you need to verify a release zip/dmg is
  really Developer-ID signed and Apple-notarised rather than trusting the README,
  (3) an app asks for Accessibility, Screen Recording, camera or mic and you want to
  know what actually leaves the machine, (4) an app has a self-updater and you need
  to know whether updates bypass Gatekeeper. Covers: source audit (deps, URLs,
  Process/shell spawns, deleted-file history), release-binary verification (sha256
  vs published checksum, codesign -dvv, --strict verify, spctl, stapler, strings
  cross-check against source, otool -L), repo/owner metadata via gh api, and the
  recurring findings patterns (quarantine-stripping updaters, agent hand-off with
  --dangerously-skip-permissions, user-configured shell runners). Also covers the
  `curl -fsSL https://x/install.sh | sh` CLI-binary variant (Rust/Go single binary,
  no .app): read install.sh first, triple-check sha256 against the vendor manifest
  AND the GitHub release asset `digest`, and know that `adhoc,linker-signed` plus
  `spctl: rejected` is NORMAL there, not a red flag. Nothing is executed until the
  audit is done; everything is read or inspected.
author: Claude Code
version: 1.1.0
date: 2026-09-02
---

# Audit a GitHub-hosted macOS app before installing it

## Problem

"Is it safe to install X?" cannot be answered from the README, the star count,
or a scan of file names. The three things that actually settle it are (a) what
the source does with the network and with `Process`, (b) whether the shipped
binary is the same code, signed by an identity Apple can revoke, and (c) what
the app can do *by design* once granted permissions. All three are checkable in
a few minutes without running the app, but the commands are spread across
git, gh, codesign, spctl, stapler, strings and otool, and it is easy to skip
the ones that matter.

## Context / Trigger Conditions

- User message shaped like "is it safe to install <github url>", "is this
  malware", "should I trust this", "can I run this", for a macOS app.
- The repo is Swift Package / Xcode / Tauri / Electron, ships a `.app` in a
  zip or dmg under GitHub Releases, and asks for TCC permissions
  (Accessibility, Screen Recording, Camera, Microphone, Input Monitoring).
- The app has a self-updater, a "run shell command" feature, or an
  "AI agent" integration.

## Solution

Work entirely in the scratchpad. Cloning and unzipping execute nothing;
`codesign`/`spctl`/`stapler`/`strings`/`otool` only read the bundle.

### 1. Source audit (one Bash call, all read-only)

```bash
cd "$SCRATCH" && git clone --quiet https://github.com/OWNER/REPO.git && cd REPO
git log --format='%an <%ae>' | sort | uniq -c            # who wrote it
find . -path ./.git -prune -o -type f -print | head -200 # shape of the tree
cat Package.swift package.json Cargo.toml 2>/dev/null    # third-party deps
grep -rnoE 'https?://[^" )>]+' Sources/ src/ | sort -u   # every endpoint
grep -rnE 'URLSession|Process\(\)|executableURL|/bin/(ba|z)?sh|base64|osascript|SMAppService|xattr|dangerously' Sources/ src/
git log --diff-filter=D --name-only --format='' | sort -u # what it USED to do
find . -path ./.git -prune -o -type f \( -name '*.dylib' -o -name '*.so' -o -name '*.bin' -o -name '*.zip' \) -print  # committed binaries = red flag
```

Read in full, not just grep: the updater, anything that spawns a `Process`,
anything that registers a login item, the entitlements, and the release
workflow under `.github/workflows/`. Check `.github/workflows` builds from
source (`swift build` / `make app`) rather than uploading a pre-built blob.

### 2. Repo and owner metadata

```bash
gh api repos/OWNER/REPO --jq '{created_at, pushed_at, stargazers_count, forks_count, license: .license.spdx_id, homepage, fork}'
gh api users/OWNER --jq '{login, name, created_at, public_repos, followers, blog}'
gh api repos/OWNER/REPO/releases --jq '.[0:5][] | "\(.tag_name)  \(.published_at)  \([.assets[].name] | join(","))"'
```

A young repo with an old, populated owner account is normal for a side
project. A young repo AND a young owner account with no other repos is not
proof of malice, but it removes the reputational signal, so weight the
binary checks more heavily.

### 3. Release-binary verification (the part the README cannot fake)

Run the bundled helper against the latest release asset:

```bash
~/.claude/skills/audit-github-macos-app-before-install/scripts/verify_release.sh \
  https://github.com/OWNER/REPO/releases/latest/download/App.zip
```

It downloads the zip and its `.sha256` sibling (if published), compares the
hash, unzips with `ditto`, then prints: `codesign -dvv` (look for
`Authority=Developer ID Application: <name> (<TEAMID>)`,
`flags=0x10000(runtime)`, `Notarization Ticket=stapled`),
`codesign --verify --deep --strict`, `spctl -a -vv -t exec` (must say
`accepted` and `source=Notarized Developer ID`), `xcrun stapler validate`,
the embedded entitlements, every URL in the binary's strings, every
`dangerously`/`/bin/sh`/`osascript` string, and `otool -L` filtered to
non-system libraries.

Then **cross-check**: the URL list from `strings` must be a subset of the
URL list from the source grep in step 1. Any host in the binary that is
not in the source means the shipped bytes were not built from the shown
code.

### 4. Classify what you found

Report in three buckets, and keep them separate:

| Bucket | Examples |
|---|---|
| Hidden behaviour (verdict-changing) | Undisclosed endpoint, telemetry, obfuscated/base64 payload, committed binary, ad-hoc or missing signature on a "notarised" release, strings/source mismatch |
| By-design power (disclose, not a flaw) | Accessibility control, login item on by default, user-configured shell runner, camera/mic |
| Trust-chain weakness (moderate, note it) | Self-updater that verifies integrity only and strips quarantine; agent hand-off with permission bypass; no build provenance |

Give a verdict with a confidence label, list the by-design caveats, and
give the install command that uses the notarised release (not a source
build, which is ad-hoc signed and loses TCC grants on every rebuild).

## Verification

The audit is sound when all of these hold:

- `spctl -a -vv -t exec App.app` prints `accepted` and
  `source=Notarized Developer ID`; `xcrun stapler validate` prints
  `The validate action worked!`.
- Local `shasum -a 256` of the zip equals the published `.sha256`.
- Binary `strings` URLs are all present in the source grep.
- `otool -L` shows only `/System/` and `/usr/lib/` libraries (or the
  bundled frameworks you expected).
- You have read, not just grepped, every file that spawns a `Process`.

## Example

Pawvis (alexandriax/pawvis, v0.30.0, 02/09/2026): zero third-party deps;
endpoints in source and binary both exactly `api.github.com`,
`github.com`, `google.com/search`; Developer ID `KMZ785G889`, notarised,
stapled, `spctl` accepted; only system libs. Verdict: not malware, high
confidence. By-design caveats: Accessibility, login item on by default,
opt-in hand-off to `claude -p ... --dangerously-skip-permissions`.
Trust-chain note: updater verifies sha256 from the same GitHub release and
`codesign --verify` (no TeamIdentifier pin), then runs
`xattr -dr com.apple.quarantine` before relaunch, so Gatekeeper never
re-assesses updates; installs only on a user click.

## Notes

- `codesign --verify` proves the seal is intact, not who sealed it. An
  updater that relies on it and then strips quarantine has turned "trust
  Apple's notarisation" into "trust the GitHub account". Pin the
  `TeamIdentifier` (compare `codesign -dvv` output) if you ever write one.
- Deleted files in history (`--diff-filter=D`) are the fastest way to see a
  project's earlier privacy posture (e.g. a removed cloud transcription
  provider). Not a red flag on its own, but worth a sentence.
- `spctl -a -t exec` still works on macOS 26 (Darwin 25) even though
  `spctl --master-disable` was removed in Sequoia.
- A Homebrew cask committed to the repo often pins an old version; check
  its `version` against the latest release before recommending it.
- No build attestation on GitHub Releases means you cannot prove the zip
  came from CI. Say so with a Moderate label; signature + notarisation
  still cover the bytes.
- Do not run the app to "see what it does". Static checks plus
  notarisation are enough for a verdict; running it grants nothing extra
  and risks the TCC prompts you were trying to reason about.

## Variant: `curl | sh` CLI binary (no .app bundle)

Rust/Go tools such as Herdr ship a bare Mach-O via `curl -fsSL https://x/install.sh | sh`.
The steps above mostly transfer, but two of the verification rules would give a
WRONG verdict if applied literally. Verified on Herdr v0.8.2, 02/09/2026.

1. **Read the script, don't pipe it.** `curl -fsSL URL -o "$SCRATCH/install.sh"`
   and read all of it. Good signs: reads a manifest, checks a sha256, `mv` into
   `~/.local/bin`, no `sudo`, no edits to `.zshrc`/`.bashrc`, no `xattr -d`.
2. **Triple-check the hash.** Download the same asset the script would, then
   compare three values that come from three different places:
   ```bash
   shasum -a 256 herdr.bin                                      # local bytes
   curl -fsSL https://x/latest.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["sha256"]["macos-aarch64"])'   # vendor manifest
   gh api repos/O/R/releases/tags/TAG --jq '.assets[] | select(.name=="ASSET") | .digest'   # GitHub-computed
   ```
   GitHub now publishes a `digest` (`sha256:...`) on every release asset, so
   the vendor's manifest cannot lie without the GitHub digest disagreeing.
   Do not `cat` the manifest: release-notes fields can be 100 KB+ and flood
   the tool result; extract fields with python/jq.
3. **Expect ad-hoc signing and `spctl: rejected`.** A curl-installed CLI is
   typically `flags=0x20002(adhoc,linker-signed)`, `TeamIdentifier=not set`,
   `Signature=adhoc`, and `spctl -a -t exec` prints `rejected`. This is the
   norm for Rust/Go release binaries, not evidence of tampering, and it does
   not block execution because curl (unlike a browser) sets no
   `com.apple.quarantine` xattr, so Gatekeeper never assesses it. The
   consequence is that there is no Apple-revocable identity; shift the weight
   to the CI provenance check below and to `strings`/`otool -L`.
4. **Check CI builds from source.** In `.github/workflows/release.yml` look
   for `cargo build --release --locked` (or `go build`) and for the step that
   writes the vendor manifest; `strings` paths like `/Users/runner/.cargo/...`
   inside the binary corroborate a GitHub-hosted runner. Label provenance
   Moderate unless there is a build attestation.
5. **Exercise a TUI-only daemon without a TTY.** If the tool opens a TUI by
   default, use its headless server sub-command to prove it runs
   (Herdr: `herdr server &`, `herdr status`, `herdr server stop`) instead of
   launching the TUI from a non-interactive shell.

Verdict template for this variant: hash triple-match + CI-from-source +
endpoints all vendor/GitHub + no persistence strings (`LaunchAgents`,
`launchctl`, `crontab`, `.zshrc`) = install, High on the bytes, Moderate on
provenance. Say explicitly that it is not notarised and why that is expected.
