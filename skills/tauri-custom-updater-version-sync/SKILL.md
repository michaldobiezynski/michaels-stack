---
name: tauri-custom-updater-version-sync
description: |
  Fix Tauri v2 auto-updater silently failing to deliver new releases
  when using a custom HTTP updater endpoint (Next.js API route, Cloudflare
  Worker, Express server, etc.). Use when: (1) a new release has been
  tagged, built, signed and uploaded to the CDN, but installed clients
  never auto-update, (2) the updater endpoint returns HTTP 204 "no
  update available" despite a newer version existing on the CDN,
  (3) hitting `/updates?current_version=<OLD>&target=...&arch=...`
  returns 204 or an old version, (4) `/download` page still links to
  the previous release version. Root cause is usually a hardcoded
  version constant in the updater endpoint source that wasn't bumped
  alongside the Tauri app's Cargo.toml and package.json. Covers the
  release-process blind spot and gives a copy-pasteable pre-merge
  checklist.
author: Claude Code
version: 1.0.0
date: 2026-04-11
---

# Tauri Custom Updater Version Sync

## Problem

You release a new version of a Tauri v2 desktop app by:

1. Bumping `Cargo.toml` + `package.json` versions
2. Building and signing the artefacts
3. Uploading them to your CDN (Cloudflare R2, S3, GitHub Releases, etc.)
4. Verifying the URLs return HTTP 200

...and then no user ever receives the update, because their installed
app's auto-updater silently keeps reporting "already on latest".

The root cause is that Tauri v2 apps using a **custom HTTP updater
endpoint** (set via `plugins.updater.endpoints` in `tauri.conf.json`)
typically have **two separate version sources of truth**:

1. The Tauri app's `Cargo.toml` / `package.json` — what gets baked into
   the installed binary as `current_version`
2. The updater endpoint's server-side version constant — what the
   endpoint compares `current_version` against to decide whether to
   return an update

A release that only bumps (1) will silently fail to reach users,
because the endpoint still returns "no update" from its stale (2).

## Context / Trigger Conditions

All of the following usually apply:

- Tauri v2 app with `updater` plugin enabled
- `tauri.conf.json` has `plugins.updater.endpoints: ["https://.../updates?..."]`
  pointing at a custom HTTP endpoint (not GitHub Releases directly)
- The endpoint is a Next.js API route, Cloudflare Worker, Express
  server, or similar server-side code in a **separate repository** or
  at least a separate source file from the Tauri app
- A release has been tagged, built, signed, and uploaded to the CDN
- CDN URLs return HTTP 200 when hit directly
- Installed clients on the previous version never see an update
  notification and never auto-update
- Hitting the updater endpoint manually with a curl request using the
  previous version as `current_version` returns 204 or the old version:

  ```bash
  curl -v "https://your-site/updates?target=darwin&arch=aarch64&current_version=0.15.1"
  # HTTP/2 204 ← bug symptom
  ```

- Grepping the updater source for the old version finds it hardcoded:

  ```bash
  grep -rn "0\.15\.1" path/to/updater/endpoint/
  # src/lib/downloads.ts:1:export const APP_VERSION = "0.15.1";
  ```

## Solution

### Immediate fix

Bump the version constant in the updater endpoint source to match the
new release, then redeploy:

```typescript
// Before
export const APP_VERSION = "0.15.1";
export const RELEASE_DATE = "2026-04-04T12:00:00Z";
export const RELEASE_NOTES = "...";

// After
export const APP_VERSION = "0.16.0";
export const RELEASE_DATE = "2026-04-11T21:32:20Z";
export const RELEASE_NOTES = "...new-version release notes...";
```

Deploy the updater repo (Vercel, Cloudflare Pages, etc.). Verify:

```bash
curl -v "https://your-site/updates?target=darwin&arch=aarch64&current_version=0.15.1"
# HTTP/2 200, JSON body with "version": "0.16.0"
```

### Permanent fix: single source of truth

The cleanest long-term fix is to stop hardcoding the version in the
updater endpoint at all. Options:

1. **Scan the CDN at request time.** The endpoint lists the latest
   version directory on the CDN and returns whatever it finds. Works
   for Cloudflare R2 via the S3-compatible API or a Worker with the R2
   binding; for GitHub Releases via the `/latest` API.

2. **Read from `latest.json`.** Tauri release scripts can generate a
   `latest.json` manifest with the version and signatures. Have the
   updater endpoint `fetch()` that file from the CDN and use it as the
   source of truth.

3. **Cross-repo shared constant.** Publish a small NPM/GitHub package
   containing just the version constant, bump it in CI whenever the
   Tauri repo bumps, and import it in both places.

4. **CI automation.** Have the Tauri repo's release workflow open a
   follow-up PR on the updater repo bumping the constant. Reduces the
   manual step without removing it.

## Verification

Before claiming a release is "shipped to users":

1. **Hit the updater endpoint from the command line with the OLD
   version**, not the new one. This simulates what an installed client
   does:

   ```bash
   OLD_VERSION="0.15.1"
   curl -sv "https://your-site/updates?target=darwin&arch=aarch64&current_version=$OLD_VERSION" 2>&1 \
     | head -40
   ```

2. Expected response for a successful release: HTTP 200 with a JSON
   body containing the new version and a valid signature URL:

   ```json
   {
     "version": "0.16.0",
     "url": "https://cdn/.../pawn-au-chocolat_aarch64.app.tar.gz",
     "signature": "dW50cn...",
     "pub_date": "...",
     "notes": "..."
   }
   ```

3. Buggy response: HTTP 204 No Content → means the endpoint still
   thinks the client is on the latest version, which means the
   endpoint's `APP_VERSION` is stale.

4. Verify actual end-to-end by installing the previous version on a
   fresh machine and letting it check for updates. If it offers the
   new version, the chain is working.

## Release checklist (copy-paste)

For any Tauri v2 release with a custom updater endpoint:

```markdown
- [ ] Bump `package.json` version
- [ ] Bump `src-tauri/Cargo.toml` version
- [ ] Run `cargo check` to update `Cargo.lock`
- [ ] Build and sign all platform artefacts
- [ ] Upload artefacts to CDN
- [ ] Verify CDN URLs return HTTP 200
- [ ] **BUMP THE VERSION CONSTANT IN THE UPDATER ENDPOINT SOURCE**
      (e.g. src/lib/downloads.ts in the companion Next.js repo)
- [ ] Deploy the updater endpoint repo
- [ ] curl the updater endpoint with the PREVIOUS version and verify
      it returns 200 + the new version
- [ ] Only THEN announce the release / close release tickets
```

## Example

Concrete instance from pawn-au-chocolat 0.16.0 release (April 2026):

**Setup:**
- Tauri v2 desktop app at `github.com/owner/pawn-au-chocolat`
- Custom updater at `github.com/owner/chess-puzzle-creator`
  (Next.js app deployed to Vercel, routes: `/updates`, `/download`)
- `tauri.conf.json` has
  `endpoints: ["https://www.pawn-au-chocolat.com/updates?target={{target}}&arch={{arch}}&current_version={{current_version}}"]`
- Updater source imports `APP_VERSION` from `src/lib/downloads.ts`
- `/download` page renders buttons whose URLs interpolate `APP_VERSION`

**What went wrong:**
- Bumped `Cargo.toml` + `package.json` → 0.16.0 ✅
- Built, signed, notarised all 19 artefacts ✅
- Uploaded to Cloudflare R2 at `downloads.pawn-au-chocolat.com/releases/v0.16.0/` ✅
- Verified CDN returned HTTP 200 on the artefacts ✅
- Shipped the marketing copy PR in the updater repo ✅
- **Forgot to bump `src/lib/downloads.ts` APP_VERSION** ❌
- Auto-updater silently no-op'd for every installed 0.15.1 client
- `/download` page still linked to 0.15.1 URLs

**How it was caught:**
User asked "did you update the tags in the Next.js app as well for
the downloads link". A `grep -rn "0.15.1" src` in the updater repo
instantly showed the stale constant in `src/lib/downloads.ts`.

**The fix:**
One-line bump in `src/lib/downloads.ts` + redeploy the Next.js app.

## Notes

### Don't false-positive the .sig file format as "double-encoded"

When you `curl https://cdn/.../foo.app.tar.gz.sig`, the response looks
like a base64 blob (`dW50cnVzdGVkIGNvbW1lbnQ6...`). Decoding it once
yields the human-readable minisign signature
(`untrusted comment: signature from tauri secret key\n...`). It is
tempting to conclude the `.sig` file was accidentally re-encoded by an
upload step, and that the endpoint should base64-decode it before
returning. **This is wrong.**

That base64-looking content is the canonical Tauri v2 signature format.
Tauri's bundler writes `.sig` files this way deliberately, the
reference `latest.json` it generates uses the same string verbatim, and
the updater plugin base64-decodes the value internally before handing
to `minisign-verify`. The endpoint must forward the `.sig` content as
plain text, exactly as fetched. `signature.trim()` (to drop trailing
newlines) is fine; any further "decoding" breaks signature verification.

How to tell signatures are actually correct end-to-end:

```bash
curl -s https://cdn/.../foo.app.tar.gz -o foo.tar.gz
curl -s https://cdn/.../foo.app.tar.gz.sig | base64 -d -o foo.tar.gz.minisig
echo "<pubkey-base64>" | base64 -d > pubkey.pub
minisign -V -p pubkey.pub -m foo.tar.gz
# Signature and comment signature verified
```

If that minisign-verify succeeds, the artefact + sig + pubkey chain is
healthy and any user-reported "auto-update errors out" is downstream
of signature verification (network, schema, install-time permissions).

### Schema gotcha — dynamic vs static endpoints

When `tauri.conf.json` `endpoints` URL contains `{{target}}`,
`{{arch}}`, `{{current_version}}` placeholders, Tauri uses the
**dynamic endpoint contract**: the response is a flat single-platform
JSON with five fields (`version`, `url`, `signature`, `pub_date`,
`notes`) and NO `platforms.<key>` wrapper. The wrapper format is for
the static `latest.json` flow (no placeholders in the URL). Don't
"fix" a dynamic endpoint by adding a `platforms` wrapper — Tauri
won't find the keys it expects.

### Other notes

- This pitfall specifically bites **custom** updater endpoints. Apps
  that use Tauri's built-in GitHub Releases updater
  (`endpoints: ["https://github.com/.../releases/latest/download/latest.json"]`)
  don't have this problem because GitHub tracks the latest release
  automatically from the tag.
- The symptom is always **silent failure**. No error logs, no warnings,
  no Sentry event. Just "users don't upgrade". Easy to miss for days.
- A related but distinct trap: the `/download` page on your marketing
  site showing the old version. That's also usually the same constant
  and the same fix.
- `latest.json` generated by Tauri release scripts often has URLs
  pointing at GitHub Releases (the default Tauri pattern) but if your
  updater endpoint points at a CDN, the `latest.json` URLs are
  **cosmetic** — only the endpoint response matters to the actual
  updater flow. Don't let a correct-looking `latest.json` give you
  false confidence.
- When grepping for the old version to find the stale constant, also
  grep for `parseInt.*version`, `APP_VERSION`, `LATEST_VERSION`,
  `version:.*"\d`, and any hardcoded URL fragments like `/releases/v`.

## References

- [Tauri v2 Updater plugin](https://v2.tauri.app/plugin/updater/)
- [Tauri v2 Updater endpoint format](https://v2.tauri.app/plugin/updater/#server-support)
- Related skill: `tauri-v2-plugin-pitfalls` (other Tauri v2 gotchas)
- Related skill: `macos-codesign-chain-missing` (macOS signing traps
  in the same release flow)
- Related skill: `appimage-qemu-emulation-fix` (Linux AppImage build
  traps in the same release flow)
- Related skill: `release-download-link-verification` (verify all
  download URLs return HTTP 200 after upload)
