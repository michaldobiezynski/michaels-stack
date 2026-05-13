---
name: playwright-cdp-persistent-browser
description: |
  Pattern for maintaining a persistent headless Chrome browser across multiple
  CLI invocations using Chrome DevTools Protocol (CDP). Use when: (1) building
  CLI tools that need to interact with a browser across separate commands,
  (2) creating bw.py-style browser helpers for AI agents, (3) needing browser
  state (cookies, session, page) to persist between script runs, (4) reducing
  Playwright startup overhead from 1-2s to near-zero per command. Covers:
  Chrome launch with --remote-debugging-port, connect_over_cdp, PID management,
  and safe disconnect without killing the browser.
author: Claude Code
version: 1.0.0
date: 2026-03-31
---

# Playwright CDP Persistent Browser Pattern

## Problem
Each Playwright script launch starts a new browser (1-2s overhead). For CLI tools
where you run many short commands against the same browser session, this overhead
dominates. You need browser state to persist between invocations.

## Context / Trigger Conditions
- Building CLI browser tools (like `bw.py`) for AI agents to drive
- Need to run `navigate`, `click`, `read` as separate CLI calls
- Browser session (cookies, localStorage, page state) must persist
- Want to reduce per-command overhead from ~2s to ~200ms

## Solution

### Architecture

```
Chrome (--remote-debugging-port=9222)  ← long-lived process
    ↑
bw.py start     → launches Chrome, saves PID to .bw_state
bw.py navigate  → connect_over_cdp → navigate → disconnect
bw.py click     → connect_over_cdp → click → disconnect
bw.py stop      → kills Chrome PID
```

### 1. Find Playwright's bundled Chromium

```python
from pathlib import Path

def find_chromium() -> str:
    pw_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    for d in sorted(pw_cache.glob("chromium-*"), reverse=True):
        b = (d / "chrome-mac-arm64" /
             "Google Chrome for Testing.app" /
             "Contents" / "MacOS" /
             "Google Chrome for Testing")
        if b.exists():
            return str(b)
    raise RuntimeError("Chromium not found")
```

### 2. Launch Chrome with remote debugging

```python
import subprocess, json, time
from pathlib import Path

STATE_FILE = Path(".bw_state")
CDP_PORT = 9222

def start():
    proc = subprocess.Popen([
        find_chromium(),
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--disable-gpu",
        "--window-size=1280,720",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for CDP to be ready
    import urllib.request
    for _ in range(10):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version")
            break
        except Exception:
            continue

    STATE_FILE.write_text(json.dumps({"pid": proc.pid, "port": CDP_PORT}))
```

### 3. Connect, execute, disconnect (per command)

```python
from playwright.sync_api import sync_playwright

def connect():
    """Connect to running browser. Returns (pw, browser, page)."""
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    contexts = browser.contexts
    if contexts and contexts[0].pages:
        page = contexts[0].pages[0]
    else:
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        page = ctx.new_page()
    return pw, browser, page

def disconnect(pw):
    """Disconnect WITHOUT killing Chrome."""
    try:
        pw.stop()  # Drops WebSocket connection, Chrome stays alive
    except Exception:
        pass
```

### 4. Stop browser

```python
import os, signal

def stop():
    state = json.loads(STATE_FILE.read_text())
    os.kill(state["pid"], signal.SIGTERM)
    STATE_FILE.unlink(missing_ok=True)
```

### Critical: disconnect safely

**DO NOT call `browser.close()`** on a CDP connection — it may clear contexts
and close pages. Instead, call `pw.stop()` which drops the WebSocket connection
but leaves Chrome and all its state intact.

## Verification

```bash
# Start
python bw.py start          # "Browser started (PID 1234)"

# Navigate
python bw.py go "https://example.com"   # Shows page text

# State persists
python bw.py js "document.title"        # Returns "Example Domain"

# Stop
python bw.py stop            # "Browser stopped"
```

## Notes
- The Chrome binary path is macOS ARM64-specific. For Linux:
  `chromium-*/chrome-linux64/chrome`
- `--headless=new` (Chrome's new headless mode) is required for CDP compatibility
- The `.bw_state` file should be gitignored
- If Chrome crashes, the PID file becomes stale — check with `os.kill(pid, 0)`
  before connecting and clean up if the process is gone
- Suppress Playwright's Node.js deprecation warnings with
  `os.environ["NODE_NO_WARNINGS"] = "1"` before importing
- Each `connect_over_cdp` takes ~200ms (vs ~2s for a full browser launch)
- The default context's page persists across connections — this is how state
  (URL, cookies, localStorage) survives between CLI invocations
