---
name: macos-finder-services-quick-action
description: |
  Programmatically create macOS Finder right-click / Services / Quick Actions (.workflow
  bundles) from the command line, without opening Automator. Use when: (1) user asks to
  add a Finder right-click entry like "Open in iTerm2", "Open in Warp", "Open in Ghostty",
  "Open in VS Code", or any custom shortcut on folders/files, (2) user wants to replace
  the built-in "New Terminal at Folder" service with a different terminal app,
  (3) building setup scripts that install Services/Quick Actions as part of a dotfiles
  or provisioning flow, (4) you need a folder-targeted right-click action that runs
  AppleScript or a shell script with the selected path. Covers the undocumented .wflow
  plist schema, Info.plist NSServices keys, Services registry refresh via `pbs -flush`
  and `pbs -update`, and registration verification. Applies to macOS 10.10 through
  macOS 26 Tahoe.
author: Claude Code
version: 1.0.0
date: 2026-04-23
---

# macOS Finder Services / Quick Action — Programmatic Creation

## Problem

macOS "Services" (a.k.a. Quick Actions) show up under Finder's right-click menu and let you run a script against the selected file/folder. The documented way to create one is via Automator.app's GUI — which an agent or setup script can't drive. The `.workflow` bundle format is **not officially documented**, so it's easy to produce a bundle that macOS silently ignores.

Classic symptoms of a broken bundle:
- The service never appears in Finder's right-click menu
- It doesn't show up in System Settings → Keyboard → Keyboard Shortcuts → Services
- `pbs -dump_pboard` doesn't list it
- Automator.app can't open the bundle, or opens it as a blank workflow

## Context / Trigger Conditions

Use this skill when:
- The user asks for a custom Finder right-click action (e.g. "open this folder in iTerm2/Warp/Ghostty/VS Code/Sublime")
- The user wants to replace "New Terminal at Folder" (which is hardcoded to Terminal.app) with a different terminal
- You're writing dotfiles / setup automation that installs Services
- You need any folder- or file-scoped right-click entry driven by AppleScript or shell

## Solution

### 1. Bundle layout

A Quick Action is a directory ending in `.workflow` under `~/Library/Services/`:

```
~/Library/Services/<Menu Name>.workflow/
└── Contents/
    ├── Info.plist      # Declares the Service (menu name, target app, accepted types)
    └── document.wflow  # The Automator workflow (the actual action to run)
```

**The directory name is the display name that appears in the menu.** Spaces are fine.

### 2. Info.plist — the Service declaration

Tells macOS "this bundle is a Service, here's what it accepts, here's the menu label":

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>NSServices</key>
    <array>
        <dict>
            <key>NSMenuItem</key>
            <dict>
                <key>default</key>
                <string>Open in iTerm2</string>   <!-- Menu label -->
            </dict>
            <key>NSMessage</key>
            <string>runWorkflowAsService</string>  <!-- Must be this literal -->
            <key>NSRequiredContext</key>
            <dict>
                <key>NSApplicationIdentifier</key>
                <string>com.apple.finder</string>  <!-- Only appear in Finder -->
            </dict>
            <key>NSSendFileTypes</key>
            <array>
                <string>public.folder</string>     <!-- Folder-only -->
                <!-- For files too, add: <string>public.item</string> -->
            </array>
        </dict>
    </array>
</dict>
</plist>
```

Key facts:
- `NSMessage` must be the literal string `runWorkflowAsService`
- `NSRequiredContext.NSApplicationIdentifier = com.apple.finder` scopes it to Finder only. Omit to make it global.
- `NSSendFileTypes` uses UTIs:
  - `public.folder` — folders only
  - `public.item` — any file or folder
  - `public.plain-text` — text files only
  - `public.image` — images only
- For "no selection required" (e.g. runs on the current Finder window), use `NSSendTypes` instead of `NSSendFileTypes`, and in `document.wflow` set `serviceProcessesInput` to 1 or omit input handling.

### 3. document.wflow — the workflow

This is the Automator plist. Minimal shape for a "Run AppleScript" action targeted at a folder Service:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>AMApplicationBuild</key><string>512</string>
    <key>AMApplicationVersion</key><string>2.10</string>
    <key>AMDocumentVersion</key><string>2</string>
    <key>actions</key>
    <array>
        <dict>
            <key>action</key>
            <dict>
                <key>AMAccepts</key>
                <dict>
                    <key>Container</key><string>List</string>
                    <key>Optional</key><true/>
                    <key>Types</key><array><string>*</string></array>
                </dict>
                <key>AMActionVersion</key><string>2.0.3</string>
                <key>AMApplication</key><array><string>Automator</string></array>
                <key>AMParameterProperties</key><dict><key>source</key><dict/></dict>
                <key>AMProvides</key>
                <dict>
                    <key>Container</key><string>List</string>
                    <key>Types</key><array><string>*</string></array>
                </dict>
                <key>ActionBundlePath</key>
                <string>/System/Library/Automator/Run AppleScript.action</string>
                <key>ActionName</key><string>Run AppleScript</string>
                <key>ActionParameters</key>
                <dict>
                    <key>source</key>
                    <string>on run {input, parameters}
    if (count of input) is 0 then return input
    set folderPath to POSIX path of (item 1 of input as alias)
    tell application "iTerm"
        activate
        set newWindow to (create window with default profile)
        tell current session of newWindow
            write text "cd " &amp; quoted form of folderPath
        end tell
    end tell
    return input
end run</string>
                </dict>
                <key>BundleIdentifier</key><string>com.apple.RunScriptAction</string>
                <key>CFBundleVersion</key><string>2.0.3</string>
                <key>CanShowSelectedItemsWhenRun</key><false/>
                <key>CanShowWhenRun</key><true/>
                <key>Category</key><array><string>AMCategoryUtilities</string></array>
                <key>Class Name</key><string>RunScriptAction</string>
                <key>InputUUID</key><string>2D0AA6E9-94D2-4F6B-9A6A-1C1A8B2E9A01</string>
                <key>OutputUUID</key><string>6C3E5B7A-3A0B-4C7E-9D2D-5C8B4F1A2B02</string>
                <key>UUID</key><string>F9C9DA1E-8B5E-4A86-9C1E-4A1D1E9B8F03</string>
                <key>UnlocalizedApplications</key><array><string>Automator</string></array>
                <key>arguments</key><dict/>
                <key>isViewVisible</key><true/>
                <key>location</key><string>309.500000:316.000000</string>
                <key>nibPath</key>
                <string>/System/Library/Automator/Run AppleScript.action/Contents/Resources/Base.lproj/main.nib</string>
            </dict>
            <key>isViewVisible</key><true/>
        </dict>
    </array>
    <key>connectors</key><dict/>
    <key>workflowMetaData</key>
    <dict>
        <key>serviceInputTypeIdentifier</key>
        <string>com.apple.Automator.fileSystemObject.folder</string>
        <key>serviceOutputTypeIdentifier</key>
        <string>com.apple.Automator.nothing</string>
        <key>serviceProcessesInput</key><integer>0</integer>
        <key>workflowTypeIdentifier</key>
        <string>com.apple.Automator.servicesMenu</string>
    </dict>
</dict>
</plist>
```

**Critical keys that often get omitted and cause silent failure:**
- `workflowMetaData.workflowTypeIdentifier = com.apple.Automator.servicesMenu` — marks it as a Service (not an Application or stand-alone workflow)
- `workflowMetaData.serviceInputTypeIdentifier` — must match `NSSendFileTypes`:
  - `com.apple.Automator.fileSystemObject.folder` for folders
  - `com.apple.Automator.fileSystemObject` for any file/folder
  - `com.apple.Automator.text` for text
  - `com.apple.Automator.nothing` for no input
- `ActionBundlePath` + `BundleIdentifier` + `Class Name` must all point at the same action. For "Run AppleScript" use `/System/Library/Automator/Run AppleScript.action` + `com.apple.RunScriptAction` + `RunScriptAction`. For "Run Shell Script" use `/System/Library/Automator/Run Shell Script.action` + `com.apple.RunShellScriptAction` + `RunShellScriptAction`.
- The three UUIDs can be any valid UUIDs — they just need to exist. Generate with `uuidgen` if you want fresh ones.

### 4. Run Shell Script variant

If you'd rather use a shell script than AppleScript, swap `ActionParameters` and the bundle identifier:

```xml
<key>ActionBundlePath</key>
<string>/System/Library/Automator/Run Shell Script.action</string>
<key>ActionName</key><string>Run Shell Script</string>
<key>ActionParameters</key>
<dict>
    <key>COMMAND_STRING</key>
    <string>for f in "$@"; do open -a "iTerm" "$f"; done</string>
    <key>CheckedForUserDefaultShell</key><true/>
    <key>inputMethod</key><integer>1</integer>  <!-- 0=stdin, 1=args -->
    <key>shell</key><string>/bin/bash</string>
    <key>source</key><string/>
</dict>
<key>BundleIdentifier</key><string>com.apple.RunShellScriptAction</string>
<key>Class Name</key><string>RunShellScriptAction</string>
```

With `inputMethod=1`, selected paths come through as `$1`, `$2`, … With `inputMethod=0` they arrive on stdin, one per line.

### 5. AppleScript-in-XML escaping

When the AppleScript lives inside the wflow plist, XML rules apply:
- `&` → `&amp;`
- `<` → `&lt;`
- `>` → `&gt;`

Easy miss: `"cd " & quoted form of p` must be written as `"cd " &amp; quoted form of p` in the plist.

### 6. Register the Service

After writing the files, refresh the Services registry:

```bash
/System/Library/CoreServices/pbs -flush
/System/Library/CoreServices/pbs -update
```

No logout needed. On Tahoe (26.x) these commands still work — macOS hasn't reworked `pbs`.

## Verification

1. **Lint both plists** before trusting them:
   ```bash
   plutil -lint "$HOME/Library/Services/<name>.workflow/Contents/Info.plist"
   plutil -lint "$HOME/Library/Services/<name>.workflow/Contents/document.wflow"
   ```
   Both must say `OK`. Any "Encountered unexpected character" or "Conversion of string failed" is a bug in the plist — fix before moving on.

2. **Confirm macOS indexed the Service**:
   ```bash
   /System/Library/CoreServices/pbs -dump_pboard | grep -A3 "<Your Menu Label>"
   ```
   You should see `NSBundlePath = "/Users/.../<name>.workflow"` and the `default = "<Your Menu Label>"` line. If it's absent, `pbs -flush && pbs -update` again. If still absent, the Info.plist is malformed.

3. **Open Automator.app and open the `.workflow` bundle** — Automator will load it if the wflow is valid, and show a warning or blank if not. Useful sanity check during development.

4. **First actual run** will prompt the user for permission for the Quick Action to control the target app (e.g. iTerm2). This is expected — accept it once.

5. **If the menu entry doesn't appear in Finder right-click**:
   - Check System Settings → Keyboard → Keyboard Shortcuts → Services → Files and Folders → is the entry listed and ticked?
   - On Tahoe, it may appear under the **Quick Actions** submenu of Finder's context menu rather than **Services**.
   - Relaunch Finder: `killall Finder`.

## Example: Full iTerm2 installer

```bash
#!/bin/bash
set -euo pipefail

NAME="Open in iTerm2"
DIR="$HOME/Library/Services/$NAME.workflow/Contents"
mkdir -p "$DIR"

cat > "$DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>NSServices</key>
  <array>
    <dict>
      <key>NSMenuItem</key><dict><key>default</key><string>Open in iTerm2</string></dict>
      <key>NSMessage</key><string>runWorkflowAsService</string>
      <key>NSRequiredContext</key><dict><key>NSApplicationIdentifier</key><string>com.apple.finder</string></dict>
      <key>NSSendFileTypes</key><array><string>public.folder</string></array>
    </dict>
  </array>
</dict>
</plist>
PLIST

# ... (document.wflow from the template above) ...

plutil -lint "$DIR/Info.plist"
plutil -lint "$DIR/document.wflow"
/System/Library/CoreServices/pbs -flush
/System/Library/CoreServices/pbs -update

echo "Installed. Enable under System Settings → Keyboard → Keyboard Shortcuts → Services → Files and Folders."
```

## Notes

- **Changing an existing service**: edit the files in place and re-run `pbs -flush && pbs -update`. No need to uninstall first.
- **Uninstall**: `rm -rf "$HOME/Library/Services/<name>.workflow" && /System/Library/CoreServices/pbs -flush`.
- **Per-machine vs per-user**: `~/Library/Services/` is user-scoped; `/Library/Services/` is machine-wide (requires sudo).
- **Quarantine**: bundles *created locally* don't get quarantined. Bundles downloaded (from a zip, git archive, etc.) may be quarantined — strip with `xattr -dr com.apple.quarantine <bundle>`.
- **Code signing**: unsigned workflows still run, but on future macOS versions this may tighten. For production distribution, sign the bundle with `codesign --deep`.
- **Tahoe (26.x) caveat**: the Finder context menu has moved things around — the old "Services" submenu now sometimes lives inside a "Quick Actions" submenu. Behaviour is unchanged; label hunting is the only friction.
- **You cannot redirect the built-in "New Terminal at Folder"** to iTerm2 via a preference; it's hardcoded to Terminal.app. A custom Service is the clean solution.
- **iTerm2 AppleScript shape**: modern iTerm2 (3.x+) uses `create window with default profile`, `create tab with default profile`, `tell current session of …`, and `write text "…"`. The old `do script` API still works but is discouraged.

## References

- Apple — [Services Implementation Guide](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/SysServices/introduction.html) (archived but still accurate for the Info.plist schema)
- Apple — [NSSendFileTypes / NSRequiredContext plist keys](https://developer.apple.com/documentation/bundleresources/information_property_list/nsservices)
- iTerm2 — [AppleScript documentation](https://iterm2.com/documentation-scripting.html)
- Uniform Type Identifiers reference: `man 5 uti` or [UTI concepts](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/understanding_utis/understand_utis_conc/understand_utis_conc.html)
