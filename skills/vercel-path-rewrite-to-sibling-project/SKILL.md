---
name: vercel-path-rewrite-to-sibling-project
description: |
  Serve one Vercel project under a path of another project's domain (e.g. a Vite game at
  example.com/play behind a Next.js marketing site). Use when: (1) you want /play (or /app, /docs)
  on the main domain to come from a separate deploy, (2) you worry the target's *.vercel.app URL is
  behind Vercel Authentication and the proxy would get a login page, (3) /play/ answers 308 to /play
  in Next.js, (4) a rewrite env var seems ignored, (5) `vercel project protection` is not a known
  command, (6) you need a PREVIEW of both together but the sibling's previews are behind Vercel
  Authentication (the proxy would get a 302 to a login). Covers base-path builds, prefix-stripping
  rewrites, which URLs deployment protection covers, build-time env in next.config, a prebuilt CLI
  deploy for a project with no Git link, and a combined protected preview with no security change.
author: Claude Code
version: 1.1.0
date: 2026-09-27
---

# Serve a sibling Vercel project under a path

## Problem
Two apps, one domain: a Next.js site owns example.com and a separate static app (Vite) should appear
at example.com/play with the same origin (no iframe cross-origin issues, no CORS).

## Solution
1. **Build the app for the path.** Vite: `vite build --base=/play/` and move every hard-coded root path
   (`'/models/x.glb'`, worker URLs, `fetch('/...')`) onto `import.meta.env.BASE_URL`. Keep dev at `/`
   by passing the base only in the public build script.
2. **Serve the build at its own root**, not under /play: the Vercel project for the app outputs the
   build directory (`vercel.json`: `buildCommand`, `outputDirectory`), so its files live at `/assets/...`.
3. **Rewrite with the prefix dropped** in the site's `next.config.ts`:
   ```ts
   const game = process.env.GAME_ORIGIN; // read at BUILD time: set it before the site builds
   async rewrites() {
     if (!game) return [];
     return [
       { source: "/play", destination: `${game}/` },
       { source: "/play/:path*", destination: `${game}/:path*` },
     ];
   }
   ```
   The browser asks example.com/play/assets/x.js; Vercel proxies game-origin/assets/x.js.
4. **Target the project's production alias** (`<project>.vercel.app`). With the team default
   `ssoProtection: all_except_custom_domains`, that alias answered 200 publicly while per-deployment
   URLs (`<project>-<hash>-<team>.vercel.app`) 302 to a login. So no protection change was needed;
   check with curl before disabling anything.

## Gotchas (all observed 25/09/2026)
- Next.js answers `/play/` with a 308 to `/play` (trailingSlash false); the rewrite then serves it. A
  test that flags requests outside `/play/` must allow the exact path `/play`.
- `vercel env add NAME preview` in non-interactive mode wants a Git branch; production alone worked.
- Vercel CLI 50.35 has no `vercel project protection`; read and change `ssoProtection` through the API
  (Vercel MCP `get_project` / `update_project`).
- For a project without a Git link: `vercel link --project <name>`, `vercel pull --environment=production`,
  `vercel build --prod`, `vercel deploy --prebuilt --prod`. The CLI in agent mode prints JSON "next
  steps", not a success line: confirm with `get_project` (latestDeployment READY) and by comparing the
  hashed entry script on the live URL with `.vercel/output/static/index.html`.
- The proxied path did not serve a stale build after a redeploy (entry hash matched within seconds).

## Previewing both together (added 27/09/2026, verified end to end)
The site's rewrite runs server-side, so it cannot reach the sibling's protected preview deployments.
Without touching protection settings, bundle the sibling into one preview build of the site:
1. Build the sibling for the path (`npm run build:play` -> `dist-play`).
2. Copy it into the site's `public/play/` for this build only (do not commit it; remove it after).
3. `vercel pull --yes --environment=preview`, then `GAME_ORIGIN=<sibling production alias> vercel build`
   (not `--prod`). Next's rewrites returned as an array are `afterFiles`, so the copied files in
   `public/play/` are served first (the new pages come from the preview itself), and anything not
   copied, such as `/play` itself, still falls through to the live sibling.
4. `vercel deploy --prebuilt` (a protected preview). Logged-in team members open it directly; the
   real pages carry no X-Frame-Options (only the login redirect does), so same-origin iframes work.
5. To check it headless: Vercel MCP `get_access_to_vercel_url` gives a 23-hour `_vercel_share` link;
   open it in Playwright (it sets the access cookie, and same-origin subresources and iframes load).
   The MCP `web_fetch_vercel_url` got a 200 for `/` but a 302 to the login for a static sub-path.
A script: build, copy, pull, build with the env, remove the copy (in a `trap`), deploy.

## Verification
Run the app's end-to-end tests against the real domain (a `PLAY_BASE_URL`-style switch in the
Playwright config that skips the webServer): pieces load, workers start, and no request fails or
escapes the path.

## Notes
- Tests: skill `playwright-webserver-skips-build-stale-bundle` (never reuse a server for a build test).
- Memory safety when running the site's `next dev` locally: skill `turbopack-home-lockfile-memory-runaway`.
