---
name: tauri-v2-macos-missing-edit-menu
description: |
  Fix for Cmd+C / Cmd+V / Cmd+X / Cmd+A silently doing nothing in every text
  input across a Tauri 2 macOS app. Use when: (1) user reports "copy/paste
  isn't working anywhere in the app", (2) keyboard clipboard shortcuts have
  no effect - no error, no beep, just nothing, (3) the menu bar visibly shows
  only a partial set of submenus (e.g. App | File | View | Help with Edit
  missing), (4) right-click > Paste works but Cmd+V does not (rules out
  clipboard permission), (5) behaviour is identical in dev and installed
  release builds. Root cause is macOS binding clipboard shortcuts to
  @selector(copy:) etc. on NSMenu items - the app needs a menu with
  PredefinedMenuItem paste/copy/cut/selectAll entries.
  IMPORTANT: Tauri 2 auto-applies Menu::default; manually calling set_menu in
  Rust setup() is REDUNDANT and RACES with the auto-apply. But a more common
  and sneakier cause in frontend-heavy Tauri apps: a JS call to
  Menu.new(...).setAsAppMenu() (from @tauri-apps/api/menu) silently REPLACES
  Tauri's default menu with one that omits Edit. grep the frontend for
  setAsAppMenu before blaming Rust. Also covers a /tmp wrapper-bundle
  diagnostic pitfall where ad-hoc codesign corrupts the menu bar independent
  of code.
author: Claude Code
version: 2.1.0
date: 2026-04-15
---

# Tauri 2 macOS: Clipboard Shortcuts and the Default Menu

## Problem
Cmd+C / Cmd+V / Cmd+X / Cmd+A silently do nothing in every text input across
a Tauri 2 app on macOS. There is no error, no OS beep, no menu flash - the
shortcuts simply have no effect. Behaviour is identical in `tauri dev` and
the installed release. Users cannot copy text out of or paste text into any
input, textarea, or contenteditable in the app.

## Context / Trigger Conditions
- Tauri 2 (`tauri = "2"` in `src-tauri/Cargo.toml`)
- Target platform: macOS
- Symptom is universal: every `<input>`, `<textarea>`, Mantine `TextInput`,
  and contenteditable is affected
- Right-click context menu paste DOES work (rules out clipboard permission;
  confirms the issue is keyboard-shortcut routing, not clipboard access)
- Affects dev and installed builds equally
- Menu bar may visibly show ONLY a partial set of submenus: `<AppName> | View | Help`
  with Edit, File, and Window submenus missing

Not to be confused with:
- `tauri-v2-browser-automation-limitation` - different symptom (automation,
  not clipboard)
- `tauri-dev-computer-use-bundle-id` - only dev builds affected; here both
  dev and release are broken

## First-Principles Model — Why Menus Gate Clipboard on macOS

macOS does not route keyboard shortcuts like Cmd+C directly to the active
text field. Instead:

1. AppKit looks up the shortcut's key equivalent in the app's `NSMenu` (the
   main menu bar).
2. If matched, AppKit sends the corresponding selector
   (`@selector(copy:)`, `@selector(paste:)`, `@selector(cut:)`,
   `@selector(selectAll:)`) down the responder chain.
3. The focused text field or WKWebView's first responder handles that
   selector and performs the action.

**No menu item = no selector dispatch = silent no-op.**

Additional macOS constraint: **the root `NSMenu` can only contain submenus.**
Items added at the root level are silently dropped. This is why Tauri's
`Menu::default` wraps every item in a submenu (App/File/Edit/View/Window/Help).

## Root Cause + The Common Mistakes

Tauri 2 DOES provide a default menu automatically — but frontend or backend
code can silently replace it.

### Tauri 2's default behaviour

`Builder::enable_macos_default_menu(true)` is **on by default**. In
`Builder::build()`, Tauri checks:

```rust
#[cfg(target_os = "macos")]
if self.menu.is_none() && self.enable_macos_default_menu {
    self.menu = Some(Box::new(|app_handle| {
        crate::menu::Menu::default(app_handle)
    }));
}
```

So a fresh Tauri 2 macOS app already has `Menu::default` applied, which
includes the Edit submenu with Cut/Copy/Paste/Select All. Clipboard
shortcuts should work out of the box.

### Mistake #1 — Redundant `set_menu` in Rust setup()

Reading advice that says "add a default menu to fix clipboard", developers
add this to their `setup()`:

```rust
.setup(move |app| {
    #[cfg(target_os = "macos")]
    {
        let menu = tauri::menu::Menu::default(app.handle())?;
        app.set_menu(menu)?;   // ❌ redundant AND racy
    }
    Ok(())
})
```

Or worse, they hand-build submenus via `SubmenuBuilder` and call `set_menu`.

`AppHandle::set_menu` on macOS schedules init via `run_on_main_thread`, so
the set_menu call runs asynchronously. If the Tauri auto-apply and the
setup-scheduled set_menu run in an unexpected order, or if one overwrites
the other mid-init, you can end up with a partially-applied menu bar —
visually showing only App/View/Help with Edit/File/Window missing, AND
clipboard shortcuts broken.

### Mistake #2 — JS `setAsAppMenu()` without Edit (more common in practice)

Apps that want a custom menu bar (File > New Tab, Help > Check for updates,
etc.) frequently build it in the **frontend** using the JS API from
`@tauri-apps/api/menu`:

```ts
import { Menu, MenuItem, Submenu } from "@tauri-apps/api/menu";

const fileSubmenu = await Submenu.new({
  text: "File",
  items: [await MenuItem.new({ text: "New Tab", /* ... */ })],
});
const menu = await Menu.new({ items: [fileSubmenu /* no Edit! */] });
await menu.setAsAppMenu();  // ❌ silently replaces Menu::default
```

**`setAsAppMenu()` is a full replacement, not an addition.** As soon as it
runs, Tauri's default Edit submenu is gone, Cmd+V stops working, and
because the Rust `main.rs` looks perfectly clean, the bug is easy to miss.

Common symptoms of this case:
- Rust `setup()` has no menu code at all (grep shows nothing)
- Menu bar looks complete but lacks Edit (may be 4 submenus:
  `<AppName> | File | View | Help`)
- The visible submenus contain app-specific items (e.g. "Check for updates",
  "Clear saved data", "Open Logs") that aren't part of `Menu::default`

**Diagnostic grep — run this first** when you see the symptoms:

```bash
grep -rn "setAsAppMenu\|Menu\.new\|Submenu\.new\|MenuItem\.new" src/
```

If any frontend file calls `setAsAppMenu()`, that is where the menu is
being replaced — fix it there, not in Rust.

On macOS, enumerate the actual live menu bar to confirm:

```bash
osascript -e 'tell application "System Events" to tell process "<AppName>" to get name of menu bar items of menu bar 1'
```

If "Edit" is missing from the output, the frontend is overriding the menu.

## Solution

### Decision tree

1. Does any frontend file call `setAsAppMenu()` (grep for it)?
   → **Yes**: fix the frontend (Mistake #2 below). The Rust side is fine.
   → **No**: continue.
2. Does `main.rs` have `app.set_menu(...)` in `setup()`?
   → **Yes**: delete it (Mistake #1 below). Tauri's auto-apply is sufficient.
   → **No**: investigate plugins or a `/tmp` wrapper-bundle (see Diagnostic
     Pitfall below).

### Fix for Mistake #1 (Rust set_menu in setup): do nothing

For most Tauri 2 apps on macOS, the correct code is **no menu code at all**.
Tauri auto-applies `Menu::default`. If your `setup()` has this pattern:

```rust
.setup(move |app| {
    #[cfg(target_os = "macos")]
    {
        let menu = tauri::menu::Menu::default(app.handle())?;
        app.set_menu(menu)?;
    }
    // ... rest
})
```

**Delete it.** Rebuild. Clipboard shortcuts should work.

### Fix for Mistake #2 (JS setAsAppMenu missing Edit): add an Edit submenu

If the frontend builds its own menu with `setAsAppMenu()`, the fix is to
include an Edit submenu with **predefined** Cut/Copy/Paste/Select All
items — the JS API exposes these via `PredefinedMenuItem`:

```ts
import { Menu, Submenu, PredefinedMenuItem } from "@tauri-apps/api/menu";

const editSubmenu = await Submenu.new({
  text: "Edit",
  items: await Promise.all([
    PredefinedMenuItem.new({ item: "Undo" }),
    PredefinedMenuItem.new({ item: "Redo" }),
    PredefinedMenuItem.new({ item: "Separator" }),
    PredefinedMenuItem.new({ item: "Cut" }),
    PredefinedMenuItem.new({ item: "Copy" }),
    PredefinedMenuItem.new({ item: "Paste" }),
    PredefinedMenuItem.new({ item: "Separator" }),
    PredefinedMenuItem.new({ item: "SelectAll" }),
  ]),
});

const menu = await Menu.new({
  items: [fileSubmenu, editSubmenu, viewSubmenu, helpSubmenu],
});
await menu.setAsAppMenu();
```

`PredefinedMenuItemOptions.item` valid values (Tauri 2 JS API):
`'Separator' | 'Copy' | 'Cut' | 'Paste' | 'SelectAll' | 'Undo' | 'Redo' |
'Minimize' | 'Maximize' | 'Fullscreen' | 'Hide' | 'HideOthers' | 'ShowAll' |
'CloseWindow' | 'Quit' | 'Services'`.

Critical rules:
- Use `PredefinedMenuItem.new({ item: "Paste" })`, NOT
  `MenuItem.new({ text: "Paste", accelerator: "CmdOrCtrl+V" })`. A custom
  MenuItem with a manual accelerator does **not** map to AppKit's
  `@selector(paste:)` — it fires your `action` callback instead, and the
  text field's native paste path is never invoked.
- On macOS, predefined items use system-provided localized labels
  automatically ("Coller" in French, "貼り付け" in Japanese, etc.) — don't
  add your own translation strings for the predefined item labels.
- The Edit submenu itself (its title) does need translation via your app's
  i18n system, since that's a string you control.

### If you genuinely need a custom menu

Register it via `Builder::menu()` (consumed before `setup()`), NOT via
`app.set_menu()` in setup():

```rust
tauri::Builder::default()
    .menu(|app_handle| {
        use tauri::menu::{MenuBuilder, SubmenuBuilder};
        let edit = SubmenuBuilder::new(app_handle, "Edit")
            .undo().redo().separator()
            .cut().copy().paste().select_all()
            .build()?;
        // ... other submenus; Window/Help should use
        // Submenu::with_id_and_items(app, WINDOW_SUBMENU_ID, ...) /
        // HELP_SUBMENU_ID to get macOS role tagging
        MenuBuilder::new(app_handle).item(&edit).build()
    })
    .setup(move |app| { Ok(()) })
```

Critical rules when building a custom menu:
- Every item at the root level must be a `Submenu` — raw menu items are
  silently dropped on macOS.
- Use `PredefinedMenuItem::paste(...)` / `.copy()` etc. (or `SubmenuBuilder::paste()`),
  not custom `MenuItem::new(...)` with the label "Paste". Only predefined
  items are wired to `@selector(paste:)`.
- Window submenu should use `Submenu::with_id_and_items(app, WINDOW_SUBMENU_ID, ...)`;
  Help submenu should use `HELP_SUBMENU_ID`. Tauri's init code looks up
  these magic IDs to tag the submenus with macOS system roles.

### If you want to disable the default menu entirely

```rust
tauri::Builder::default()
    .enable_macos_default_menu(false)
```

But understand you've just broken all clipboard shortcuts unless you
register a replacement menu via `.menu(...)`.

## Diagnostic Pitfall: /tmp Wrapper Bundles Fake the Symptom

When debugging Tauri dev binaries with computer-use (see
`tauri-dev-computer-use-bundle-id`), a common workaround is:

1. Copy `/Applications/<AppName>.app` to `/tmp/<name>.app`
2. Replace `Contents/MacOS/<binary>` with a fresh debug build
3. `codesign --force --deep --sign -` to ad-hoc sign
4. Launch the wrapper

This wrapper can exhibit a **partial menu bar with the exact symptom**
this skill addresses (Edit/File/Window missing, clipboard shortcuts broken)
EVEN WHEN THE RUST CODE IS CORRECT. Possible causes: ad-hoc signature
fails menu-related entitlements; Launch Services metadata mismatch; or
the inherited Info.plist doesn't match the new binary.

**Rule:** before concluding the Rust menu code is broken, verify with a
real `tauri build --debug` bundle or a signed release build. If a real
bundle works but the `/tmp` wrapper doesn't, the wrapper is the culprit,
not the code.

## Verification
After applying the fix and restarting:

1. `cargo check` in `src-tauri/` passes.
2. Rebuild and relaunch via `npm run dev` / `pnpm tauri dev` / a fresh
   `tauri build --debug` (HMR does NOT apply Rust changes).
3. In any text input (Mantine `TextInput`, plain `<input>`, `<textarea>`):
   - Select text + Cmd+C, paste elsewhere → works.
   - Cmd+V into the input → works.
   - Cmd+X → cuts text.
   - Cmd+A → selects all text in the focused field.
4. Check the macOS menu bar — you should see the full default menu:
   `<AppName> | File | Edit | View | Window | Help`. If any of these are
   missing, either a custom menu is silently dropping items, or you're
   testing against a wrapper bundle that corrupts the menu.
5. Right-click in a text input → context menu Paste should continue to
   work both before and after the fix (it's independent of the main menu).

## Example

### Before (broken)

```rust
.setup(move |app| {
    #[cfg(target_os = "macos")]
    {
        let menu = tauri::menu::Menu::default(app.handle())?;
        app.set_menu(menu)?;
    }
    // ... setup
    Ok(())
})
```

### After (working)

```rust
.setup(move |app| {
    // No menu code — Tauri auto-applies Menu::default when
    // enable_macos_default_menu is true (the default) and no custom
    // menu was registered via Builder::menu().
    // ... setup
    Ok(())
})
```

Commit pattern: `fix: (main) remove redundant set_menu call racing with Tauri default menu`

## Notes

- The skill previously (v1.0.0) recommended calling
  `app.set_menu(Menu::default(...))` in setup(). That advice was wrong —
  it's redundant with Tauri's auto-apply and can race with it, producing
  the exact symptom the advice was meant to fix. v2.0.0 corrected this.
  v2.1.0 adds the JS `setAsAppMenu()` case (Mistake #2), which is often
  the actual cause in frontend-heavy apps where `main.rs` looks clean.
- If you `grep` for `set_menu` or `Menu::default` in the Rust codebase and
  find one call in `setup()`, that is likely the bug — delete it.
- If the Rust side is clean, grep the frontend for
  `setAsAppMenu\|Menu\.new\|Submenu\.new`. Replacement via `setAsAppMenu()`
  is silent and easy to miss.
- `enable_macos_default_menu(false)` + a custom `Builder::menu(...)` is
  the right pattern for real customisation in Rust. Never mix
  `Builder::menu(...)` with an `app.set_menu(...)` in setup() — the latter
  will race.
- On Windows and Linux, the webview handles clipboard directly via
  keyboard events; the menu code path is macOS-specific. The default
  `Menu::default` does include a Windows/Linux menu bar which may not
  match app design — disable via `enable_macos_default_menu(false)` (the
  flag covers Windows too despite the name) if you don't want a menu on
  those platforms AND you don't need clipboard menu routing (which you
  don't, on non-macOS).
- If paste works but Cmd+A (Select All) doesn't in a focused `<input>`,
  check for an app-level hotkey (e.g. `react-hotkeys-hook`'s
  `useHotkeys('ctrl+a', ...)`) that is preventing default. On macOS that
  hook maps `ctrl+a` to literal Control+A, not Cmd+A, so usually unrelated.
- Tauri version history: `wry` PR #1208 (May 2024, wry 0.24.8+) fixed a
  multiwebview-specific cmd+V forwarding bug on macOS. If on wry <0.24.8
  upgrading may be sufficient. Modern Tauri 2 (wry 0.40+) has this fix.

## References

- [Tauri issue #2397 — Copy/Paste and Other Keyboard Shortcuts Do Not Work on MacOS](https://github.com/tauri-apps/tauri/issues/2397)
  (canonical long-standing thread; fix is "add a menu")
- [Tauri issue #8676 — command shortcuts on macos webview](https://github.com/tauri-apps/tauri/issues/8676)
  (multiwebview; fixed in wry PR #1208, wry 0.24.8+)
- [Tauri issue #11422 — Setting the app menu in Tauri v2 on Mac OS](https://github.com/tauri-apps/tauri/issues/11422)
  ("root menu bar can only contain submenus"; raw items at root are dropped)
- [Tauri issue #12458 — command+v/c/x shortcuts do not work in input components](https://github.com/tauri-apps/tauri/issues/12458)
  ("shortcuts depend on menu items so if you disable or overwrite the
  default menu without adding the required items you'll break the shortcuts")
- [Tauri v2 Window Menu docs](https://v2.tauri.app/learn/window-menu/)
- [Tauri `Menu::default` source](https://docs.rs/tauri/latest/tauri/menu/struct.Menu.html#method.default)
- [AppKit responder chain for keyboard shortcuts](https://developer.apple.com/documentation/appkit/nsresponder)
- Related skills:
  - `tauri-v2-plugin-pitfalls` - broader Tauri 2 plugin gotchas
  - `tauri-dev-computer-use-bundle-id` - when only the dev build misbehaves
    under computer-use (related to the wrapper-bundle pitfall above)
  - `tauri-v2-browser-automation-limitation` - unrelated automation issue
