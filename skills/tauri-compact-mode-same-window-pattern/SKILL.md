---
name: tauri-compact-mode-same-window-pattern
description: |
  Implementing a "picture-in-picture" / floating mini-overlay / compact mode in a
  Tauri 2 app WITHOUT spawning a separate webview. Use when: (1) you want an
  always-on-top floating panel that shows a subset of the main app's state,
  (2) you'd otherwise reach for `WebviewWindow.new()` to create a second window,
  (3) you need state (FEN, engine session, theme, atoms) to seamlessly continue
  between full and compact views. Pattern: resize the existing main window to a
  small footprint, setAlwaysOnTop(true), and have the root layout switch to a
  chromeless render based on a single boolean atom. State persists trivially
  because it's the same React tree.
author: Claude Code
version: 1.0.0
date: 2026-04-29
---

# Tauri compact mode via same-window resize (not a second webview)

## Problem

You want a floating mini-window (picture-in-picture, compact analysis overlay,
sticky controller) that:

- Shows above all other apps
- Is much smaller than the main window
- Carries running engine / network / atom state from the main view
- Goes back to the full window cleanly

The natural reach is `WebviewWindow.new(label, options)` to spawn a second
window. Then you discover: state doesn't carry over (it's a separate React
tree, separate atoms, separate engine connections), IPC sessions get a new
window context, and you need to manually plumb every piece of state through
events. It's a lot of code and a lot of bugs.

## Context / Trigger Conditions

- Tauri 2 app (also works on v1 with the same primitives).
- React + a global state library (Jotai, Zustand, Redux, Recoil) - state needs
  to live above the views.
- A router (TanStack Router, React Router) that lets you have a "compact route".
- The mini view is a STRICT SUBSET of the main app, not an independent surface.

Don't use this pattern if:

- The mini view needs to outlive the main window's lifecycle (e.g. you close
  the main app but want the float to stay).
- The mini view is a different app concern entirely (settings, log viewer).
- You need the mini and main windows visible *simultaneously* (then yes, you
  do need two webviews).

## Solution

Implement compact mode as **one boolean atom** that flips three things:

```ts
// 1. Window size + always-on-top (Tauri side)
const win = getCurrentWebviewWindow();
await win.setSize(new LogicalSize(COMPACT_W, COMPACT_H));
await win.setAlwaysOnTop(true);
await win.center().catch(() => {});

// 2. The atom that the root layout reads
setCompactModeAtom(true);

// 3. Navigate to the compact route (no-op if already there)
navigate({ to: "/compact" });
```

In the **root route's layout component**, branch on the atom:

```tsx
// __root.tsx
const compact = useAtomValue(compactModeAtom);
if (compact) {
  // Bare Outlet - no AppShell, no sidebar, no tabs.
  return <Outlet />;
}
return (
  <AppShell>
    <Outlet />
  </AppShell>
);
```

The compact route renders a self-contained chromeless view with its own header,
controls, and body. Because it's the **same webview**, all atoms, IPC sessions,
event listeners, engine processes, and React component caches survive. State
handoff is automatic.

To exit:

```ts
await win.setAlwaysOnTop(false);
await win.setSize(new LogicalSize(DEFAULT_W, DEFAULT_H));
await win.center().catch(() => {});
setCompactModeAtom(false);
navigate({ to: "/" });
```

## Verification

1. Enter compact: window shrinks, floats above other apps, chromeless layout
   shows.
2. Exit: window restores, AppShell returns.
3. While in compact: any timers, engine sessions, network requests started in
   the main view continue uninterrupted.
4. `app.get_webview_window("main")` from Rust still resolves - there's only one
   window.
5. `WebviewWindow.getAll()` from JS returns one entry.

## Example

Pawn au Chocolat live-analysis miniboard:

- Webview label: `"main"` (the only one).
- Atom: `compactLiveAnalysisModeAtom` (in-memory, not `atomWithStorage` -
  re-entry on app launch is a no-op).
- Compact size: 340×620 (expanded) or 340×260 (collapsed) via a second
  toggle that resizes within compact mode.
- Default size on exit: 1200×800.
- Carrying state: FEN, orientation, crop region, detection confidence, and
  the running Stockfish session ID all live in atoms set by `enterCompactMode`.
  The compact route reads them on mount and the engine-start `useEffect` keeps
  pumping `BestMovesPayload` events into the same atom store.

Hook for the launch dance:

```ts
// useEnterCompactMode.ts
export function useEnterCompactMode() {
  const setCompactMode = useSetAtom(compactModeAtom);
  // ... other set atoms
  const navigate = useNavigate();
  return useCallback(async ({fen, orientation, ...}) => {
    const win = getCurrentWebviewWindow();
    await win.setSize(new LogicalSize(340, 620));
    await win.setAlwaysOnTop(true);
    setCompactFen(fen);
    setCompactOrientation(orientation);
    setCompactMode(true);
    void navigate({ to: "/live" });
    return { ok: true };
  }, [...]);
}
```

## Notes

- **Focus-existing-window logic is unnecessary.** Since there's no second
  window, there's nothing to deduplicate. Multiple "Open compact" buttons
  in different parts of the UI all flip the same atom.
- **Keep the compact-mode atom in-memory, not `atomWithStorage`.** Otherwise,
  the user gets the floating mini on next launch with no obvious way to exit
  (the Tauri "Always on Top" flag is sticky on the OS side too on macOS, so
  this pile-on is jarring).
- **Drag region:** add `data-tauri-drag-region` to the compact header so users
  can drag the floating window. Required because window decorations are off
  in chromeless layout.
- **macOS `tauri-plugin-window-state-2` interaction:** if the plugin is
  enabled, it persists the compact 340×620 size and re-applies it on next
  launch. Either don't use the plugin, or skip persistence while
  `compactMode` is true. The pawn-au-chocolat repo solved this by removing
  the plugin entirely (see `window_defaults.rs`).
- **Engine sessions:** because the React tree survives, your engine
  `useEffect` cleanup behaves correctly. No need to `stopEngine` on entry to
  compact mode and re-start - the existing session keeps emitting payloads.
- **Mint a fresh `tabId` on each entry** so the engine DashMap key
  `(tab_id, engine_path)` doesn't collide with a previous compact session
  that didn't get cleaned up.

## References

- Tauri Window API: https://tauri.app/v1/api/js/window/
- Tauri 2 setAlwaysOnTop: https://docs.rs/tauri/latest/tauri/webview/struct.WebviewWindow.html
