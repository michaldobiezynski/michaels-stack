---
name: isomorphic-dompurify-vercel-jsdom-lambda-crash
description: |
  Fix for Next.js routes that work locally but return HTTP 500 on Vercel
  production with error "Failed to load external module jsdom..." and
  "ERR_REQUIRE_ESM: require() of ES Module @exodus/bytes/encoding-lite.js
  from html-encoding-sniffer not supported". Triggered when a server-rendered
  page imports isomorphic-dompurify (directly or via a 'use client' component
  whose module is still evaluated during SSR). Root cause: isomorphic-dompurify
  pulls jsdom on the server, and jsdom's transitive dep html-encoding-sniffer
  hits a CommonJS-vs-ESM interop crash in Vercel's serverless runtime. Fix is
  to replace isomorphic-dompurify with sanitize-html (uses parse5, no jsdom).
  Also relevant when: (1) sanitising LLM-generated HTML on the server,
  (2) dev server is fine but `vercel --prod` deploy 500s only on specific
  routes, (3) local `next build && next start` works but lambda fails.
author: Claude Code
version: 1.0.0
date: 2026-05-22
---

# isomorphic-dompurify Crashes on Vercel Lambda

## Problem

A Next.js server component (or a `"use client"` component imported by one)
that uses `isomorphic-dompurify` works locally — both `npm run dev` AND
`npm run build && next start` — but returns HTTP 500 on Vercel production
deploys. The error in Vercel runtime logs is:

```
Error: Failed to load external module jsdom-<hash>:
Error [ERR_REQUIRE_ESM]: require() of ES Module
/var/task/node_modules/@exodus/bytes/encoding-lite.js
from /var/task/node_modules/html-encoding-sniffer/lib/html-encoding-sniffer.js
not supported.
  at Context.externalRequire ... .next/server/chunks/ssr/[turbopack]_runtime.js
```

The error mentions `@exodus/bytes` (which sounds suspicious but is just
Vercel's namespacing of the `bytes` package), `html-encoding-sniffer`
(a transitive dep of jsdom), and `[turbopack]_runtime.js` (Next.js 15+
bundler).

The page response body still contains your rendered RSC payload as a
giant `__next_f.push([1, ...])` chunk — the data is there, but the
`<html id="__next_error__">` wrapper signals the SSR threw and Next.js
returned the error shell.

## Context / Trigger Conditions

Hit this when ALL of these are true:

- Next.js App Router (verified on 16.2.6).
- Deployed to Vercel.
- A server component imports a module that transitively imports
  `isomorphic-dompurify`. A `"use client"` boundary does NOT save you —
  Next.js still evaluates the client module's code during SSR to render
  the initial HTML.
- The route returns HTTP 500.
- The Vercel runtime log shows `ERR_REQUIRE_ESM` somewhere mentioning
  `html-encoding-sniffer` or `@exodus/bytes`.

Local dev / `vercel build` locally / `next build && next start` all work
because the host Node version handles the ESM/CJS interop, but Vercel's
lambda runtime evaluates externals differently.

## Solution

Replace `isomorphic-dompurify` with `sanitize-html`. `sanitize-html` uses
`parse5` instead of jsdom, has no problematic ESM/CJS interop, and works
in both vitest (no special config) and Vercel serverless.

### Steps

```bash
npm uninstall isomorphic-dompurify
npm install sanitize-html
npm install --save-dev @types/sanitize-html
```

### Code change

Before:

```ts
import DOMPurify from "isomorphic-dompurify";

const SANITISE_CONFIG = {
  ALLOWED_TAGS: ["em", "strong", "a"],
  ALLOWED_ATTR: ["href", "class", "data-n"],
  ALLOWED_URI_REGEXP: /^#clip-\d+$/,
};

const clean = DOMPurify.sanitize(html, SANITISE_CONFIG);
```

After:

```ts
import sanitizeHtml from "sanitize-html";

const ANCHOR_HREF_RE = /^#clip-\d+$/;
const SANITISE_CONFIG: sanitizeHtml.IOptions = {
  allowedTags: ["em", "strong", "a"],
  allowedAttributes: { a: ["href", "class", "data-n"] },
  allowedSchemes: [],
  allowedSchemesByTag: { a: [] },
  transformTags: {
    a: (tagName, attribs) => {
      if (!attribs.href || !ANCHOR_HREF_RE.test(attribs.href)) {
        return { tagName, attribs: {} };
      }
      return { tagName, attribs };
    },
  },
};

const clean = sanitizeHtml(html, SANITISE_CONFIG);
```

Key contract differences:

- `allowedTags` (not `ALLOWED_TAGS`) — camelCase, lowercase enum-style.
- `allowedAttributes` is keyed by tag, not a flat array.
- DOMPurify's `ALLOWED_URI_REGEXP` doesn't exist; use `allowedSchemes: []`
  to deny all schemes (so http/https/javascript hrefs are dropped), then a
  `transformTags` hook to enforce a positive regex match on `href`.

## Verification

1. Local tests still pass (XSS regression tests against `<script>`,
   `<img onerror>`, `javascript:` href — sanitize-html strips them).
2. `npm run build` clean (no jsdom resolution warnings).
3. Push, wait for Vercel redeploy, hit the route — expect HTTP 200.
4. Optional: tail Vercel logs and verify no `ERR_REQUIRE_ESM` mentions.

## Example

Real session: a Next.js synthesis page in council-clip (Vercel-hosted)
returned HTTP 200 on `/clip` but HTTP 500 on `/synthesis/demo` after a
recent merge. Local `npm run build && next start` worked. Vercel runtime
logs showed `ERR_REQUIRE_ESM` from `html-encoding-sniffer`. The merged
PR had introduced `isomorphic-dompurify` to sanitise LLM-rendered HTML
in a `ProseParagraph` client component. Swapping to `sanitize-html` with
the equivalent allowlist (+ a `transformTags` hook to preserve the
`^#clip-\d+$` URI guard) fixed the production 500 in one commit. 57
frontend tests continued to pass; no contract change.

## Notes

- **The `"use client"` directive does not skip server-side module
  evaluation** in App Router. Adding `"use client"` to the component
  doesn't prevent the import from being evaluated during SSR for the
  initial HTML render.
- **`next/dynamic({ ssr: false })`** would skip SSR but causes a flash of
  empty content; not a great fix for prose. Switching the sanitiser is
  cleaner.
- **DOMPurify-family** alternatives that still use jsdom (e.g. plain
  `dompurify` paired with `jsdom` manually) will hit the same crash. The
  fix needs to be a non-jsdom sanitiser.
- **`sanitize-html` security**: it's a well-maintained allowlist
  sanitiser. Verify the version doesn't have known CVEs before adopting.
- **Existing XSS tests** (script tag, onerror, javascript: URL) should
  carry over and continue to pass against the new sanitiser — they assert
  on observable DOM behaviour, not on which library produced it.

## References

- [sanitize-html on npm](https://www.npmjs.com/package/sanitize-html)
- [DOMPurify issue tracker — jsdom interop](https://github.com/cure53/DOMPurify/issues)
  (search for "Vercel" or "lambda" + "ERR_REQUIRE_ESM" for related reports)
- [Vercel docs on serverless function externals](https://vercel.com/docs/functions/runtimes/node-js)
