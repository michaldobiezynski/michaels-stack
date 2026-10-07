---
name: cc-video-corpus-sourcing-2026
description: |
  Source Creative-Commons video corpora that agents and third parties can actually
  download and reuse (verified Aug 2026). Use when: (1) building a reproducible video
  eval/demo corpus, (2) yt-dlp fails with "Sign in to confirm you're not a bot"
  (YouTube) or "The web client only works when logged-in" (Vimeo), (3) you need to
  verify a video's CC licence programmatically, (4) deciding whether an ND-licensed
  video can be clipped. Covers the archive.org metadata API licence check, the
  YouTube/Vimeo anonymous-access shutdowns, and licence gotchas (ND forbids clips,
  NC vs commercial artefacts).
author: Claude Code
version: 1.0.0
date: 2026-08-28
---

# Sourcing CC video corpora agents can download (2026)

## Problem

A corpus that must be re-fetched by other people from a clean environment (judges, CI, collaborators) cannot sit behind bot walls or ambiguous licences. As of mid-2026 the two obvious sources are both closed to anonymous tooling, and licence subtleties can invalidate a corpus after the work is done.

## Context / Trigger Conditions

- `yt-dlp --dump-json <youtube-url>` fails with `ERROR: Sign in to confirm you're not a bot` on every video, including controls. Real platform-side hardening, not misconfiguration: yt-dlp/yt-dlp#15865 (open since 02/2026). Player-client spoofs (tv, ios, web_embedded, mweb, web_safari) all return LOGIN_REQUIRED. Note the asymmetry: `ytsearch...:--flat-playlist` search still works, so you can gather candidate IDs but not licence fields or downloads.
- `yt-dlp <vimeo-url>` fails with `ERROR: [vimeo] <id>: The web client only works when logged-in` - platform-wide anonymous API removal as of 07/2026, yt-dlp/yt-dlp#17271. `--impersonate chrome` (curl_cffi) does not help; the block is server-side, not fingerprinting.
- `--cookies-from-browser chrome` hangs in non-interactive sessions: it needs a macOS Keychain unlock click. `--cookies-from-browser safari` fails outright without Full Disk Access.

## Solution

1. **Source from archive.org** (and other direct-file hosts like Wikimedia Commons `upload.wikimedia.org` URLs): downloads are anonymous and reliable via yt-dlp (details pages) or plain curl (direct file URLs).
2. **Verify licences via the structured metadata API**, not HTML scraping: `https://archive.org/metadata/<identifier>` returns a `licenseurl` field (e.g. `http://creativecommons.org/licenses/by-sa/3.0/us/`) that drives the CC badge on the item page, plus per-file durations. Wikimedia Commons file pages render licence text server-side (WebFetch-verifiable).
3. **Licence gotchas that invalidate corpora:**
   - **ND (No-Derivatives) forbids clipping.** Trimming a video is legally a derivative work; a CC BY-NC-ND source cannot be clipped under its licence. Reject at sourcing time.
   - **NC (NonCommercial)** items are fine as analysis inputs for non-commercial projects, but do not put their imagery into artefacts that may travel commercially (reports, demo videos, published kits). Keep a CC BY / BY-SA subset for anything published, with attribution strings recorded per item.
   - Items with no `licenseurl` set are unverifiable - reject even when a mirror claims CC.
4. **Reproducibility beats diversity:** if a source's fetch path is bot-walled for you today, it will be bot-walled for whoever reproduces the work; exclude the platform even if you could manually verify licences another way. Record the exclusion and reasoning in the corpus documentation.
5. Rich hunting grounds on archive.org beyond the obvious: `ourmedia` and `cooking_movies` collections (2005-2010 user uploads, varied physical sets), Jupiter Broadcasting / Revision3 show archives (CC-badged podcast episodes).

## Verification

Confirmed 28/08/2026: 16 archive.org items licence-verified via the metadata API and downloaded unauthenticated (~6GB) while the same session's YouTube and Vimeo metadata calls failed with the errors above.

## Notes

- The one-time interactive fix for YouTube (`yt-dlp --cookies-from-browser chrome` plus a Keychain "Always Allow" click) restores metadata access on that machine only - useless for third-party reproduction, acceptable for personal research.
- Related: [[claude-ai-share-link-fetch]] (a different bot-wall with a different escape hatch).
