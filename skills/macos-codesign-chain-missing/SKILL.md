---
name: macos-codesign-chain-missing
description: |
  Fix macOS codesign failing with "unable to build chain to self-signed
  root" + errSecInternalComponent when a .p12 export only contains the
  leaf Developer ID cert without the Apple WWDR intermediate CA. Use when:
  (1) codesign prints "Warning: unable to build chain to self-signed root
  for signer 'Developer ID Application: ...'", (2) the actual sign step
  fails with "errSecInternalComponent", (3) Tauri v2 release builds fail
  with "failed to bundle project: failed to sign app" on macOS after
  importing a .p12 into a temporary keychain, (4) `security find-identity
  -v login.keychain-db` shows the Developer ID cert but codesign still
  fails, (5) builds worked previously on the same machine and suddenly
  stopped. The fix is to install DeveloperIDG2CA.cer (or G1) into the
  login keychain so the trust chain can be built.
author: Claude Code
version: 1.0.0
date: 2026-04-11
---

# macOS Codesign "Unable to Build Chain to Self-Signed Root"

## Problem

`codesign` fails to sign a macOS app bundle with a misleading error:

```
Warning: unable to build chain to self-signed root for signer "Developer ID Application: Your Name (TEAMID)"
YourApp.app/Contents/MacOS/YourApp: errSecInternalComponent
```

This breaks Tauri v2 local release builds (`scripts/local-release.sh`) with:

```
failed to bundle project: failed to sign app
ELIFECYCLE Command failed with exit code 1.
```

The misleading error makes you think the issue is with the keychain or
the certificate itself, but the real cause is that the `.p12` file you
exported from Keychain Access (and base64'd into `APPLE_CERTIFICATE` in
`.env`) contains **only the leaf cert**, not the Apple Worldwide Developer
Relations intermediate CA that chains it back to the Apple Root CA.

## Context / Trigger Conditions

- Tauri v2 desktop app (or any macOS codesigning workflow)
- `.env` contains `APPLE_CERTIFICATE=<base64>`, `APPLE_CERTIFICATE_PASSWORD`,
  `APPLE_SIGNING_IDENTITY=Developer ID Application: ...`
- Release script imports the p12 into a temporary `build.keychain` and
  then runs `pnpm tauri build` / `codesign`
- Error appears specifically during signing of the `.app` bundle
- `security find-identity -v build.keychain` lists the identity, but
  `codesign` still fails
- Often intermittent: "it used to work" — until the environment changes
  (e.g. login keychain got wiped, Docker updated, macOS updated)

## Solution

### Diagnosis first

1. Decode and inspect the current `.p12` with openssl:
   ```bash
   PASS="$(grep APPLE_CERTIFICATE_PASSWORD= .env | cut -d= -f2-)"
   grep APPLE_CERTIFICATE= .env | head -1 | cut -d= -f2- | base64 -d > /tmp/cert.p12
   openssl pkcs12 -in /tmp/cert.p12 -nokeys -passin "pass:$PASS" -legacy 2>&1 | grep -E "friendlyName|subject=|issuer="
   rm /tmp/cert.p12
   ```

2. If the output shows **only one cert** with a leaf `subject=` (e.g.
   `Developer ID Application: Your Name`), the `.p12` is missing the
   intermediate. A proper export would show at least two certs:
   ```
   subject=CN=Developer ID Application: Your Name ...
   issuer=CN=Developer ID Certification Authority, OU=G2, O=Apple Inc., C=US
   subject=CN=Developer ID Certification Authority, OU=G2, O=Apple Inc., C=US
   issuer=C=US, O=Apple Inc., OU=Apple Certification Authority, CN=Apple Root CA
   ```

3. Find which intermediate CA generation (G1 or G2) signed your leaf cert:
   ```bash
   openssl pkcs12 -in /tmp/cert.p12 -nokeys -passin "pass:$PASS" -legacy \
     2>&1 | openssl x509 -noout -issuer
   # Look for: issuer=CN=Developer ID Certification Authority, OU=G2, ...
   ```
   - `OU=G2` → you need `DeveloperIDG2CA.cer` (newer, issued after 2021)
   - No `OU` marker → you need `DeveloperIDCA.cer` (G1, older)

4. Verify login keychain is missing the intermediate:
   ```bash
   security find-certificate -c "Developer ID Certification Authority" \
     -a ~/Library/Keychains/login.keychain-db 2>&1 | grep -E "labl|alis"
   ```
   If empty, the intermediate is missing.

### Fix

Install the correct intermediate into the login keychain. The release
script's temporary `build.keychain` is in the same keychain search list
(via `security list-keychains -d user -s build.keychain login.keychain`),
so codesign will find the intermediate in login.keychain when building
the trust chain.

```bash
# Apple's intermediates are public; download if you don't have them
curl -o /tmp/DeveloperIDG2CA.cer https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
curl -o /tmp/DeveloperIDCA.cer   https://www.apple.com/certificateauthority/DeveloperIDCA.cer

# Install both (belt-and-braces, both are Apple-signed public certs)
security add-certificates -k ~/Library/Keychains/login.keychain-db /tmp/DeveloperIDG2CA.cer
security add-certificates -k ~/Library/Keychains/login.keychain-db /tmp/DeveloperIDCA.cer
rm /tmp/DeveloperIDG2CA.cer /tmp/DeveloperIDCA.cer

# Verify
security find-certificate -c "Developer ID Certification Authority" \
  -a ~/Library/Keychains/login.keychain-db | grep "labl"
```

Then re-run your release script. The `.env` / `.p12` do NOT need to change.

### Alternative: Re-export the .p12 with the full chain

If you prefer to fix the `.p12` itself (so it's self-contained and
portable to other machines / CI secrets):

1. Open **Keychain Access** (`open /System/Applications/Utilities/Keychain\ Access.app`)
2. Find "Developer ID Application: ..." in My Certificates
3. ⌘-click to select **both** the Developer ID Application cert **and**
   the "Developer ID Certification Authority" (G2) intermediate
4. File → Export Items → save as `.p12`
5. Re-base64 and put into `.env`:
   ```bash
   base64 -i new.p12 | tr -d '\n' | pbcopy
   ```

## Verification

After the fix, re-run your release script. You should see:

```
Signing with identity "Developer ID Application: Your Name (TEAMID)"
Signing /path/to/YourApp.app/Contents/MacOS/YourApp
Signing with identity "Developer ID Application: Your Name (TEAMID)"
Signing /path/to/YourApp.app
    Built application at: /path/to/YourApp
Notarizing Finished with status Accepted for id ...
```

No more "unable to build chain" warning, no more `errSecInternalComponent`.

Verify the signed app with:

```bash
codesign -dvv YourApp.app
# Should show: Authority=Developer ID Application: ...
#              Authority=Developer ID Certification Authority
#              Authority=Apple Root CA

spctl -a -t exec -vvv YourApp.app
# Should show: source=Notarized Developer ID
```

## Example: pawn-au-chocolat session (April 2026)

Session discovered:
- `Certificates_take2.p12` and the current `APPLE_CERTIFICATE` in `.env`
  **both** contained only the leaf cert
- `~/Library/Keychains/login.keychain-db` had zero Developer ID certs
  (`security find-identity -v` → "0 valid identities found")
- `~/Documents/DeveloperIDG2CA.cer` existed (from an old-Mac migration
  folder) and was the correct intermediate for this leaf (issuer OU=G2)
- `security add-certificates -k ~/Library/Keychains/login.keychain-db \
  ~/Documents/DeveloperIDG2CA.cer` fixed the build immediately
- Subsequent signing + notarisation completed cleanly

## Notes

- **This is not a keychain lock issue.** Unlocking login.keychain won't
  help if the intermediate isn't there to find.
- **This is not a .env / base64 issue.** The base64 decodes fine and the
  p12 is valid — it just has an incomplete chain.
- **openssl 3 needs `-legacy`** to inspect a macOS-exported `.p12` because
  the files use RC2-40-CBC, which OpenSSL 3 disables by default. Without
  `-legacy` you get `unsupported RC2-40-CBC` errors that are unrelated
  to this bug.
- **G1 vs G2**: Apple issued Developer ID certs under the "G1" Certification
  Authority until Sept 2021, and under the "G2" authority since. Most
  currently-valid Developer IDs are G2-issued. You can check by looking
  at the `issuer=` of your leaf cert (`OU=G2` or absence).
- **macOS certificate rotation**: Apple periodically rotates the intermediate
  CAs. The G1 cert expires Feb 2027; G2 expires Sept 2031. When Apple
  issues a new authority, you'll need to add that as well.
- **CI builds are unaffected** because GitHub Actions' `macos-latest`
  runners come with the Apple root + WWDR intermediates pre-installed in
  their system keychain. This bug only bites local release builds where
  the user has a stripped-down login keychain.
- The Tauri `build.keychain` trap in release scripts tears down the temp
  keychain on exit, so between runs `security find-identity -v` shows
  zero identities — this is NORMAL and not the cause of this bug.

## References

- Apple Certificate Authority downloads: https://www.apple.com/certificateauthority/
- `DeveloperIDG2CA.cer` direct: https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
- `DeveloperIDCA.cer` direct (G1): https://www.apple.com/certificateauthority/DeveloperIDCA.cer
- Tauri signing docs: https://v2.tauri.app/distribute/sign/macos/
- Radar on errSecInternalComponent codesign chain errors: https://developer.apple.com/forums/thread/86161
