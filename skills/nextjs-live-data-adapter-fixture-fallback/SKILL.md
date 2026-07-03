---
name: nextjs-live-data-adapter-fixture-fallback
description: |
  Wire fixture-backed Next.js (App Router) screens to a live backend API with
  graceful degradation. Use when: (1) migrating pages that read local fixtures
  to fetch live data, (2) the backend returns a shape that does NOT match the
  view's structured props (e.g. a flat block document vs structured
  chapters/entries/groups), (3) some structured fields cannot be supplied by
  the live payload, (4) you need pages to never 500 / never render a blank live
  page. Covers the server-only fetch + pure adapter + fixture-fallback layering,
  the "return null on lossy/empty" honesty rule, structure-from-block-order
  reconstruction, and the vitest idiom for server-only fetch.
author: Claude Code
version: 1.0.0
date: 2026-06-04
---

# Next.js live-data wiring with adapter + fixture fallback

## Problem
A set of Next.js App Router screens already render from local fixtures via
synchronous getters that never fail. You must wire them to a live backend whose
response shape differs from the view's structured props, and some of the view's
fields cannot be derived from the live payload. Naively fetching and force-
mapping produces blank or half-built live pages presented as complete.

## Context / Trigger Conditions
- Pages call a synchronous fixture getter (`getX(slug)`) that always returns a
  value (so routes never 500).
- The backend returns a flat/document shape (e.g. `{blocks[], clips{}, trace[]}`)
  but the view wants structured arrays (`chapters`, `entries`, `groups`, sides).
- The route param does not always carry enough information for the live call
  (e.g. the backend needs two ids + a topic but the route only has one slug).

## Solution
Three layers, each independently testable:

1. **server-only fetch** (`lib/xFetch.ts`, first line `import "server-only";`):
   reads a non-`NEXT_PUBLIC_` base URL, `fetch(..., { cache: "no-store" })`,
   returns `null` on unset-base / non-ok / throw. Never let env reach the client.

2. **pure adapters** (`lib/xAdapters.ts`, no server-only): map the backend
   payload to each structured view type. Two rules:
   - **Return `null`** when the payload is missing OR yields no usable content
     OR a load-bearing field cannot be reconstructed (e.g. a timeline with no
     recoverable dates). Do NOT emit a half-built object.
   - **Reconstruct structure from block order/type**: when the backend encodes
     sections as a flat list (a heading block opens a section, following item
     blocks attach to it), walk the blocks to rebuild the structure. Fill fields
     the payload genuinely lacks honestly (empty string / derived-from-other-
     fields), never fabricated, and document each in a comment.

3. **loaders** glue them: `adapt(await fetchX(path)) ?? getFixture(slug)`. The
   page becomes `async` and `await loadX(slug)`; it always gets a valid object,
   so it stays never-fail. `generateMetadata` calls the same loader.

When the route param is insufficient, make the live call opt-in via
`searchParams` (the page already receives them in Next 16 as a Promise); without
the required params, return the fixture and do not fetch.

## Verification
- `npx tsc --noEmit` clean; `npx vitest run` green; `npm run build` succeeds and
  the wired routes flip to dynamic (`ƒ`) because of `no-store`.
- Adapter unit tests assert: structure reconstruction, lossy-field fills, and
  `null` on empty/lossy/null input.
- Fetch tests assert: URL per type, `cache: "no-store"`, `null` on
  unset/non-ok/throw, and that opt-in loaders do NOT fetch without their params.

## Example
```ts
// adapter: null on lossy input so the page falls back to the fixture
export function adaptArc(payload: Payload | null, topic: string): ArcCollection | null {
  if (!payload) return null;
  const clips = clipList(payload);
  if (clips.length === 0) return null;
  const entries = clips.map((clip, i) => ({ year: yearFrom(raw[i]), clip /* ... */ }));
  const years = entries.map((e) => e.year).filter((y) => y > 0);
  if (years.length === 0) return null; // timeline needs dates -> fall back
  return { type: "arc", topic, entries, /* ... */ };
}
// loader: adapt-or-fixture
export async function loadArc(id: string, sp: SearchParams = {}) {
  const speakerId = one(sp.speaker_id), t = one(sp.topic);
  if (!speakerId || !t) return getArc(id);               // opt-in, no fetch
  return adaptArc(await fetchPayload(`arc/${enc(speakerId)}?topic=${enc(t)}`), t) ?? getArc(id);
}
```

## Notes
- vitest idiom for the server-only fetch: alias `server-only` to an empty stub
  in `vitest.config.ts`; in tests reassign `global.fetch` and copy/restore
  `process.env` in `beforeEach`/`afterEach` (no `vi.mock`/`vi.stubEnv`/MSW).
  Cast partial fetch mocks `as unknown as typeof fetch`. Assert URL + options
  together with `expect.objectContaining({ cache: "no-store" })`.
- Decode HTML entities when extracting plain text from sanitised HTML prose for
  React text children: a server-side sanitiser (nh3/html5ever) serialises bare
  `& < >` as `&amp; &lt; &gt;`. Strip tags then decode, `&amp;` LAST.
- XSS: confirm the views render adapter-derived strings as text nodes (escaped),
  not via `dangerouslySetInnerHTML`.
- If the live payload drops a field the structured view needs (e.g. a per-item
  date), prefer fixing the backend to surface it (additive) AND keep the adapter
  forward-compatible (read it if present, fall back to fixture if not).
