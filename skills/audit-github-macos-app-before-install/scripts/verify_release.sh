#!/bin/bash
# Verify a macOS app release zip without running it: checksum, signature,
# notarisation, entitlements, embedded URLs, linked libraries.
#
# Usage: verify_release.sh <zip-url> [sha256-url] [work-dir]
#   sha256-url defaults to <zip-url>.sha256 (skipped if it 404s).
#   work-dir defaults to a fresh directory under $TMPDIR.
set -uo pipefail

ZIP_URL="${1:?usage: verify_release.sh <zip-url> [sha256-url] [work-dir]}"
SHA_URL="${2:-${ZIP_URL}.sha256}"
WORK="${3:-$(mktemp -d "${TMPDIR:-/tmp}/verify-release.XXXXXX")}"
mkdir -p "$WORK" && cd "$WORK" || exit 1

section() { printf '\n=== %s ===\n' "$1"; }

section "download"
curl -fsSL -o app.zip "$ZIP_URL" || { echo "download failed: $ZIP_URL"; exit 1; }
if curl -fsSL -o app.zip.sha256 "$SHA_URL" 2>/dev/null; then
    published="$(awk '{print tolower($1)}' app.zip.sha256)"
    local_sha="$(shasum -a 256 app.zip | awk '{print $1}')"
    echo "published: $published"
    echo "local:     $local_sha"
    [[ "$published" == "$local_sha" ]] && echo "sha256: MATCH" || echo "sha256: MISMATCH"
else
    echo "no published .sha256 at $SHA_URL (not fatal)"
    shasum -a 256 app.zip
fi

section "unpack"
ditto -x -k app.zip . || { echo "ditto failed"; exit 1; }
APP="$(find . -maxdepth 3 -name '*.app' -type d | head -1)"
[[ -n "$APP" ]] || { echo "no .app found in zip"; find . -maxdepth 2 | head; exit 1; }
echo "bundle: $APP"
BIN="$APP/Contents/MacOS/$(/usr/libexec/PlistBuddy -c 'Print CFBundleExecutable' "$APP/Contents/Info.plist" 2>/dev/null)"
echo "version: $(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist" 2>/dev/null)"
echo "bundle id: $(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Contents/Info.plist" 2>/dev/null)"

section "codesign -dvv (want Developer ID Application + runtime flag + stapled ticket)"
codesign -dvv "$APP" 2>&1 | grep -E 'Authority|TeamIdentifier|flags=|Notarization|Timestamp|Format'

section "codesign --verify --deep --strict"
codesign --verify --deep --strict --verbose=2 "$APP" 2>&1

section "spctl (want: accepted, source=Notarized Developer ID)"
spctl -a -vv -t exec "$APP" 2>&1

section "stapler validate"
xcrun stapler validate "$APP" 2>&1 | tail -1

section "entitlements"
codesign -d --entitlements - "$APP" 2>/dev/null | grep -E '\[Key\]' | sed 's/.*\[Key\] //'

section "URLs embedded in binary (cross-check against source grep)"
strings -n 8 "$BIN" | grep -oiE 'https?://[a-z0-9./_?=-]+' | sort -u

section "sharp strings in binary"
strings -n 6 "$BIN" | grep -E 'dangerously|/bin/(ba|z)?sh|osascript|xattr|quarantine|base64' | sort -u | head -20

section "non-system dynamic libraries (want: none)"
otool -L "$BIN" | tail -n +2 | grep -v '/System/\|/usr/lib/' || echo "(none)"

section "bundled frameworks / helpers"
find "$APP/Contents" -maxdepth 2 \( -name 'Frameworks' -o -name 'XPCServices' -o -name 'Library' -o -name 'Helpers' \) -exec ls -1 {} \; 2>/dev/null || true
echo "(empty = nothing bundled beyond the main binary)"

printf '\nwork dir: %s\n' "$WORK"
