---
name: nextjs-theme-localstorage-hydration
description: |
  Fix React/Next.js App Router hydration mismatches caused by a theme (or any
  preference) read from localStorage during render. Use when: (1) the dev
  overlay shows "A tree hydrated but some attributes of the server rendered HTML
  didn't match the client properties" pointing at a theme toggle or <html>
  data-theme; (2) a hook seeds state with useState(() => localStorage.getItem(...));
  (3) the React Compiler / react-hooks lint errors "Calling setState
  synchronously within an effect can trigger cascading renders" when you try to
  fix it by reading storage in useEffect. Covers the useSyncExternalStore +
  suppressHydrationWarning pattern with a pre-hydration boot script.
author: Claude Code
version: 1.0.0
date: 2026-06-03
---

# Next.js theme-from-localStorage hydration

## Problem
A theme picker (or any client preference) persisted in localStorage renders
fine on its own but throws a React hydration mismatch once a non-default value
is saved: the server renders the default, the client's first render reads the
stored value, and the two trees diverge ("...some attributes of the server
rendered HTML didn't match the client properties").

## Context / Trigger conditions
- Next.js App Router (or any SSR React) with a `"use client"` theme component.
- A hook like `const [theme] = useState(() => readFromLocalStorage())`. The
  initialiser runs on the client during the hydration render, so the hydration
  output already differs from the server HTML.
- Often paired with a pre-hydration inline `<script>` ("boot script") that sets
  `document.documentElement.dataset.theme` before React runs, to avoid a flash.
- Trying to fix it by moving the read into `useEffect(() => setTheme(read()))`
  trips the React Compiler lint: "Calling setState synchronously within an
  effect can trigger cascading renders".

## Solution
Use `useSyncExternalStore` — it is purpose-built for this server/client snapshot
split and produces NO hydration warning, because React renders the
`getServerSnapshot` value for SSR + the first hydration render, then re-reads
`getSnapshot` on the client (synchronously, before paint).

```ts
"use client";
import { useCallback, useEffect, useSyncExternalStore } from "react";

const KEY = "app.theme";
const DEFAULT = "quiet";

function readStored() {
  if (typeof window === "undefined") return DEFAULT;
  try { return localStorage.getItem(KEY) ?? DEFAULT; } catch { return DEFAULT; }
}
function applyToDom(t: string) {
  if (typeof document !== "undefined") document.documentElement.dataset.theme = t;
}

// Module-level registry so a change re-renders every consumer.
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => { listeners.add(cb); return () => { listeners.delete(cb); }; };

export function useTheme() {
  // getServerSnapshot (3rd arg) = DEFAULT on server + first hydration render;
  // getSnapshot (2nd arg) = the persisted value on the client. No mismatch.
  const theme = useSyncExternalStore(subscribe, readStored, () => DEFAULT);

  // DOM sync is a side effect (NOT setState), so the lint rule is satisfied.
  useEffect(() => { applyToDom(theme); }, [theme]);

  const setTheme = useCallback((next: string) => {
    try { localStorage.setItem(KEY, next); } catch {}
    applyToDom(next);
    listeners.forEach((l) => l());   // notify consumers to re-read the snapshot
  }, []);

  return { theme, setTheme };
}
```

Also add `suppressHydrationWarning` to the `<html>` element in the root layout,
because the pre-hydration boot script sets `data-theme` on `<html>` and the
server markup intentionally omits it:

```tsx
<html lang="en" suppressHydrationWarning> ... </html>
```

## Verification
- Persist a non-default theme, hard-reload, and confirm the dev server log shows
  **no** "tree hydrated but some attributes..." line (drive it headlessly with
  agent-browser: set localStorage, reload, grep the dev log).
- `eslint` no longer reports the setState-in-effect error.
- A `getSnapshot` returning a primitive (string) is stable across calls by
  value, so React does not loop.

## Notes
- `getServerSnapshot` participates only in SSR/first-hydration; client change
  detection is entirely via the `subscribe` callback. This pattern does NOT add
  cross-tab sync by itself — add a `storage` event listener inside `subscribe`
  if you need it.
- Keep the boot script: it paints the correct theme before hydration so there is
  no flash; the hook + effect then re-sync React state to it without warnings.
- Do NOT "fix" the warning by seeding `useState` from storage or by calling
  `setState` inside an effect; both reintroduce the mismatch or the lint error.

## References
- React docs: useSyncExternalStore (https://react.dev/reference/react/useSyncExternalStore)
- React hydration mismatch (https://react.dev/link/hydration-mismatch)
- next-themes uses the same suppressHydrationWarning + post-mount-resolve approach.
