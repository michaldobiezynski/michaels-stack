---
name: tauri-dev-computer-use-bundle-id
description: |
  Tauri dev binary invisible to computer-use when a production copy of the same
  app is also installed. Use when: (1) code changes appear correct but UI does
  not reflect them in screenshots, (2) open_application opens a stale UI instead
  of the tauri dev window, (3) screenshots show no trace of a window you can see
  with your own eyes, (4) list_granted_applications shows the release bundle ID
  but not the dev one, (5) running tauri dev while /Applications/<app>.app is
  also installed. Root cause is bundle-ID-based access gating in computer-use.
author: Claude Code
version: 1.0.0
date: 2026-04-14
---

# Tauri Dev Binary vs Installed App: computer-use Bundle ID Mismatch

## Problem
During `tauri dev`, `computer-use` screenshots and clicks target the installed
release copy of the app at `/Applications/<AppName>.app` instead of the dev
binary at `src-tauri/target/debug/<app>`. The dev window is physically visible
on screen but absent from screenshots, and `open_application` brings the stale
release build to the front. Code changes appear to have no effect because you
are verifying against the wrong window.

## Context / Trigger Conditions
- A prior release of the Tauri app is installed at `/Applications/<AppName>.app`
- `tauri dev` / `pnpm tauri dev` / `bun tauri dev` is running in another terminal
- Screenshot shows an older version of the UI (e.g. toolbar button missing that
  you just added in code)
- Error page / blank area shows `tauri://localhost/assets/...` asset URLs
  (indicates built bundle, not Vite dev server)
- `list_granted_applications` shows the release bundle ID (e.g.
  `org.pawnauchocolat.app`) but the dev binary uses a different bundle ID
- AppleScript can move the dev window but computer-use screenshots still
  filter it out

## Root Cause
`computer-use` gates access by bundle ID, not by window or process. When the
user approves an app via `request_access`, the granted bundle ID is the one
from the signed release `.app` bundle. The dev binary built by
`cargo tauri dev` runs with a different (or missing) bundle ID because it is
not packaged into a `.app` - it is a raw executable in `target/debug/`.

Consequences:

1. `screenshot` omits the dev window because its bundle ID is not in the grant
   list, even though the window is visible to the user's eyes and AppleScript.
2. `open_application <AppName>` resolves the installed `.app` via Launch
   Services and foregrounds that one, not the dev binary.
3. `left_click` targets whatever the frontmost granted app shows, which is the
   installed release build.
4. The dev binary is functionally invisible to computer-use despite being
   fully runnable.

## Detection
Run these checks in parallel:

```bash
# Is the installed release app present?
ls -d /Applications/<AppName>.app

# Are there two processes? The dev one will be in target/debug/
ps aux | grep -iE '<app-name>' | grep -v grep

# What bundle IDs are currently granted to computer-use?
# (check list_granted_applications output)
```

If both the installed app and the dev binary are running, and screenshots
show the installed UI, you have hit this issue.

## Solution

### Preferred: verify behaviour without the UI
1. Unit / integration tests via `vitest` - verify component logic directly.
2. `tauri-driver` + WebDriver - drives the actual Tauri webview by process.
3. Ask the user to screenshot the dev window and paste the image into chat.

### If you must use computer-use against the dev build
1. Quit the installed release app entirely:
   ```bash
   osascript -e 'tell application "<AppName>" to quit'
   # or force if it has no graceful quit
   pkill -f '/Applications/<AppName>.app'
   ```
2. Restart `tauri dev` and let it open its own window.
3. Re-request access and confirm the granted bundle ID corresponds to the
   dev binary. If the dev binary has no bundle ID, package a debug `.app`
   bundle (`cargo tauri build --debug`) and run that instead.
4. Verify by clicking on the dev window's title bar and confirming
   `cursor_position` / `screenshot` show the expected frame.

### Fallback
Rename or move the installed app out of `/Applications/` for the duration of
the dev session so Launch Services cannot resolve it.

## Verification
After quitting the installed app and restarting `tauri dev`:

- `screenshot` shows the dev window with your latest code changes
- `open_application <AppName>` brings the dev window forward, not a stale one
- The app does NOT show `tauri://localhost/assets/...` URLs; dev builds load
  from the Vite dev server at `http://localhost:1420` (visible in DevTools)

## Notes
- This is separate from the general Tauri browser-automation limitation
  (see `tauri-v2-browser-automation-limitation` skill). That skill is about
  agent-browser vs the Tauri webview. This skill is about OS-level
  computer-use targeting the wrong native window.
- The problem is symmetrical: it also occurs if the dev binary was installed
  by a previous `tauri build` and a newer release is also installed.
- On macOS, Launch Services caches bundle-to-path mappings; after moving an
  app you may need to wait or run `lsregister -kill -r` for the change to
  take effect.
- The dev binary running without a bundle is a macOS peculiarity; on Linux
  and Windows the mismatch manifests differently (usually both windows are
  visible but clicks land on whichever is frontmost).
- Do not silently retry screenshots or clicks when you suspect this issue -
  diagnose the root cause first. Otherwise you waste time verifying against
  the wrong UI.

## References
- Tauri v2 docs on `cargo tauri dev` vs `cargo tauri build`:
  https://tauri.app/v2/reference/cli/
- macOS Launch Services and bundle resolution:
  https://developer.apple.com/documentation/coreservices/launch_services
- Related skill: `tauri-v2-browser-automation-limitation`
