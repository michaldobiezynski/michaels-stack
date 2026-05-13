---
name: release-download-link-verification
description: |
  Verify all download links return HTTP 200 after a desktop app release.
  Use when: (1) uploading new release artefacts to a CDN (Cloudflare R2,
  S3, GitHub Releases), (2) bumping version constants in a marketing
  site or download page, (3) updating latest.json or auto-updater
  manifests, (4) any step in a release pipeline that changes download
  URLs. Catches broken links caused by missing uploads, wrong version
  strings, filename mismatches, or CDN propagation delays. Covers both
  the CDN artefact layer and the marketing/download page layer.
author: Claude Code
version: 1.0.0
date: 2026-04-12
---

# Release Download Link Verification

## Problem

Desktop app releases involve multiple layers that must stay in sync:
CDN artefacts, marketing site version constants, download page URLs,
and auto-updater manifests. A version bump or upload that misses even
one artefact silently breaks download links for an entire platform.
Users see 404 errors, broken install buttons, or stale versions with
no error on the release side.

Common causes of broken download links:
- Artefact build failed for one platform but the release continued
- Version string in download URL template doesn't match uploaded filename
- Upload script skipped a file (non-fatal warning went unnoticed)
- Marketing site version bumped before artefacts were uploaded
- latest.json points to old URLs or missing platform entries
- CDN cache serving stale 404 responses after a delayed upload

## Context / Trigger Conditions

Run this verification whenever ANY of these happen:
- New artefacts uploaded to CDN (R2, S3, GitHub Releases)
- Version constant changed in marketing site / download page source
- latest.json or updater manifest regenerated
- Marketing site deployed (Vercel, Netlify, Cloudflare Pages)
- Any release phase marked "complete"

## Solution

### Layer 1: CDN artefact verification

After uploading, verify every artefact URL returns HTTP 200. Check
the full set for all platforms, not just the one you just uploaded.

```bash
VERSION="0.17.0"
BASE="https://downloads.your-app.com/releases/v${VERSION}"

echo "=== CDN Artefact Verification ==="

URLS=(
  # macOS
  "${BASE}/your-app_${VERSION}_aarch64.dmg"
  "${BASE}/your-app_${VERSION}_x64.dmg"
  "${BASE}/your-app_aarch64.app.tar.gz"
  "${BASE}/your-app_aarch64.app.tar.gz.sig"
  "${BASE}/your-app_x64.app.tar.gz"
  "${BASE}/your-app_x64.app.tar.gz.sig"
  # Linux
  "${BASE}/your-app_${VERSION}_amd64.AppImage"
  "${BASE}/your-app_${VERSION}_amd64.AppImage.sig"
  "${BASE}/your-app_${VERSION}_amd64.AppImage.tar.gz"
  "${BASE}/your-app_${VERSION}_amd64.AppImage.tar.gz.sig"
  "${BASE}/your-app_${VERSION}_amd64.deb"
  "${BASE}/your-app_${VERSION}_amd64.deb.sig"
  # Windows
  "${BASE}/your-app_${VERSION}_x64-setup.exe"
  "${BASE}/your-app_${VERSION}_x64-setup.exe.sig"
  "${BASE}/your-app_${VERSION}_x64-setup.nsis.zip"
  "${BASE}/your-app_${VERSION}_x64-setup.nsis.zip.sig"
  # Manifest
  "${BASE}/latest.json"
)

FAILED=0
for url in "${URLS[@]}"; do
  STATUS=$(curl -sI -o /dev/null -w "%{http_code}" "$url")
  if [ "$STATUS" = "200" ]; then
    echo "  OK   $url"
  else
    echo "  FAIL ($STATUS) $url"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
if [ "$FAILED" -gt 0 ]; then
  echo "RESULT: $FAILED URL(s) failed verification"
  exit 1
else
  echo "RESULT: All URLs return HTTP 200"
fi
```

### Layer 2: Marketing site / download page verification

After deploying the marketing site, verify the download page URLs
match the CDN artefacts. The marketing site typically constructs URLs
from a version constant:

```typescript
// src/lib/downloads.ts
const R2_BASE_URL = `https://downloads.your-app.com/releases/v${APP_VERSION}`;
// URLs like: ${R2_BASE_URL}/your-app_${APP_VERSION}_x64-setup.exe
```

Verify by:
1. Checking the version constant matches the release version
2. Hitting each constructed URL from the download page config

```bash
# Extract version from marketing site source
SITE_VERSION=$(grep 'APP_VERSION' src/lib/downloads.ts | head -1 | grep -o '"[^"]*"' | tr -d '"')
echo "Marketing site version: $SITE_VERSION"
echo "Expected version: $VERSION"

if [ "$SITE_VERSION" != "$VERSION" ]; then
  echo "MISMATCH: Marketing site still shows $SITE_VERSION"
  exit 1
fi
```

### Layer 3: Auto-updater manifest verification

The latest.json must contain valid signatures and URLs for every
platform the updater supports:

```bash
echo "=== Updater Manifest Verification ==="
MANIFEST=$(curl -s "${BASE}/latest.json")

# Check version matches
MANIFEST_VERSION=$(echo "$MANIFEST" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])")
echo "Manifest version: $MANIFEST_VERSION"

# Check all platform entries exist
for PLATFORM in "darwin-x86_64" "darwin-aarch64" "linux-x86_64" "windows-x86_64"; do
  SIG=$(echo "$MANIFEST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['platforms']['$PLATFORM']['signature'][:20])" 2>/dev/null)
  URL=$(echo "$MANIFEST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['platforms']['$PLATFORM']['url'])" 2>/dev/null)

  if [ -z "$SIG" ] || [ -z "$URL" ]; then
    echo "  MISSING: $PLATFORM entry not found in latest.json"
  else
    STATUS=$(curl -sI -o /dev/null -w "%{http_code}" "$URL")
    echo "  $PLATFORM: sig=${SIG}... url=$STATUS"
  fi
done
```

### Layer 4: Cross-layer consistency check

The most insidious bugs happen when layers disagree. Run this final
check to catch version drift:

```bash
echo "=== Cross-Layer Consistency ==="

# 1. CDN artefact version (from filenames)
CDN_VERSION=$(curl -sI "${BASE}/your-app_${VERSION}_aarch64.dmg" -o /dev/null -w "%{http_code}")

# 2. Marketing site version (from source)
SITE_VERSION=$(grep 'APP_VERSION' path/to/marketing/src/lib/downloads.ts | head -1 | grep -o '"[^"]*"' | tr -d '"')

# 3. Updater manifest version (from latest.json)
MANIFEST_VERSION=$(curl -s "${BASE}/latest.json" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])")

# 4. Desktop app version (from package.json)
APP_VERSION=$(node -p "require('./package.json').version")

echo "Desktop app:      $APP_VERSION"
echo "CDN artefacts:    $([ "$CDN_VERSION" = "200" ] && echo "$VERSION" || echo "MISSING")"
echo "Marketing site:   $SITE_VERSION"
echo "Updater manifest: $MANIFEST_VERSION"

if [ "$APP_VERSION" = "$SITE_VERSION" ] && [ "$APP_VERSION" = "$MANIFEST_VERSION" ] && [ "$CDN_VERSION" = "200" ]; then
  echo "All layers consistent."
else
  echo "VERSION DRIFT DETECTED - fix before announcing release."
fi
```

## When to run each layer

| Release step                       | Layer 1 | Layer 2 | Layer 3 | Layer 4 |
|-------------------------------------|---------|---------|---------|---------|
| After uploading artefacts to CDN    | Yes     |         | Yes     |         |
| After deploying marketing site      |         | Yes     |         | Yes     |
| After regenerating latest.json      |         |         | Yes     |         |
| Before announcing release           | Yes     | Yes     | Yes     | Yes     |
| After user reports broken downloads | Yes     | Yes     | Yes     | Yes     |

## Verification

The skill itself IS the verification. Success criteria:
- Every URL returns HTTP 200 (not 301, 302, 403, or 404)
- All four version sources agree
- latest.json contains entries for all supported platforms
- Each platform entry has both a non-empty signature and a reachable URL

## Example: pawn-au-chocolat 0.17.0

This release broke Linux and Windows downloads because:
1. AppImage build failed silently inside Docker (arm64 QEMU issue)
2. Windows NSIS installer build completed but zip/signing was skipped
3. Upload script warned about missing files but continued
4. Marketing site was updated with 0.17.0 URLs pointing to missing artefacts
5. latest.json only had macOS entries, missing Linux and Windows

A Layer 1 check after upload would have caught this immediately:

```
  OK   .../pawn-au-chocolat_0.17.0_aarch64.dmg
  OK   .../pawn-au-chocolat_0.17.0_x64.dmg
  FAIL (404) .../pawn-au-chocolat_0.17.0_amd64.AppImage
  FAIL (404) .../pawn-au-chocolat_0.17.0_x64-setup.exe
```

The fix required rebuilding the missing artefacts, signing them, uploading
to R2, updating latest.json with all four platform signatures, and
re-uploading. Total time to fix: ~30 minutes. Time to prevent with a
verification script: ~5 seconds.

## Integration into release scripts

Add verification as the final step of your upload script:

```bash
# At the end of upload-release.sh:
echo ""
echo "=== Post-Upload Verification ==="
FAILED=0
for url in "${ALL_URLS[@]}"; do
  STATUS=$(curl -sI -o /dev/null -w "%{http_code}" "$url")
  if [ "$STATUS" != "200" ]; then
    echo "FAIL ($STATUS): $url"
    FAILED=$((FAILED + 1))
  fi
done

if [ "$FAILED" -gt 0 ]; then
  echo ""
  echo "WARNING: $FAILED download URL(s) are not returning HTTP 200."
  echo "DO NOT update the marketing site until all URLs are live."
  exit 1
fi

echo "All $((${#ALL_URLS[@]})) download URLs verified."
```

## Notes

- CDN propagation can cause brief 404s after upload. If using Cloudflare
  R2 with a custom domain, responses are typically instant (no edge
  cache to invalidate). For CloudFront or other CDNs with edge caching,
  wait 60 seconds and retry before concluding a URL is broken.
- Signature files (.sig) are easy to forget. They don't affect direct
  downloads but break the auto-updater silently.
- The upload script should treat missing source files as errors, not
  warnings. A `set -e` won't catch this if the upload function uses
  `if [ -f ]` guards that silently skip missing files.
- Always verify ALL platforms after uploading, not just the one you
  changed. A previous partial upload may have left other platforms
  broken.
- Run verification from outside your network/VPN to catch any access
  control issues that wouldn't surface from your development machine.

## References

- [Smoke Testing in CI/CD Pipelines](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/) - patterns for post-deployment verification
- [Microsoft Engineering Fundamentals: Smoke Testing](https://microsoft.github.io/code-with-engineering-playbook/automated-testing/smoke-testing/) - HTTP 200 health checks as release gates
- [CDN Content Integrity Verification](https://www.meegle.com/en_us/topics/content-delivery-network/cdn-content-integrity-verification/) - signature and hash verification for CDN-hosted artefacts
- Related skill: `tauri-custom-updater-version-sync` (version constant drift)
- Related skill: `appimage-qemu-emulation-fix` (build failures that cause missing artefacts)
- Related skill: `macos-codesign-chain-missing` (macOS signing failures)
