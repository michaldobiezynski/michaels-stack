---
name: tauri-v2-plugin-pitfalls
description: |
  Tauri v2 plugin reliability issues: FS and HTTP plugins can silently fail.
  Use when: (1) readTextFile returns corrupted/null-byte data despite valid file on disk,
  (2) Tauri HTTP fetch hangs indefinitely with infinite spinner,
  (3) AbortController doesn't abort Tauri fetch,
  (4) SWR or React Query hooks never resolve when using Tauri commands as fetchers,
  (5) "JSON Parse error: Unrecognized token ''" from files that look valid,
  (6) writeTextFile fails with "expected a value for key path but the IPC call used a bytes payload",
  (7) Tauri event system silently drops events not registered in collect_events!() macro.
  Covers workarounds for @tauri-apps/plugin-http, @tauri-apps/plugin-fs, and
  Tauri v2 event system in pawn-au-chocolat and other Tauri v2 apps.
author: Claude Code
version: 2.0.0
date: 2026-04-02
---

# Tauri v2 Plugin Pitfalls: FS, HTTP, and Events

## Problem
Tauri v2's FS, HTTP, and event plugins can silently fail in ways that are
extremely hard to debug:
1. `readTextFile` may return null bytes (`\0\0`) instead of actual file content
2. The HTTP plugin's `fetch` can hang indefinitely without resolving or rejecting
3. `AbortController` does NOT work with Tauri's custom `fetch` implementation
4. `writeTextFile` fails with IPC serialisation error on macOS
5. Tauri events silently drop if not registered in `collect_events!()` macro

## Context / Trigger Conditions

### Null-byte file reads
- Error: `SyntaxError: JSON Parse error: Unrecognized token ''`
- The file looks valid when checked with `cat`, `xxd`, or any standard tool
- `readTextFile` from `@tauri-apps/plugin-fs` returns a string of null bytes
- `"\0\0".trim()` returns `"\0\0"` (null bytes are NOT whitespace)
- `JSON.parse("\0\0")` fails with the misleading "Unrecognized token ''" error

### HTTP fetch hanging
- Symptom: Infinite spinner, SWR/React Query `isLoading` stays `true` forever
- The URL works fine in `curl`, browser, and the website itself
- Tauri HTTP permissions are configured correctly in capabilities
- `AbortController` with `signal` option does NOT abort Tauri's fetch
- `Promise.race` with a timeout ALSO fails because the Tauri fetch keeps the
  Promise executor alive

### writeTextFile IPC serialisation failure
- Error: `invalid args 'path' for command 'write_text_file': command write_text_file expected a value for key path but the IPC call used a bytes payload`
- `writeTextFile` from `@tauri-apps/plugin-fs` fails when called from the frontend
- The file path and content are both valid strings
- This is a serialisation bug in the Tauri v2 FS plugin's IPC layer on macOS

### Tauri event system silently drops events
- `listen("event_name", callback)` never fires despite `emit("event_name", payload)` being called from Rust
- The event IS being emitted (confirmed via logging on Rust side)
- The event type is NOT registered in the `collect_events!()` macro in `main.rs`
- Tauri v2 specta requires ALL event types to be registered, or they are silently dropped

### SWR key race condition (related)
- `useSWR(opened ? os : null, fetcher)` where `os` comes from another async hook
- On first render, `os` is `undefined`, making the key `undefined`
- SWR disables fetching for `null`/`undefined`/`false` keys
- When `os` resolves, SWR SHOULD re-fetch, but if the fetcher itself hangs
  (due to Tauri HTTP), the spinner stays forever

## Solution

### For null-byte file reads
Guard `JSON.parse` with a null-byte check before parsing:

```typescript
const storedValue = await storage.getItem(key);
if (
  storedValue === null ||
  storedValue === undefined ||
  typeof storedValue !== "string" ||
  storedValue.trim() === "" ||
  storedValue.charCodeAt(0) === 0  // Catches null-byte corruption
) {
  return initialValue;
}
```

### For HTTP fetch hanging
**Use `window.fetch` directly** when the server has CORS enabled (`Access-Control-Allow-Origin: *`):

```typescript
// DON'T: Tauri HTTP plugin fetch can hang
import { fetch } from "@tauri-apps/plugin-http";
const data = await fetch(url); // May hang forever

// DO: Browser native fetch (when CORS allows)
const data = await window.fetch(url); // Reliable
```

If you must use Tauri's fetch (for non-CORS endpoints), wrap Tauri commands
in try-catch so one hanging command doesn't block the entire fetcher:

```typescript
async (os: Platform) => {
  let bmi2 = false;
  try {
    bmi2 = await commands.isBmi2Compatible();
  } catch {
    // Default gracefully if Tauri command fails
  }
  const response = await window.fetch(url);
  // ...
}
```

### For writeTextFile IPC failure
**Add a custom Rust command** to bypass the plugin entirely:

```rust
// src-tauri/src/fs.rs
#[tauri::command]
#[specta::specta]
pub async fn write_text_file(path: String, content: String, append: bool) -> Result<(), Error> {
    let p = Path::new(&path);
    if let Some(parent) = p.parent() {
        if !parent.exists() {
            create_dir_all(parent)?;
        }
    }
    if append {
        use std::io::Write;
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(p)?;
        file.write_all(content.as_bytes())?;
    } else {
        std::fs::write(p, content)?;
    }
    Ok(())
}
```

Then use `commands.writeTextFile(path, content, append)` instead of the plugin's `writeTextFile`.

### For silently dropped Tauri events
Register ALL event types in the `collect_events!()` macro in `main.rs`:

```rust
.events(tauri_specta::collect_events!(
    BestMovesPayload,
    DatabaseProgress,
    DownloadProgress,  // Must be here or listen() silently ignores it
    ReportProgress
))
```

Alternatively, bypass the event system entirely using `tokio::oneshot` channels
to return values directly from async Rust commands.

### For SWR key race conditions
Make the key explicitly falsy until all dependencies resolve:

```typescript
// DON'T: os=undefined makes key=undefined (disabled)
useSWR(opened ? os : null, fetcher);

// DO: Only activate when os is defined
useSWR(opened && os ? `engines-${os}` : null, fetcher);
```

## Verification
1. The JSON parse error disappears from terminal logs
2. The engine download list loads (with or without a brief delay)
3. SWR `isLoading` transitions to `false` after data loads
4. No infinite spinners in UI components that depend on Tauri fetches

## Example
In pawn-au-chocolat's `useDefaultEngines` hook:

```typescript
// Before (broken): Tauri fetch hangs, os race condition
import { fetch } from "@tauri-apps/plugin-http";
export function useDefaultEngines(os, opened) {
  return useSWR(opened ? os : null, async (os) => {
    const bmi2 = await commands.isBmi2Compatible();
    const data = await fetch("https://www.pawn-au-chocolat.com/engines.json");
    return (await data.json()).filter(e => e.os === os && e.bmi2 === bmi2);
  });
}

// After (working): Browser fetch, guarded key, resilient commands
export function useDefaultEngines(os, opened) {
  return useSWR(opened && os ? `engines-${os}` : null, async () => {
    let bmi2 = false;
    try { bmi2 = await commands.isBmi2Compatible(); } catch {}
    const data = await window.fetch("https://www.pawn-au-chocolat.com/engines.json");
    return (await data.json()).filter(e => e.os === os && e.bmi2 === bmi2);
  });
}
```

## Notes
- The null-byte corruption may be caused by a timing issue between Rust's
  `std::fs::write` and Tauri FS plugin's `readTextFile` on macOS
- The HTTP plugin issue may be macOS-specific (WebKit-based webview)
- The writeTextFile IPC failure is a serialisation bug in the plugin's IPC layer
- The released/bundled app may behave differently from `cargo tauri dev`
- Always check CORS headers (`curl -sI url | grep access-control`) before
  deciding to use `window.fetch` vs Tauri's fetch
- **General pattern**: When any Tauri v2 plugin fails, the reliable fix is to
  add a custom Rust `#[tauri::command]` that does the same thing via `std::fs`
  or `reqwest`, bypassing the plugin entirely
- These issues were observed with Tauri v2.0, @tauri-apps/plugin-http 2.0.0,
  @tauri-apps/plugin-fs 2.0.0 on macOS Darwin 25.4.0
