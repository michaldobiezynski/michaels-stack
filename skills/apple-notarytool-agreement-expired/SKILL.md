---
name: apple-notarytool-agreement-expired
description: |
  Fix Apple notarytool / notarisation failing with "HTTP status code: 403.
  A required agreement is missing or has expired". Use when: (1) Tauri v2
  macOS release builds fail at the notarisation step after codesign
  succeeded, (2) `xcrun notarytool submit` returns 403 with text about a
  required agreement, (3) CI or local-release scripts print "failed to
  notarize app" followed by "A required agreement is missing or has
  expired. This request requires an in-effect agreement that has not
  been signed or has expired", (4) a previously-working release pipeline
  suddenly stops notarising with no code changes. The fix is NOT a cert,
  keychain, or Apple ID / team ID issue - it is Apple waiting for a human
  to accept an updated legal agreement at developer.apple.com/account.
  Also covers the related gotcha where `| tee` in a release script masks
  the real non-zero exit code so the script appears to succeed.
author: Claude Code
version: 1.0.0
date: 2026-04-15
---

# Apple notarytool 403 "Agreement Missing or Expired"

## Problem

`xcrun notarytool submit` rejects every submission with:

```
failed to bundle project: Error: HTTP status code: 403. A required
agreement is missing or has expired. This request requires an in-effect
agreement that has not been signed or has expired. Ensure your team has
signed the necessary legal agreements and that they are not expired.
: failed to notarize app
```

In a Tauri v2 build this surfaces as:

```
Notarizing .../pawn-au-chocolat.app
failed to bundle project: Error: HTTP status code: 403. ...
 ELIFECYCLE  Command failed with exit code 1.
```

The misleading part: **403 and "agreement"** sound like a credentials
or permissions error (wrong Apple ID, wrong team ID, expired app-specific
password, revoked certificate). None of those is the actual cause.

The real cause is that Apple has updated one of the Developer Program
legal agreements (commonly the Paid Apps Agreement or an updated
Developer Program Licence Agreement) and is waiting for a **human in
the developer account** to read and accept it. Until someone does,
every notarisation request for that team returns 403 regardless of
how valid your credentials are.

## Context / Trigger Conditions

Strong signal that this is the root cause (vs. a credential issue):

- codesigning of the `.app` bundle **succeeded** moments earlier
- `security find-identity -v` shows a valid, unexpired Developer ID cert
- Apple ID + app-specific password + team ID all match what worked before
- No recent changes to `.env`, to the release script, or to the cert
- **Both** `notarytool history` AND `notarytool submit` return the
  **same** 403 body. Any notarytool API call for the affected team
  fails until the agreement is accepted - history is not a useful
  "credentials-vs-agreement" discriminator.
- It "used to work yesterday" with no local changes
- Often coincides with: WWDC week, end of quarter, a macOS/Xcode major
  release, Apple tax/regional expansion announcements, or a membership
  renewal anniversary

Weak signal (these could be credential issues too):

- 401 Unauthorized → credential issue, not this skill
- 403 without the word "agreement" in the body → credential/permission
  issue, not this skill
- "Team not found" → team ID typo, not this skill

Only treat 403 as agreement expiry when the body explicitly mentions
"agreement ... missing or has expired".

## Solution

There is no code fix. The account holder (or an admin with Legal role)
must accept the pending agreement in the Apple Developer portal:

1. Sign in at <https://developer.apple.com/account>
2. Open **Agreements, Tax, and Banking** (sometimes under "Membership"
   → "Legal Agreements" on newer account UIs)
3. Look for any row showing "Action Required" or a yellow/red badge —
   typical offenders:
   - Apple Developer Program Licence Agreement (free, non-paid apps)
   - Paid Applications Agreement (anyone shipping a paid macOS/iOS app
     — but also required for many notarisation scenarios)
   - Updated regional addenda (tax/banking for a new country)
4. Read + accept. Changes are effective immediately; no propagation
   delay for notarisation.
5. Re-run the release/notarisation. If still 403, check whether there
   are multiple teams under the same Apple ID — the agreement must be
   accepted for the team whose ID is in `APPLE_TEAM_ID`.

### Who can accept

- **Individual accounts:** the Apple ID holder must accept.
- **Organization accounts:** only the **Account Holder** or someone with
  the **Admin + Legal** role can accept the agreement. A plain Admin
  cannot. A Developer role definitely cannot. If you're not sure who
  holds the role, the agreements page tells you.

This is a genuine blocker — agents cannot accept the agreement for the
user. Stop, report clearly, wait for confirmation.

## Related gotcha: `| tee` hiding the failure

Release scripts that pipe through `tee` for logging mask non-zero exit
codes because bash returns the exit code of the last command in a pipe
(`tee`, which almost always succeeds):

```bash
./scripts/local-release.sh --upload 2>&1 | tee /tmp/release.log
# exit code here is always 0, regardless of whether the script failed
```

Symptom: the background task / CI step reports "completed successfully"
even though the log clearly shows `ELIFECYCLE Command failed with exit
code 1`. The `ELIFECYCLE` line is the truthful one.

Fixes (in order of preference):

```bash
# 1. pipefail — exits with first non-zero in the pipe
set -o pipefail
./scripts/local-release.sh --upload 2>&1 | tee /tmp/release.log

# 2. PIPESTATUS — inspect each stage
./scripts/local-release.sh --upload 2>&1 | tee /tmp/release.log
[ "${PIPESTATUS[0]}" -eq 0 ] || exit "${PIPESTATUS[0]}"

# 3. Avoid tee entirely for release pipelines
./scripts/local-release.sh --upload > /tmp/release.log 2>&1
```

When debugging a "release succeeded but nothing was uploaded" situation,
always `grep -E 'Error|failed|ELIFECYCLE|exit code' <log>` before trusting
the reported exit code.

## Verification

After the account holder accepts the agreement:

```bash
# Smoke test without a full rebuild
xcrun notarytool submit --apple-id "$APPLE_ID" \
                       --password "$APPLE_PASSWORD" \
                       --team-id "$APPLE_TEAM_ID" \
                       --wait \
                       path/to/some-tiny-test.zip

# Expected: "Accepted" status (or "Invalid" with a real technical reason,
# not a 403 agreement error)
```

Then re-run the full release. macOS notarisation typically takes
1-5 minutes per artefact — factor that into overall build time
(roughly 30-45 min for four macOS artefacts with signing + notarising
+ stapling).

## Example: pawn-au-chocolat 0.18.2

Attempted release after merging feature work on 2026-04-15. Build
reached macOS Intel notarisation, then:

```
Notarizing /.../pawn-au-chocolat.app
failed to bundle project: Error: HTTP status code: 403.
A required agreement is missing or has expired.
```

No artefacts produced for any platform (script exits at first macOS
failure before reaching ARM, Linux, Windows). Release script reported
exit 0 due to `| tee /tmp/pawn-release-0.18.2.log`, misleading the
caller into thinking upload had happened.

Fix: account holder accepted updated Paid Applications Agreement at
developer.apple.com/account → Agreements, Tax, and Banking → re-ran
`./scripts/local-release.sh --upload` → all 19 artefacts built and
uploaded to R2.

## Notes

- Apple does not email the account holder proactively when an agreement
  needs re-acceptance. You discover it by a failed notarisation (or by
  noticing banner notifications next time someone logs into App Store
  Connect).
- There is no way to pre-accept future agreements — each new version
  must be accepted after it's published.
- On a healthy account, `notarytool submit --wait` returns an
  "Accepted" / "Invalid" status within a few minutes. A 403 at submit
  time that's NOT about agreements is almost always a wrong
  `APPLE_TEAM_ID` for the cert, or a revoked app-specific password.
- This error also surfaces in GitHub Actions, CircleCI, and other CI
  runners using `actions/setup-xcode` + `notarytool`. CI cannot accept
  agreements; only a human in the developer portal can.
- `xcrun notarytool history` does NOT help diagnose this. When the
  agreement is pending, every notarytool call for the affected team
  returns the same 403, including history. Don't rely on "history
  works but submit fails" as a signal.
- Direct link to the agreements page (bypasses dashboard):
  <https://developer.apple.com/account/resources/agreements/view>.
  Useful when the user reports "I logged in but saw nothing pending"
  - often they were on the dashboard and never reached this page.
- If the user accepts one agreement but the error persists, there are
  almost certainly **more** pending. Apple's UI lists them one at a
  time; accepting one doesn't auto-close a simultaneously-updated
  second agreement. Ask them to return to the page and accept all.

## References

- [Apple Developer Agreements, Tax, and Banking](https://developer.apple.com/account) - log in then navigate to the Agreements section
- [`notarytool` command reference](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow) - Apple's official notarisation docs
- [Tauri v2 macOS signing guide](https://v2.tauri.app/distribute/sign/macos/) - covers the wider signing + notarisation pipeline
- Related skill: `macos-codesign-chain-missing` - a different macOS build failure (missing Apple WWDR intermediate CA in the p12); fails at `codesign` before notarisation even starts
- Related skill: `release-download-link-verification` - run Layer 1 checks after a release to confirm all platform artefacts actually uploaded; complements the tee-exit-code trap above
