---
name: tauri-window-state-compact-size-persist
description: |
  Tauri v2 apps using tauri-plugin-window-state silently restore the previous
  session's window SIZE and POSITION on every launch. Use when: (1) a Tauri
  app has a "compact mode" / "mini window" / always-on-top floating panel
  that calls webviewWindow.setSize() to shrink the main window, (2) the user
  reports the app starts as a tiny / "minimised" window on fresh launch after
  exiting from compact mode, (3) the next launch restores a default-size
  window at an off-screen top-left because compact mode centred a small
  window and the TL was saved, (4) you're wiring up
  tauri-plugin-window-state with .Builder::new().build() (the default),
  (5) you already constrained StateFlags to exclude SIZE/POSITION but the
  bug still happens. Root cause v1: StateFlags defaults to `all()` including
  SIZE + POSITION. Root cause v2 (subtle): even with StateFlags constrained,
  the plugin's SAVE path still writes width/height/x/y to the state file —
  the flags only filter on RESTORE. Once the file contains the compact
  dimensions, any later code path that reads them (or any future plugin
  version that respects fewer flags on restore) brings the bug back.
  Recommended fix: remove the plugin entirely and let tauri.conf.json
  defaults be the only source of truth.
author: Claude Code
version: 2.0.0
date: 2026-04-29
---

# Tauri v2: compact mode + window-state plugin persists tiny sizes across launches

## Problem

A Tauri v2 app that uses `tauri-plugin-window-state` AND has a mode that
programmatically shrinks the main window (e.g. a "compact / mini / always-
on-top floating panel" via `webviewWindow.setSize(new LogicalSize(340,
260))`) will silently persist those shrunken dimensions on close. On the
next launch, the user sees a tiny 340×260 "minimised-looking" window even
though the in-memory compact-mode atom/flag is false.

Worse: if the compact UI also centres the small window
(`webviewWindow.center()`), the saved top-left is roughly
`((screenW - 340) / 2, (screenH - 260) / 2)`. When a later fix restores a
default 1200×800 size at that TL, the window can extend off the edge of
the display.

## Context / Trigger Conditions

- Tauri 2 desktop app (macOS/Windows/Linux)
- `tauri-plugin-window-state = "2"` in `src-tauri/Cargo.toml`
- Plugin wired up with the default builder:
  `.plugin(tauri_plugin_window_state::Builder::new().build())`
- The app has any flow that calls `webviewWindow.setSize()` to shrink the
  main window (compact mode, mini-player, always-on-top floating view,
  picture-in-picture, etc.)
- User reports: "the app starts minimised / tiny" after using that flow
- `tauri.conf.json` window config has no explicit `width`/`height` (Tauri's
  fallback is 800×600) or has them but they're being overridden by the
  plugin restore

## Solution

### Recommended (v2): remove the plugin entirely

The earlier "trim state flags" fix below is **incomplete**:
`tauri-plugin-window-state` v2 ignores `StateFlags` on the SAVE path.
Even with `StateFlags` set to `MAXIMIZED | FULLSCREEN | VISIBLE |
DECORATIONS`, the on-disk JSON keeps containing `width`, `height`, `x`,
`y`, `prev_x`, `prev_y`. Inspect the file to verify:

```bash
cat ~/Library/Application\ Support/<bundle.id>/.window-state.json
# {"main":{"width":680,"height":520,"x":0,"y":66,"prev_x":712,
#  "prev_y":242,"maximized":true,"visible":true,...}}
```

The flag-filtered restore happens to look correct in the common path,
but if the user ever unmaximises, or the plugin's filtering changes
across versions, those stale dimensions surface.

**Cleanest fix**:

1. Drop `tauri-plugin-window-state = "2"` from `Cargo.toml`.
2. Drop `@tauri-apps/plugin-window-state` from `package.json`.
3. Remove `window-state:default` from `src-tauri/capabilities/main.json`.
4. Remove the plugin registration from `main.rs`.
5. **Add a one-shot startup cleanup** that deletes the legacy
   `.window-state.json` in `app_config_dir()` so existing users upgrading
   past this commit don't carry stale state forward. Without this, the
   file keeps sitting there and could be read by any future code path
   you forget about.

```rust
pub fn cleanup_legacy_window_state(app_config_dir: &Path) -> std::io::Result<bool> {
    let target = app_config_dir.join(".window-state.json");
    match std::fs::remove_file(&target) {
        Ok(()) => Ok(true),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(e),
    }
}

// In .setup(move |app| { ... }):
if let Ok(config_dir) = app.path().app_config_dir() {
    let _ = cleanup_legacy_window_state(&config_dir);
}
```

Trade-off: users lose the persisted maximised/fullscreen state across
sessions. In practice that's acceptable — most users want predictable
launches at a sensible default more than they want their last
maximisation respected.

### Legacy fix (v1, incomplete — kept here for context)

This was the original April 2026 fix. It works for the common case but
fails the "everything in the JSON gets written" property described
above. Use only if you really need to keep the plugin.

### 1. Trim the state flags

In `src-tauri/src/main.rs`, replace the default builder with one that
excludes `SIZE` and `POSITION`:

```rust
use tauri_plugin_window_state::StateFlags;

// ...

tauri::Builder::default()
    .plugin(
        tauri_plugin_window_state::Builder::new()
            .with_state_flags(
                StateFlags::MAXIMIZED
                    | StateFlags::FULLSCREEN
                    | StateFlags::VISIBLE
                    | StateFlags::DECORATIONS,
            )
            .build(),
    )
    // other plugins...
```

Why each flag kept:
- `MAXIMIZED` — a maximised window stays maximised on relaunch. A compact
  window is never maximised, so this doesn't re-trigger the bug.
- `FULLSCREEN` — harmless for most apps; preserves fullscreen intent.
- `VISIBLE` — the plugin tracks whether the window was visible vs
  minimised-to-dock; needed for expected launch behaviour.
- `DECORATIONS` — preserves titlebar/chrome state.

Why `SIZE` dropped — the main complaint. Every launch starts at the
`tauri.conf.json` default.

Why `POSITION` dropped — if compact mode centred the small window, the
saved TL will place the default-sized window off-screen on next launch.
Safer to always recentre.

### 2. Set an explicit default size in tauri.conf.json

```json
"app": {
  "windows": [
    {
      "title": "...",
      "visible": false,
      "decorations": true,
      "width": 1200,
      "height": 800,
      "center": true
    }
  ]
}
```

Without explicit dims, Tauri falls back to 800×600. With them, every
launch lands at your chosen default, centred.

## Verification

1. Launch the app fresh — window should be at the declared default size,
   centred.
2. Resize the window manually to something non-default (e.g. 1400×900),
   close, relaunch — window should be **back to the default** (confirms
   `SIZE` is no longer persisted). This is the intended trade-off.
3. Enter compact mode (`setSize(340, 260)` + `setAlwaysOnTop(true)`),
   close the app while still in compact, relaunch — window should be at
   the **default size** (1200×800), **not** 340×260. This is the bug fix.
4. Maximise the window, close, relaunch — should come back maximised
   (confirms `MAXIMIZED` still works).

## Example — symptom before fix

```
# User flow
1. Open the app — 800x600 (Tauri fallback)
2. Trigger compact mode — app calls setSize(340, 260); setAlwaysOnTop(true); center()
3. User closes the app while compact
4. Plugin saves WindowState { width: 340, height: 260, x: <centre>, y: <centre>, ... }
5. Relaunch — plugin restores 340x260 at saved centre
6. User sees a tiny window even though `compactLiveAnalysisModeAtom` is false
```

After fix:

```
3. User closes the app while compact
4. Plugin saves WindowState { maximized: false, fullscreen: false, visible: true, decorations: true } (no size, no position)
5. Relaunch — plugin restores ONLY those flags; SIZE falls through to tauri.conf.json default
6. Window is 1200x800 centred, regardless of prior session
```

## Notes

- This is a deliberate UX trade-off: users who manually resize the main
  window to their preferred dimensions lose that choice on next launch.
  In practice, users have one "preferred default" which you should bake
  into `tauri.conf.json`, and deviations from that are usually temporary.
- If you want to preserve user-chosen NORMAL sizes but reject compact
  sizes, the alternative is: keep `SIZE` in the flags AND add a Rust
  startup hook that probes `window.outer_size()` after the plugin
  restores and resets to default if below a threshold (e.g.
  `width < 700 || height < 500` physical px). More code, more edge
  cases around DPI scaling — only do this if dropping `SIZE` is too
  aggressive.
- On macOS, `visible: false` in `tauri.conf.json` is often paired with
  a Rust-side `.show()` call after setup; the `VISIBLE` flag covers
  the user having minimised-to-dock vs visible state across launches.
- The `center: true` field in `tauri.conf.json` only applies to the
  INITIAL creation; subsequent launches ignore it (the plugin restores
  instead). Because we dropped `POSITION`, launches with no saved
  position fall back to Tauri's default placement. If you see windows
  landing at (0,0), add a `.center()` call in the Rust setup hook.
- `tauri-plugin-window-state` v2.0.1 `StateFlags` enum:
  `SIZE | POSITION | MAXIMIZED | VISIBLE | DECORATIONS | FULLSCREEN`.
  `Default for StateFlags` returns `Self::all()`.

## References

- `tauri-plugin-window-state` v2.0.1 source: `StateFlags` bitflags enum
  and `Builder::with_state_flags` API
  (`~/.cargo/registry/src/.../tauri-plugin-window-state-2.0.1/src/lib.rs`)
- Tauri v2 window config schema:
  https://tauri.app/reference/config/#windowconfig
