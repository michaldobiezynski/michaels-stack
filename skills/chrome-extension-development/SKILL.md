---
name: chrome-extension-development
description: |
  Comprehensive guide for autonomously developing, testing, and iterating on Chrome extensions
  using Claude Code. Use when:
  (1) the user wants to create or modify a Chrome extension,
  (2) the user asks how to test a Chrome extension with Playwright or Puppeteer,
  (3) the user wants to iterate on extension UI using screenshots and console feedback,
  (4) the user asks about loading unpacked extensions programmatically,
  (5) the user encounters issues with --load-extension flag removal in Chrome 137+,
  (6) the user wants to set up E2E testing for a Chrome extension,
  (7) the user asks about WXT, Plasmo, or CRXJS extension frameworks,
  (8) the user wants to publish an extension to the Chrome Web Store via CLI,
  (9) the user needs to debug content scripts, service workers, or extension popups,
  (10) the user asks about hot module replacement (HMR) for Chrome extensions.
  Covers the complete lifecycle: scaffolding, development, testing, debugging, packaging,
  and publishing. Includes verified Playwright and Puppeteer APIs, Chrome CLI flag status,
  console capture limitations, and the autonomous iteration loop.
author: Claude Code
version: 1.0.0
date: 2026-02-22
---

# Chrome Extension Development with Claude Code

## Problem

Developing Chrome extensions traditionally requires manual browser interaction: loading
unpacked extensions via `chrome://extensions`, clicking reload, visually inspecting the
result, and checking multiple DevTools consoles. This manual loop makes it difficult for
an AI coding assistant to iterate autonomously.

This skill documents the complete, verified approach for Claude Code to develop, test,
and iterate on Chrome extensions without human intervention during the development loop.

## Context / Trigger Conditions

Use this skill when:

- Building a new Chrome extension from scratch
- Modifying an existing Chrome extension
- Setting up automated E2E testing for extensions
- Debugging content scripts, service workers, or popup UIs
- Encountering `--load-extension` flag issues on Chrome 137+
- Wanting to use WXT, Playwright, or Puppeteer with extensions
- Publishing extensions to the Chrome Web Store via CLI
- Needing visual feedback on extension UI rendering

---

## Part 1: The Autonomous Iteration Loop

### Overview

Claude Code can iterate on a Chrome extension without human intervention using this loop:

```
1. Write/edit extension source files
        |
2. Build the extension (if using a framework like WXT)
        |
3. Launch Playwright with bundled Chromium + extension loaded
        |
4. Navigate to target pages, take screenshots, capture console output
        |
5. Close browser
        |
6. Read screenshots (visual) + stdout/stderr (text) for feedback
        |
7. Analyse results, fix issues
        |
   Back to step 1
```

Every step is a CLI command or file operation. No human clicks required.

### Critical Requirements

1. **Playwright v1.49+** (new headless mode that supports extensions)
2. **Playwright v1.57+** (for service worker console capture via `sw.on('console')`)
3. **Playwright's bundled Chromium** (branded Chrome removed `--load-extension`)
4. **Direct Anthropic API** for screenshot reading (broken on OpenRouter/Bedrock)

### Iteration Cycle Time

Each edit-build-test cycle takes approximately 5-10 seconds:
- File edits: instant
- WXT build: 2-5 seconds
- Chromium launch + test: 1-3 seconds
- Browser close + result reading: instant

---

## Part 2: Chrome CLI Flag Status (Critical Knowledge)

### Flags Removed from Branded Chrome

| Flag | Removed In | Date | Still Works On |
|------|-----------|------|---------------|
| `--load-extension` | Chrome 137 | 27 May 2025 | Chromium, Chrome for Testing, ChromeOS |
| `--disable-extensions-except` | Chrome 139 | 5 August 2025 | Chromium, Chrome for Testing, ChromeOS |
| `--extensions-on-chrome-urls` | Chrome 139 | 5 August 2025 | Chromium, Chrome for Testing, ChromeOS |

A workaround (`--disable-features=DisableLoadExtensionCommandLineSwitch`) existed through
Chrome 141 but was removed in Chrome 142 (28 October 2025).

**Sources:**
- [RFC: Removing --load-extension](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/aEHdhDZ-V0E)
- [PSA: --load-extension removal](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/1-g8EFx2BBY)
- [PSA: --disable-extensions-except removal](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/FxMU1TvxWWg)

### Practical Impact

- **Playwright**: Unaffected. Ships bundled open-source Chromium where all flags work.
- **Puppeteer**: Unaffected. Uses bundled Chromium or Chrome for Testing.
- **Selenium**: Must use Chrome for Testing (`npx @puppeteer/browsers install chrome@stable`).
- **web-ext**: Broken on branded Chrome 137+. Fixed in web-ext 8.8.0+. Use Chrome for Testing.
- **Manual CLI launch**: Must use Chrome for Testing, not branded Chrome.

### All Extension-Related Chrome Flags

| Flag | Description |
|------|-------------|
| `--load-extension=<path>` | Load unpacked extension. Comma-separate multiple paths. |
| `--disable-extensions-except=<path>` | Disable all extensions except those specified. |
| `--disable-extensions` | Disable all extensions entirely. |
| `--allow-file-access-from-files` | Allow file:// URIs to read other file:// URIs. |
| `--extensions-on-chrome-urls` | Allow extensions on chrome:// URLs (removed Chrome 139). |
| `--pack-extension=<path>` | Pack extension into .crx file. |
| `--pack-extension-key=<path>` | Private key for packing. |
| `--no-first-run` | Skip first-run experience. |
| `--disable-default-apps` | Disable default apps on first run. |
| `--disable-component-extensions-with-background-pages` | Reduce noise in testing. |
| `--allow-future-manifest-version` | Load extensions with newer manifest versions. |
| `--enable-extension-activity-logging` | Enable extension activity logging. |

---

## Part 3: Playwright Extension Testing (Verified API)

### Loading an Extension

Extensions MUST be loaded via `launchPersistentContext`. Regular `launch()` does not
support extensions.

```javascript
const { chromium } = require('playwright');
const path = require('path');

const pathToExtension = path.resolve(__dirname, 'my-extension');
const userDataDir = '/tmp/test-user-data-dir';

const context = await chromium.launchPersistentContext(userDataDir, {
  channel: 'chromium',  // REQUIRED for headless extension support
  args: [
    `--disable-extensions-except=${pathToExtension}`,
    `--load-extension=${pathToExtension}`,
  ],
});
```

**Critical:** `channel: 'chromium'` is required. Without it, extensions silently fail
to load in headless mode. This opts into the new headless implementation (real Chromium
without a window) rather than the old headless shell.

**Source:** [playwright.dev/docs/chrome-extensions](https://playwright.dev/docs/chrome-extensions)

### Getting the Extension ID

```javascript
let [serviceWorker] = context.serviceWorkers();
if (!serviceWorker)
  serviceWorker = await context.waitForEvent('serviceworker');

const extensionId = serviceWorker.url().split('/')[2];
```

The service worker URL format is `chrome-extension://<id>/service-worker.js`.

**Limitation:** This only works if the extension has a service worker. For content-script-only
extensions, see "Extensions Without Service Workers" below.

### Accessing the Extension Popup

```javascript
const page = await context.newPage();
await page.goto(`chrome-extension://${extensionId}/popup.html`);
await page.screenshot({ path: 'popup.png' });
```

This opens the popup as a full page, not as the small overlay. For UI testing purposes
this is sufficient.

### Playwright Test Fixture Pattern

```typescript
import { test as base, chromium, type BrowserContext } from '@playwright/test';
import path from 'path';

export const test = base.extend<{
  context: BrowserContext;
  extensionId: string;
}>({
  context: async ({}, use) => {
    const pathToExtension = path.join(__dirname, 'my-extension');
    const context = await chromium.launchPersistentContext('', {
      channel: 'chromium',
      args: [
        `--disable-extensions-except=${pathToExtension}`,
        `--load-extension=${pathToExtension}`,
      ],
    });
    await use(context);
    await context.close();
  },
  extensionId: async ({ context }, use) => {
    let [sw] = context.serviceWorkers();
    if (!sw) sw = await context.waitForEvent('serviceworker');
    const extensionId = sw.url().split('/')[2];
    await use(extensionId);
  },
});

export const expect = test.expect;
```

**Source:** [playwright.dev/docs/chrome-extensions](https://playwright.dev/docs/chrome-extensions)

### Headless Mode

- **`channel: 'chromium'`**: Extensions work in headless (new headless mode). REQUIRED.
- **Default headless shell**: Extensions do NOT work.
- **`headless: false`**: Extensions work (headed mode).
- **macOS**: No display server needed for either mode.
- **Linux CI**: New headless mode works without Xvfb. Headed mode needs Xvfb.

**Source:** [Playwright issue #33566](https://github.com/microsoft/playwright/issues/33566),
[Playwright issue #34673](https://github.com/microsoft/playwright/issues/34673)

### Console Capture

#### Content Script Console

Playwright stores ALL execution contexts (including content script isolated worlds) in its
internal `_contextIdToContext` map. This means `page.on('console')` should capture content
script `console.log` output, unlike Puppeteer which filters to main world only.

```javascript
const logs = [];
page.on('console', msg => {
  logs.push(`[${msg.type()}] ${msg.text()}`);
});
page.on('pageerror', error => {
  logs.push(`[ERROR] ${error.message}`);
});

await page.goto('https://example.com');
// Content script logs should appear in `logs`
```

**Caveat:** No primary source explicitly confirms this for isolated world content scripts.
The evidence is strong but circumstantial (source code analysis of `crPage.ts`). For
maximum reliability, have content scripts communicate via DOM mutations or
`window.postMessage` to the main world.

#### Service Worker Console

`page.on('console')` does NOT capture service worker output. Use `sw.on('console')`
instead (Playwright v1.57+):

```javascript
let [sw] = context.serviceWorkers();
if (!sw) sw = await context.waitForEvent('serviceworker');

sw.on('console', msg => {
  console.log(`[SW] ${msg.text()}`);
});
```

**Known issues:**
- Service worker console capture only works from Playwright v1.57+
- There is a race condition with MV3 service worker attachment (issue #39075)
- `page.on('console')` never captures SW output (confirmed in issue #6559)

**Sources:**
- [Playwright issue #6559](https://github.com/microsoft/playwright/issues/6559) (SW console not on page)
- [Playwright issue #39075](https://github.com/microsoft/playwright/issues/39075) (SW race condition)
- [Playwright v1.57 release notes](https://playwright.dev/docs/release-notes#version-157)

### Error Detection

#### Manifest Errors

If `manifest.json` is invalid, Chromium starts but the extension silently doesn't load.
Playwright gives NO error. Detect this indirectly:

```javascript
const context = await chromium.launchPersistentContext(userDataDir, { /* ... */ });

// Check if extension loaded successfully
const serviceWorkers = context.serviceWorkers();
if (serviceWorkers.length === 0) {
  try {
    await context.waitForEvent('serviceworker', { timeout: 5000 });
  } catch {
    console.error('Extension failed to load. Check manifest.json.');
  }
}
```

Alternative: Navigate to `chrome://extensions` and scrape the error text.

#### Content Script Errors

Captured by `page.on('pageerror')` for uncaught exceptions, and `page.on('console')`
for `console.error` calls.

#### Service Worker Errors

Fragile. Use CDP as a workaround:

```javascript
const cdpSession = await context.newCDPSession(
  await context.newPage()
);
await cdpSession.send('Runtime.enable');
cdpSession.on('Runtime.consoleAPICalled', event => {
  const args = event.args.map(a => a.value || a.description).join(' ');
  console.log(`[CDP ${event.type}] ${args}`);
});
```

### Extensions Without Service Workers

If the extension has no service worker (content-script-only), `context.serviceWorkers()`
returns nothing and you cannot get the extension ID.

**Workarounds:**

1. **Add a minimal service worker** (simplest):
   ```json
   { "background": { "service_worker": "background.js" } }
   ```
   Create an empty `background.js`. This gives Playwright something to detect.

2. **Use the `key` field in manifest.json** for a deterministic ID:
   ```json
   { "key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..." }
   ```
   The ID is derived from SHA-256 of this key, first 32 hex chars mapped to a-p.

3. **Test through effects only**: Navigate to a matching page and assert on DOM changes.
   No extension ID needed.

---

## Part 4: Puppeteer Extension Testing (Verified API)

### Loading Extensions (v24.8.0+, May 2025)

#### Method A: At Launch Time

```javascript
const puppeteer = require('puppeteer');
const path = require('path');

const browser = await puppeteer.launch({
  pipe: true,  // REQUIRED for extension loading
  enableExtensions: [path.resolve(__dirname, 'my-extension')],
});
```

#### Method B: At Runtime

```javascript
const browser = await puppeteer.launch({
  pipe: true,
  enableExtensions: true,
});
await browser.installExtension(path.resolve(__dirname, 'my-extension'));
```

`browser.installExtension()` returns the extension ID.

**Requirements:**
- `pipe: true` is REQUIRED (uses `--remote-debugging-pipe`)
- Runtime installation also needs `--enable-unsafe-extension-debugging`
- Extensions do NOT work in `headless: 'shell'` (old headless mode)

**Source:** [pptr.dev/guides/chrome-extensions](https://pptr.dev/guides/chrome-extensions),
[PR #13824](https://github.com/puppeteer/puppeteer/pull/13824),
[PR #13810](https://github.com/puppeteer/puppeteer/pull/13810)

### Getting the Extension ID

```javascript
const workerTarget = await browser.waitForTarget(
  target => target.type() === 'service_worker'
    && target.url().endsWith('background.js')
);
const extensionId = new URL(workerTarget.url()).hostname;
```

### Opening the Popup (MV3)

```javascript
const worker = await workerTarget.worker();
await worker.evaluate('chrome.action.openPopup();');

const popupTarget = await browser.waitForTarget(
  target => target.type() === 'page' && target.url().endsWith('popup.html')
);
const popupPage = await popupTarget.asPage();
```

`chrome.action.openPopup()` works without restriction on Chrome 127+.

**Source:** [Chrome action API](https://developer.chrome.com/docs/extensions/reference/api/action)

### Service Worker Access

```javascript
const worker = await workerTarget.worker();

// Evaluate code in service worker context
const version = await worker.evaluate(() => {
  return chrome.runtime.getManifest().version;
});

// Send messages
const response = await worker.evaluate(() => {
  return new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'getData' }, resolve);
  });
});
```

### Testing Service Worker Termination (v22.1.0+)

```javascript
await worker.close(); // Kill the service worker

// Trigger an event that wakes it up
await page.goto('https://example.com');

// Wait for service worker to restart
const newWorkerTarget = await browser.waitForTarget(
  target => target.type() === 'service_worker'
);
```

**Source:** [Chrome: Test service worker termination](https://developer.chrome.com/docs/extensions/how-to/test/test-serviceworker-termination-with-puppeteer)

### Content Script Console Limitation

Puppeteer's `page.on('console')` does NOT capture content script isolated world logs.
This is by design in Puppeteer's source code (`FrameManager.ts`): only `MAIN_WORLD`
and `PUPPETEER_WORLD` execution contexts are tracked. Content script contexts are
silently discarded.

**Workaround:** Forward logs from content scripts to the service worker:

```javascript
// In content script
const _log = console.log;
console.log = (...args) => {
  chrome.runtime.sendMessage({ type: 'LOG', args: args.map(String) });
  _log.apply(console, args);
};
```

Then capture from the service worker target.

**Sources:**
- [Puppeteer source: FrameManager.ts](https://github.com/puppeteer/puppeteer/blob/main/packages/puppeteer-core/src/cdp/FrameManager.ts)
- [Puppeteer issue #4465](https://github.com/puppeteer/puppeteer/issues/4465)

### Playwright vs Puppeteer Comparison

| Feature | Playwright | Puppeteer |
|---------|-----------|-----------|
| Load at launch | `launchPersistentContext` + args | `enableExtensions: [path]` |
| Runtime install | Not supported | `browser.installExtension(path)` |
| Headless extensions | Yes (`channel: 'chromium'`) | No (`headless: false` required) |
| Content script console | Captured (all contexts stored) | NOT captured (filtered out) |
| SW console | `sw.on('console')` (v1.57+) | `worker.on('console')` |
| Kill service worker | Not directly supported | `worker.close()` (v22.1.0+) |
| Open popup | Navigate to URL only | `chrome.action.openPopup()` |
| `pipe: true` required | No | Yes |

**Recommendation:** Playwright is better for content script testing (captures isolated
world console). Puppeteer is better for service worker lifecycle testing (can kill/restart).

---

## Part 5: Extension Development Frameworks

### WXT (Recommended)

The leading Chrome extension framework. Vite-based, supports HMR, cross-browser.

```bash
npx wxt@latest init my-extension
cd my-extension
npm install
```

**Development:**
```bash
npx wxt dev          # HMR for popup, options, content scripts
npx wxt dev -b firefox  # Cross-browser dev
```

**Building:**
```bash
npx wxt build        # Output: .output/chrome-mv3/
npx wxt zip          # Create distributable zip
```

**E2E testing with Playwright** (officially documented):

1. Build: `npx wxt build`
2. Point Playwright at `.output/chrome-mv3/`
3. Run tests against the built extension

WXT's HMR does NOT compose with Playwright. They are separate workflows:
- **Development**: `wxt dev` (launches its own browser)
- **Testing**: `wxt build` then Playwright against `.output/chrome-mv3`

**Source:** [wxt.dev](https://wxt.dev/),
[WXT E2E testing guide](https://wxt.dev/guide/essentials/e2e-testing),
[WXT Playwright example](https://github.com/wxt-dev/examples/tree/main/examples/playwright-e2e-testing)

### Plasmo

Alternative framework with ~10k+ GitHub stars.

```bash
npm create plasmo
cd my-extension
npm run dev
```

Live-reloading optimised for React. Non-React code triggers full extension reload.

### CRXJS Vite Plugin

Vite plugin approach (no full framework).

```javascript
// vite.config.ts
import { crx } from '@crxjs/vite-plugin';
import manifest from './manifest.json';
export default { plugins: [crx({ manifest })] };
```

True HMR for content scripts. Full extension reload for service worker changes.

### Key Limitation Across All Frameworks

No framework achieves stateful hot-reload for MV3 service workers. The ephemeral,
event-driven nature of MV3 service workers makes this architecturally impossible.

---

## Part 6: Claude Code's Visual Feedback Loop

### Screenshot Reading

Claude Code's Read tool can read PNG/JPG files and present them visually to the model
(Claude is multimodal). This enables visual iteration on extension UIs.

```javascript
await page.screenshot({ path: 'result.png' });
await page.screenshot({ path: 'popup.png', fullPage: true });
await page.locator('#my-element').screenshot({ path: 'element.png' });
```

Claude Code then reads the screenshot: `Read tool on /path/to/result.png`

**Critical limitation:** Screenshot reading via the Read tool is broken on OpenRouter
and AWS Bedrock (issue #18588, still open February 2026). It works correctly on
direct Anthropic API (Claude Max/Pro/Teams/Enterprise).

**Source:** [Claude Code issue #18588](https://github.com/anthropics/claude-code/issues/18588),
[Claude Code docs: Work with images](https://code.claude.com/docs/en/common-workflows.md#work-with-images)

### Fallback: Text-Based Assertions

When screenshot reading is unavailable, use programmatic assertions:

```javascript
// Output text-based feedback to stdout
const title = await page.title();
console.log(`Page title: ${title}`);

const elementExists = await page.evaluate(() =>
  document.querySelector('#my-extension-element') !== null
);
console.log(`Extension element injected: ${elementExists}`);

const styles = await page.evaluate(() => {
  const el = document.querySelector('#my-extension-element');
  if (!el) return null;
  const cs = window.getComputedStyle(el);
  return { color: cs.color, fontSize: cs.fontSize, display: cs.display };
});
console.log(`Element styles: ${JSON.stringify(styles)}`);

const text = await page.locator('#my-extension-element').textContent();
console.log(`Element text: ${text}`);
```

Claude Code reads stdout from the script and gets structured feedback without
needing to interpret images.

### Recommended: Dual Feedback

Combine both approaches for maximum reliability:

```javascript
// Machine-readable feedback
const injected = await page.evaluate(() =>
  document.querySelector('#my-extension-overlay') !== null
);
console.log(`Extension injected: ${injected}`);

const consoleErrors = [];
page.on('pageerror', err => consoleErrors.push(err.message));

await page.goto('https://example.com');
await page.waitForTimeout(2000);

// Visual feedback
await page.screenshot({ path: 'result.png' });

// Summary
console.log(`Console errors: ${consoleErrors.length}`);
consoleErrors.forEach(e => console.log(`  - ${e}`));
```

---

## Part 7: Claude Code Chrome Integration

### `claude --chrome`

Claude Code has a `--chrome` flag that connects to your actual Chrome browser via the
"Claude in Chrome" browser extension.

```bash
claude --chrome
```

**Requirements:**
- Chrome or Edge only (not Brave, Arc, or other Chromium browsers)
- Claude in Chrome extension installed from Chrome Web Store
- Direct Anthropic plan (Pro, Max, Teams, Enterprise)
- NOT available via Bedrock, Vertex AI, or other third-party providers
- Claude Code 2.0.73+ and extension 1.0.36+
- Currently in beta
- WSL not supported

**Capabilities:**
- Open tabs and navigate
- Click, type, fill forms
- Read console errors and DOM state
- Extract data from web pages
- Record browser interactions as GIFs

**Use case for extensions:** Load your extension manually once via `chrome://extensions`,
then use `claude --chrome` for interactive testing in your real browser with existing
logins and session state.

**Source:** [code.claude.com/docs/en/chrome.md](https://code.claude.com/docs/en/chrome.md)

### MCP Servers for Browser Automation

- **Browser MCP** ([browsermcp.io](https://browsermcp.io/)): Chrome extension + MCP server combo
- **Chrome MCP Server** ([github.com/hangwin/mcp-chrome](https://github.com/hangwin/mcp-chrome)):
  ~10.4k stars, uses your actual Chrome session with existing logins
- **Playwright MCP**: Official MCP server for Playwright automation

---

## Part 8: Unit Testing

### jest-chrome (Unmaintained)

The original `jest-chrome` package (v0.8.0) has not been updated since November 2022.

**Use instead:** `@mobile-next/jest-chrome` (maintained fork with MV3 support).

```bash
npm install --save-dev @mobile-next/jest-chrome
```

```javascript
import { chrome } from '@mobile-next/jest-chrome';

test('queries active tab', async () => {
  const tab = { id: 1, active: true, url: 'https://example.com' };
  chrome.tabs.query.mockResolvedValue([tab]);

  const result = await chrome.tabs.query({ active: true });
  expect(result[0].id).toBe(1);
});
```

**Source:** [jest-chrome Snyk analysis](https://snyk.io/advisor/npm-package/jest-chrome),
[@mobile-next/jest-chrome on npm](https://www.npmjs.com/package/@mobile-next/jest-chrome)

### Chrome's Recommended Approach

Google recommends manual mocks:

```javascript
// mock-chrome.js
global.chrome = {
  tabs: { query: jest.fn() },
  storage: { local: { get: jest.fn(), set: jest.fn() } },
  runtime: { sendMessage: jest.fn() },
};
```

**Source:** [Chrome unit testing guide](https://developer.chrome.com/docs/extensions/how-to/test/unit-testing)

---

## Part 9: Packaging and Publishing

### Building a Zip

```bash
# Using WXT
npx wxt zip

# Using web-ext
web-ext build --source-dir ./my-extension --artifacts-dir ./dist

# Manual
cd my-extension && zip -r ../extension.zip . -x "*.git*" "node_modules/*"
```

### Chrome Web Store Upload

```bash
npm install -g chrome-webstore-upload-cli
```

```bash
chrome-webstore-upload upload \
  --source extension.zip \
  --extension-id <ID> \
  --client-id $CLIENT_ID \
  --client-secret $CLIENT_SECRET \
  --refresh-token $REFRESH_TOKEN
```

**Note:** The npm package is `chrome-webstore-upload-cli` but the CLI command is
`chrome-webstore-upload` (without `-cli`).

**Source:** [chrome-webstore-upload-cli on npm](https://www.npmjs.com/package/chrome-webstore-upload-cli)

### Installing Chrome for Testing

```bash
npx @puppeteer/browsers install chrome@stable
```

This downloads a Chrome build that supports `--load-extension` regardless of version.

**Source:** [@puppeteer/browsers on npm](https://www.npmjs.com/package/@puppeteer/browsers),
[Chrome for Testing blog](https://developer.chrome.com/blog/chrome-for-testing)

### CRX Packaging

The `crx` npm package is officially **deprecated**. Use `web-ext build` for zip files
(Chrome Web Store accepts zips) or Chrome's built-in packing:

```bash
# Chrome's built-in (requires Chrome for Testing on 137+)
/path/to/chrome --pack-extension=/path/to/extension --pack-extension-key=key.pem
```

---

## Part 10: Complete Test Harness Example

This is a ready-to-use test script that Claude Code can write and execute:

```javascript
// test-extension.js
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const extPath = path.resolve(__dirname, '.output/chrome-mv3');
  const userDataDir = '/tmp/ext-test-' + Date.now();

  // Launch with extension
  const context = await chromium.launchPersistentContext(userDataDir, {
    channel: 'chromium',
    args: [
      `--disable-extensions-except=${extPath}`,
      `--load-extension=${extPath}`,
    ],
  });

  // Verify extension loaded
  let sw;
  try {
    [sw] = context.serviceWorkers();
    if (!sw) sw = await context.waitForEvent('serviceworker', { timeout: 5000 });
    const extensionId = sw.url().split('/')[2];
    console.log(`Extension loaded. ID: ${extensionId}`);
  } catch {
    console.error('FAILED: Extension did not load. Check manifest.json.');
    await context.close();
    process.exit(1);
  }

  // Capture service worker console (Playwright v1.57+)
  sw.on('console', msg => {
    console.log(`[SW ${msg.type()}] ${msg.text()}`);
  });

  // Test content script injection
  const page = await context.newPage();
  const pageLogs = [];
  const pageErrors = [];

  page.on('console', msg => pageLogs.push(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => pageErrors.push(err.message));

  await page.goto('https://example.com');
  await page.waitForTimeout(2000);

  // Check for injected elements
  const injected = await page.evaluate(() => {
    const el = document.querySelector('[data-extension-injected]');
    return el ? el.textContent : null;
  });
  console.log(`Content script injected: ${injected !== null}`);
  if (injected) console.log(`Injected content: ${injected}`);

  // Screenshot the page
  await page.screenshot({ path: 'page-result.png', fullPage: true });
  console.log('Screenshot saved: page-result.png');

  // Test popup
  const extensionId = sw.url().split('/')[2];
  const popupPage = await context.newPage();
  await popupPage.goto(`chrome-extension://${extensionId}/popup.html`);
  await popupPage.screenshot({ path: 'popup-result.png' });
  console.log('Popup screenshot saved: popup-result.png');

  // Summary
  console.log('\n--- Results ---');
  console.log(`Page console messages: ${pageLogs.length}`);
  pageLogs.forEach(l => console.log(`  ${l}`));
  console.log(`Page errors: ${pageErrors.length}`);
  pageErrors.forEach(e => console.log(`  ${e}`));

  await context.close();
  console.log('Done.');
})();
```

Claude Code runs this via `node test-extension.js`, reads the stdout and the
screenshot files, and iterates.

---

## Part 11: Manifest V3 Service Worker Pitfalls

### Global Variables Are Lost on Termination

MV3 service workers are ephemeral. They terminate after ~30 seconds of inactivity.

```javascript
// BAD: state lost when service worker terminates
let data;
chrome.runtime.onInstalled.addListener(() => {
  data = { version: chrome.runtime.getManifest().version };
});

// GOOD: use persistent storage
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    version: chrome.runtime.getManifest().version,
  });
});
```

### Event Listeners Must Be Synchronous Top-Level

```javascript
// BAD: listener registered after await
const config = await fetchConfig();
chrome.runtime.onMessage.addListener(handler); // May not be registered in time

// GOOD: register synchronously, then use async inside
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleAsync(message).then(sendResponse);
  return true; // Keep sendResponse alive
});
```

**Source:** [Chrome service worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle)

---

## Part 12: Getting a Stable Extension ID

### Method: `key` Field in manifest.json

1. The ID is derived from SHA-256 of the public key, first 32 hex chars mapped to a-p
2. Without a `key` field, unpacked extensions get an ID based on the absolute directory path (changes across machines)
3. To get a stable ID, add the `key` field from a published version's manifest

```javascript
// Calculate extension ID from public key
const crypto = require('crypto');
function extensionId(publicKeyBase64) {
  const hash = crypto.createHash('sha256')
    .update(Buffer.from(publicKeyBase64, 'base64'))
    .digest('hex');
  return hash.substring(0, 32).split('')
    .map(c => String.fromCharCode('a'.charCodeAt(0) + parseInt(c, 16)))
    .join('');
}
```

**Source:** [Chrome manifest key docs](https://developer.chrome.com/docs/extensions/reference/manifest/key)

---

## Verification

To verify the autonomous loop works:

1. Install Playwright: `npm init playwright@latest`
2. Create a minimal extension (manifest.json + content script)
3. Run the test harness script above
4. Confirm: extension loads, screenshot is taken, console output is captured
5. Have Claude Code read the screenshot and interpret it

## Notes

- **Playwright is preferred over Puppeteer** for extension development because it
  captures content script console output that Puppeteer silently drops
- **Each iteration requires a full browser relaunch** (~1-3 seconds). No hot-reload
  mechanism exists for Playwright-loaded extensions
- **The `crx` npm package is deprecated**. Use `web-ext build` or manual zip instead
- **The original `jest-chrome` is abandoned** (last updated Nov 2022). Use
  `@mobile-next/jest-chrome` for MV3 support
- **WXT is the recommended framework** for new extensions. Plasmo is a viable alternative
- All information in this skill was verified against primary sources in February 2026

## References

- [Playwright Chrome Extensions Docs](https://playwright.dev/docs/chrome-extensions)
- [Playwright Screenshots API](https://playwright.dev/docs/screenshots)
- [Playwright v1.57 Release Notes](https://playwright.dev/docs/release-notes#version-157)
- [Playwright Issue #33566: Headless Changes](https://github.com/microsoft/playwright/issues/33566)
- [Playwright Issue #34673: Extension Headless Bug](https://github.com/microsoft/playwright/issues/34673)
- [Playwright Issue #6559: SW Console Not on Page](https://github.com/microsoft/playwright/issues/6559)
- [Playwright Issue #39075: SW Race Condition](https://github.com/microsoft/playwright/issues/39075)
- [Playwright Source: crPage.ts](https://github.com/microsoft/playwright/blob/main/packages/playwright-core/src/server/chromium/crPage.ts)
- [Puppeteer Chrome Extensions Guide](https://pptr.dev/guides/chrome-extensions)
- [Puppeteer PR #13824: enableExtensions](https://github.com/puppeteer/puppeteer/pull/13824)
- [Puppeteer PR #13810: installExtension](https://github.com/puppeteer/puppeteer/pull/13810)
- [Puppeteer Source: FrameManager.ts](https://github.com/puppeteer/puppeteer/blob/main/packages/puppeteer-core/src/cdp/FrameManager.ts)
- [Chrome: Test Extensions with Puppeteer](https://developer.chrome.com/docs/extensions/how-to/test/puppeteer)
- [Chrome: Test SW Termination](https://developer.chrome.com/docs/extensions/how-to/test/test-serviceworker-termination-with-puppeteer)
- [Chrome: Unit Testing Guide](https://developer.chrome.com/docs/extensions/how-to/test/unit-testing)
- [Chrome: Service Worker Lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle)
- [Chrome: Content Scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)
- [Chrome: Manifest Key](https://developer.chrome.com/docs/extensions/reference/manifest/key)
- [Chrome: action API](https://developer.chrome.com/docs/extensions/reference/api/action)
- [Chrome: --load-extension Removal RFC](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/aEHdhDZ-V0E)
- [Chrome: --disable-extensions-except Removal PSA](https://groups.google.com/a/chromium.org/g/chromium-extensions/c/FxMU1TvxWWg)
- [Chrome for Testing Blog](https://developer.chrome.com/blog/chrome-for-testing)
- [Claude Code: Work with Images](https://code.claude.com/docs/en/common-workflows.md#work-with-images)
- [Claude Code Issue #18588: Image Reading Bug](https://github.com/anthropics/claude-code/issues/18588)
- [Claude Code Chrome Integration](https://code.claude.com/docs/en/chrome.md)
- [WXT Framework](https://wxt.dev/)
- [WXT E2E Testing Guide](https://wxt.dev/guide/essentials/e2e-testing)
- [WXT Playwright Example](https://github.com/wxt-dev/examples/tree/main/examples/playwright-e2e-testing)
- [chrome-webstore-upload-cli](https://www.npmjs.com/package/chrome-webstore-upload-cli)
- [@puppeteer/browsers](https://www.npmjs.com/package/@puppeteer/browsers)
- [web-ext](https://github.com/mozilla/web-ext)
- [@mobile-next/jest-chrome](https://www.npmjs.com/package/@mobile-next/jest-chrome)
- [Browser MCP](https://browsermcp.io/)
- [Chrome MCP Server](https://github.com/hangwin/mcp-chrome)
- [CDP Runtime Domain](https://chromedevtools.github.io/devtools-protocol/tot/Runtime/)
