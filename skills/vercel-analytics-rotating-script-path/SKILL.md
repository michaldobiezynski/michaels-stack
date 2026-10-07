---
name: vercel-analytics-rotating-script-path
description: |
  Verify @vercel/analytics is actually working on a deployment, and avoid
  concluding it is broken when it is not. Use when: (1) you added <Analytics />
  and grep/curl for "_vercel/insights" on the deployed page returns nothing,
  (2) a Playwright or browser check for a script whose src contains "insights"
  finds no tag and no network request, (3) the analytics script is absent from
  the server-rendered HTML, (4) you need a non-flaky assertion that web
  analytics is wired up. Root causes: the SDK injects the tag client-side in an
  effect (so it is never in the SSR HTML), and Vercel serves the script from a
  ROTATING obfuscated path such as /6fc4c6f3fe5634ce/script.js to survive ad
  blockers, so the documented /_vercel/insights/script.js path does not appear.
author: Claude Code
version: 1.0.0
date: 2026-08-12
---

# Vercel Analytics: rotating script path

## Problem

After adding `<Analytics />`, every obvious check says analytics is broken:

- `curl https://site/ | grep insights` → nothing
- a browser check for `script[src*="insights"]` → no tag, no request

Both checks are wrong, and the feature is usually working fine.

## Context / Trigger conditions

- `@vercel/analytics` v2.x (verified on 2.0.1) in a Next.js App Router app.
- The package **is** in the deployed bundle (grep the deployed chunks for
  `_vercel/insights` and you will find it).
- `/_vercel/insights/script.js` returns 200 when fetched directly, yet no such
  script tag exists on the page.

## Solution

Two separate reasons the naive checks fail:

1. **The tag is injected client-side.** `<Analytics />` renders `null` and calls
   `inject()` from a `useEffect`, appending the script to `document.head` after
   hydration. It is never in the server HTML, so `curl` can never see it.

2. **The src is a rotating, obfuscated path.** On a real deployment the SDK
   reads a Vercel-injected config string and builds a src like
   `https://your-site.vercel.app/6fc4c6f3fe5634ce/script.js`. The hash changes.
   Only off-Vercel does it fall back to the documented
   `/_vercel/insights/script.js`.

**Assert on the SDK's own `data-sdkn` attribute**, which is stable across
deployments and framework entry points:

```ts
const tag = page.locator('head script[data-sdkn="@vercel/analytics/next"]');
await expect(tag).toHaveCount(1);
```

The value mirrors the entry point you imported: `@vercel/analytics/next`,
`@vercel/analytics/react`, `@vercel/analytics/sveltekit`, and so on. The
companion attribute `data-sdkv` carries the package version.

A second, cheaper signal that `inject()` ran at all:

```ts
await page.evaluate(() => typeof window.va === "function");   // queue shim
await page.evaluate(() => window.vam);                        // "production"
```

`window.va`, `window.vaq` and `window.vam` are installed by the same `inject()`
call that appends the tag, so if they exist the tag exists.

## Verification

```ts
test("web analytics is wired up", async ({ page }) => {
  const statuses: number[] = [];
  page.on("response", (r) => {
    if (r.request().resourceType() === "script"
        && /script\.js$/.test(new URL(r.url()).pathname)) {
      statuses.push(r.status());
    }
  });

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  await expect(
    page.locator('head script[data-sdkn="@vercel/analytics/next"]'),
  ).toHaveCount(1);
  expect(statuses.every((s) => s < 400)).toBe(true);   // a wrong path 404s
});
```

Run it against a deployment, and skip it locally:

```ts
test.skip(!process.env.E2E_BASE_URL, "needs a deployed URL");
```

Off Vercel the SDK still injects a tag, but the src resolves to
`/_vercel/insights/script.js`, which 404s without the Vercel edge. A local run
would go red for a reason that says nothing about the wiring.

## Example

What the head actually looks like on a working deployment:

```
/_next/static/immutable/chunks/2k8n-7ua74o0f.js
/_next/static/immutable/chunks/turbopack-2mntkq9ud9non.js
...
https://major-politics.vercel.app/6fc4c6f3fe5634ce/script.js   ← analytics
```

## Notes

- Import path per framework matters. For the Next App Router it is
  `@vercel/analytics/next`; check `package.json`'s `exports` map rather than
  copying a truncated snippet from the dashboard, which shows `@vercel/ana…`.
- If a CSP is in play, `script-src` must allow the site's own origin. Note the
  rotating path is same-origin, so `'self'` is enough; there is no third-party
  host to allow-list.
- `detectEnvironment()` keys off `process.env.NODE_ENV`. In `development` or
  `test` the src becomes `https://va.vercel-scripts.com/v1/script.debug.js`
  instead, which is a third-party origin and a different CSP question.
- Adding `<Analytics />` to a root layout does not break static prerendering:
  the page stays `○ (Static)`.

## References

- [Vercel Web Analytics quickstart](https://vercel.com/docs/analytics/quickstart)
- [@vercel/analytics package](https://www.npmjs.com/package/@vercel/analytics)
