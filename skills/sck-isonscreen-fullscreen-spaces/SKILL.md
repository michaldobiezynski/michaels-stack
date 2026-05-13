---
name: sck-isonscreen-fullscreen-spaces
description: |
  Guide to SCWindow.isOnScreen semantics when migrating macOS window capture
  from xcap to ScreenCaptureKit (SCK). Covers two related pitfalls: (a) the
  naive reading that isOnScreen == !isMinimised is wrong because inactive-Space
  windows also read false; (b) on macOS 26 Tahoe, SCShareableContent enumerates
  those inactive-Space windows but SCScreenshotManager.capture_image cannot
  actually capture them, so hiding them via !isOnScreen is in fact the right
  call on 26. Use when: (1) you're deciding how to filter out minimised windows
  under SCK, (2) you're confused why fullscreen windows in other Spaces still
  don't work after exposing them, (3) capture_image fails with "Failed to start
  stream due to audio/video capture failure" for an enumerated window.
author: Claude Code
version: 2.0.0
date: 2026-04-21
---

# SCWindow.isOnScreen is false for inactive-Space windows, not just minimised ones

## Problem

The whole reason to switch from xcap to ScreenCaptureKit on macOS is that xcap's
`Window::all()` uses CoreGraphics' `OnScreenOnly` flag, which hides windows that
live on their own Space, most notably native-fullscreen app windows. SCK's
`SCShareableContent::get()` enumerates across Spaces and DOES return those
windows.

Two pitfalls stack on top of each other:

**Pitfall 1 (the semantic gotcha).** SCK doesn't expose an `isMinimised`
property, so it's tempting to use `SCWindow.isOnScreen` as a proxy. That proxy
is wrong in the literal sense: `isOnScreen` is false for BOTH
- minimised-to-dock windows, AND
- windows on a Space that is not currently active (including every
  native-fullscreen window when you're looking at a different Space)

So if your intent is "expose fullscreen-in-another-Space windows to the user",
filtering `!isOnScreen` re-introduces exactly the bug the SCK migration was
supposed to fix.

**Pitfall 2 (the macOS 26 platform limitation).** Surfacing those inactive-Space
windows is only useful if you can actually capture them. On macOS 26 (Tahoe),
`SCShareableContent::get()` enumerates them fine, but
`SCScreenshotManager::capture_image(&filter, &config)` fails with
`"Failed to start stream due to audio/video capture failure"` for any window
whose Space isn't active, even with a correct `SCContentFilter`, correct pixel
dimensions (via `SCShareableContentInfo::for_filter().pixel_size()`), and
fully-granted Screen Recording permission. A window that captures successfully
on its own Space fails the moment the user switches away. There is no known
config incantation that fixes this on macOS 26.

Net effect: on macOS 26, hiding inactive-Space windows IS correct, because
offering to capture them is offering a capture that will always error. The
`!isOnScreen` filter is not just a legacy xcap habit any more, it matches the
capturability constraint that the capture API imposes.

## Context / Trigger Conditions

- macOS 14+ build using `screencapturekit` crate (or Swift/Obj-C SCK directly)
- Code path: `SCShareableContent::get()` → iterate `.windows()` → filter by
  `w.is_on_screen()` in some way
- Symptom: native-fullscreen windows (Chrome/Safari/Chess apps in fullscreen Space)
  enumerate but are filtered out before reaching the UI
- You can confirm the windows ARE returned by logging every `SCWindow` before any
  filter — they'll be present with the correct title/frame, and `is_on_screen()`
  will be `false`

## Solution

Which filter is correct depends on which pitfall you're hitting.

### If you are on macOS 26 (Tahoe) or newer

Use `is_on_screen()` AS the non-capturable signal. It matches platform reality:
`capture_image` can't service those windows anyway. Layer frame-size and
anonymity filters on top to kill system chrome.

```rust
let is_minimised = !w.is_on_screen(); // on 26, this also excludes inactive-Space
if width < MIN_WINDOW_EDGE || height < MIN_WINDOW_EDGE { continue; }
if title.is_empty() && app_name.is_empty() { continue; }
```

Surface a UX note somewhere in the picker so users who expected to see their
fullscreen window know what to do: switch to that Space first, then reopen the
picker.

### If you are on macOS 14/15 and capture_image works for inactive-Space windows

(Historical path; included for completeness if you verify capture works on
your target OS. On 14/15 the platform behaviour is reported to match the
enumeration, but verify on your own setup.) Do NOT use `is_on_screen()` as a
proxy:

1. **Frame-size filter**: genuinely minimised windows collapse to zero/negative
   or very small dimensions. `MIN_WINDOW_EDGE = 200` rejects them while
   keeping real app windows.
2. **Anonymity filter**: reject windows with empty title AND empty app name;
   they're almost always system UI chrome.
3. **(Optional, macOS 13.1+)**: `SCWindow.is_active()` if you genuinely need
   to distinguish Stage-Manager-style "active but off-screen" from
   truly-hidden.

```rust
let is_minimised = false; // SCK can't tell; rely on size/anonymity below
if width < MIN_WINDOW_EDGE || height < MIN_WINDOW_EDGE { continue; }
if title.is_empty() && app_name.is_empty() { continue; }
```

## Verification

**macOS 26 path (capture-limited):**
1. Put the target app in native fullscreen on a Space that is NOT active.
2. Run enumeration: the fullscreen window should be absent from the picker.
3. Switch to that Space. Reopen the picker. Window appears; capture succeeds.
4. If you instead try to capture a not-on-screen window directly via
   `SCScreenshotManager::capture_image`, you should see
   `"Failed to start stream due to audio/video capture failure"` - this is the
   symptom that justifies the filter.

**macOS 14/15 path (if capture truly works):**
1. Put the target app in native fullscreen on a Space that is NOT active.
2. Run enumeration; the window appears.
3. Capture via `SCScreenshotManager::capture_image` with
   `SCContentFilter::create().with_window(&w).build()`; image returns.

## Example

See `src-tauri/src/image_detection/capture_sck.rs` in pawn-au-chocolat. It uses
the macOS 26 path (`is_minimised = !w.is_on_screen()`), with a module-level doc
explaining why inactive-Space windows are excluded despite the original
xcap->SCK migration motivation. The picker surfaces a note to the user telling
them to switch Spaces if they want to capture a fullscreen window.

## Notes

- Apple's own API docs describe `isOnScreen` as "a Boolean value that indicates
  whether the window is on screen", true to the letter, but the informal
  reading "is the window not minimised?" is wrong. Windows on inactive Spaces
  are not on the current screen even though they're not minimised.
- This bites hardest during xcap->SCK migrations because xcap's equivalent
  filter WAS a minimised check (via different CoreGraphics APIs), so the
  mental model transfers directly, and is wrong.
- **macOS 26 (Tahoe) turns the semantic bug into a matching platform
  constraint**: even though `SCShareableContent::get()` enumerates
  inactive-Space windows, `SCScreenshotManager::capture_image` cannot service
  them. Config tweaks (`with_captures_audio(false)`, `with_shows_cursor(false)`,
  `with_queue_depth(N)`), TCC resets, and ad-hoc sign identity shuffles do not
  change this. Accept it and filter them out.
- Signal the two failure modes look identical from logs: both produce
  `SCError::CaptureFailed("Failed to start stream due to audio/video capture
  failure")`. Distinguish by checking `w.is_on_screen()` at enumeration
  time, not at capture time.
- If you genuinely need to hide minimised windows from a picker AND capture
  inactive-Space ones on an older OS, the most reliable non-`is_on_screen`
  signal is the frame collapsing to tiny dimensions. There is no single
  boolean property that corresponds to AppKit's `NSWindow.isMiniaturized`.
- `SCWindow.is_active()` (macOS 13.1+) was added specifically because
  `is_on_screen` proved insufficient for Stage Manager; it's related but
  solves a different problem, and does NOT unblock inactive-Space capture on
  macOS 26.

## References

- [SCWindow.isOnScreen (Apple)](https://developer.apple.com/documentation/screencapturekit/scwindow/3916829-isonscreen)
- [SCWindow.isActive (macOS 13.1+)](https://developer.apple.com/documentation/screencapturekit/scwindow/4168996-isactive)
- screencapturekit crate 1.5.4, `src/shareable_content/window.rs`
