---
name: nextjs-root-layout-silent-script-failures
description: |
  Three silent failures in a Next.js App Router root layout that all render a
  perfectly normal-looking page. Use when: (1) a pre-hydration boot script
  (theme/locale/feature flag) never runs and the stored preference is ignored on
  reload, (2) an inline <script> you rendered inside a <head> element is missing
  from view-source entirely, (3) a script calls localStorage.getItem(undefined)
  or otherwise sees `undefined` where you passed an imported constant,
  (4) after adding a Content-Security-Policy the page renders but nothing is
  clickable and no JS handler fires. Root causes: constants exported from a
  "use client" module are client-reference proxies on the server; Next drops
  arbitrary inline scripts placed in <head> in a root layout; and CSP
  `default-src` is the fallback for `script-src`, so it blocks Next's inline
  hydration payload. None of the three throws, type-errors, or fails a build.
author: Claude Code
version: 1.0.0
date: 2026-08-12
---

# Next.js root-layout silent script failures

## Problem

Three independent bugs, all in `app/layout.tsx`, all of which leave a page that
renders correctly and passes typecheck, lint, unit tests and `next build`. Only
driving a real browser exposes them.

## Context / Trigger conditions

- Next.js App Router (verified on Next 16.3 + React 19.2, Turbopack).
- You added a pre-hydration boot script to avoid a theme flash.
- Symptoms, any of:
  - The stored preference is applied when you click the toggle but is gone after
    a reload.
  - `view-source` / `curl` shows no trace of your inline script.
  - The script is present but reads `localStorage.getItem(undefined)`.
  - After adding CSP headers the page paints but is completely inert: buttons do
    nothing, no console error that names CSP as the cause of the inertness.

## Solution

### 1. A constant imported from a `"use client"` module is `undefined` on the server

```ts
// lib/useTheme.ts
"use client";
export const THEME_KEY = "app.theme";   // ❌ server sees a client-reference proxy
```

```tsx
// app/layout.tsx  (a server component)
import { THEME_KEY } from "@/lib/useTheme";
const BOOT = `localStorage.getItem(${JSON.stringify(THEME_KEY)})`;
// → renders: localStorage.getItem(undefined)
```

When a server component imports from a `"use client"` module, the bundler
replaces the module with a client-reference object. Component/function exports
survive as references; **plain value exports do not** and read as `undefined`.
`JSON.stringify(undefined)` returns the *string* `"undefined"`, so template
interpolation happily bakes it into the script.

Fix: put shared constants in a module with **no** `"use client"` directive, and
import that from both sides.

```ts
// lib/theme-key.ts   (no directive)
export const THEME_KEY = "app.theme";
```

### 2. An inline `<script>` inside `<head>` in a root layout is dropped

```tsx
<html>
  <head>
    <script dangerouslySetInnerHTML={{ __html: BOOT }} />  {/* ❌ never emitted */}
  </head>
  <body>{children}</body>
</html>
```

Next manages `<head>` and does not emit arbitrary inline scripts placed there.
Put it as the **first child of `<body>`** — it still executes before the rest of
the body parses, so there is no flash:

```tsx
<html suppressHydrationWarning>
  <body>
    <script dangerouslySetInnerHTML={{ __html: BOOT }} />
    {children}
  </body>
</html>
```

### 3. CSP `default-src` blocks Next's inline hydration payload

```js
// ❌ page renders, then is completely inert
"default-src 'self'; frame-ancestors 'none'"
```

`default-src` is the fallback for `script-src`. Next emits its RSC/hydration
payload as **inline** `<script>` tags, so `'self'` blocks them: the server HTML
paints and the app never hydrates. Adding `'unsafe-inline'` would "fix" it while
asserting a protection you do not have.

Without a nonce pipeline, ship only the directives that do not touch scripts:

```js
"frame-ancestors 'none'; base-uri 'self'; form-action 'none'; object-src 'none'"
```

## Verification

```bash
# 1 + 2: the script must be in the HTML, with a real key
curl -s http://127.0.0.1:3000/ | grep -o "localStorage.getItem([^)]*)"
#   want: localStorage.getItem("app.theme")   not  getItem(undefined)

# 3: after any CSP change, prove the page is still interactive
npx playwright test          # a click-driven spec, not a render-only one
```

A render-only smoke test will **not** catch #3: the page renders fine. The test
must click something and assert the result.

## Example

Full working boot script (a theme, stamped before hydration):

```tsx
import { THEME_KEY } from "@/lib/theme-key";           // no "use client"

const BOOT = `try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});`
  + `if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
        {children}
      </body>
    </html>
  );
}
```

## Notes

- `suppressHydrationWarning` on `<html>` is still required, because the boot
  script sets an attribute the server markup deliberately omits.
- Failure #1 generalises past strings: any non-function export (config objects,
  enums, arrays) crossing the client-to-server boundary is affected. The
  direction matters — server importing *from* a client module is the broken one.
- Failure #3 also bites `style-src` if you use inline `style={{...}}` props,
  which React renders as style attributes.
- For the *hydration mismatch* side of theme handling (server renders the
  default, client reads storage during render), see the companion skill
  `nextjs-theme-localstorage-hydration`, which covers the `useSyncExternalStore`
  pattern. This skill covers the boot script and CSP instead.

## References

- [React: client-reference semantics for "use client" modules](https://react.dev/reference/rsc/use-client)
- [MDN: CSP default-src is the fallback for script-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/default-src)
- [Next.js: Content Security Policy with nonces](https://nextjs.org/docs/app/guides/content-security-policy)
