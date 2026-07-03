---
name: council-of-thinkers-synthesis-share-url-404
description: |
  Diagnose 404 on a council-of-thinkers synthesis share URL
  (https://council-clip.vercel.app/synthesis/<id>) after a successful
  `mcp__council-of-thinkers__synthesise_council` call. Use when:
  (1) the MCP synthesise tool returned an `id` + `share_url` without
  error, (2) opening the share_url in a browser shows 404 / "not found",
  (3) other council MCP tools (query_council, query_speaker) still work.
  Root cause is almost always the Vercel frontend not being able to
  reach the LOCAL synthesis store: either the local HTTP read endpoint
  isn't up, OR cloudflared is running in ephemeral "quick mode"
  (`cloudflared tunnel --url ...`) instead of the named-tunnel mode the
  Vercel app expects. Covers the 4-step diagnostic: confirm record
  persisted locally, confirm local HTTP serves it, check cloudflared
  mode, then bridge or restart the named tunnel.
author: Claude Code
version: 1.0.0
date: 2026-05-24
---

# Council of Thinkers — synthesis share URL returns 404

## Problem

`mcp__council-of-thinkers__synthesise_council` returns a payload with
`share_url: https://council-clip.vercel.app/synthesis/<id>`, but loading
that URL in a browser shows 404. The synthesis tool didn't fail; the
public frontend can't fetch the record.

## Architecture (one-liner)

```
synthesise_council MCP call
  -> writes to local synthesis.db (SQLite)
  -> served by council_mcp.http_server on 127.0.0.1:8766 (or 8765)
  -> exposed to public internet by cloudflared tunnel (named, persistent hostname)
  -> council-clip.vercel.app frontend fetches /synthesis/<id> from that hostname
```

Defined in `council_mcp/http_server.py` and
`diagrams/section-08-tunnel.drawio`.

## Diagnostic flow

Run these four checks in order. Stop at the first that fails — that's
the broken link.

### 1. Record actually persisted?

```bash
sqlite3 ~/development/projects/council-of-thinkers/synthesis.db \
  "SELECT id, length(payload) FROM synthesis WHERE id='<id>';"
```

Empty row → the synthesis call didn't write. Re-run
`synthesise_council`. Otherwise continue.

### 2. Local HTTP endpoint serves it?

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8766/synthesis/<id>
```

- `200` → local read service is fine, problem is downstream (tunnel/Vercel).
- `404` → record didn't persist (back to step 1) OR the http_server is
  pointing at a different DB (check `SYNTHESIS_DB_PATH`).
- connection refused → http_server not running. Start it with
  `COUNCIL_TRANSPORT=http python -m council_mcp.server` (the unified
  runner, not the deprecated standalone `python -m council_mcp.http_server`).

### 3. cloudflared running in the RIGHT mode?

```bash
pgrep -fl cloudflared
```

Two outcomes matter:

- `cloudflared tunnel --url http://127.0.0.1:8766` — **WRONG MODE**.
  This is quick / ad-hoc mode. It mints a fresh random
  `*.trycloudflare.com` hostname on every start. The Vercel frontend's
  API base URL is pinned to a stable hostname, so the quick-tunnel URL
  is never consulted. **This is the most common silent cause of the
  404.**
- `cloudflared tunnel run council-of-thinkers` (or similar named-tunnel
  invocation) — correct mode.
- nothing — tunnel down entirely. Start the named tunnel (see step 4).
- `launchctl list | grep cloudflar` — if the launchd service is loaded
  it should be running the named tunnel automatically.

### 4. Bridge or restart the named tunnel

Two options:

**A. Use the existing named tunnel** (preferred — stable hostname,
matches Vercel config):

```bash
# kill any quick-mode cloudflared first to free port/credentials
pkill -f "cloudflared tunnel --url"

# foreground test first
cloudflared tunnel run council-of-thinkers

# then if you want it persistent, the launchd service should already be
# installed per the section-08-tunnel.drawio runbook. If not:
sudo launchctl load /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
```

The named tunnel routes `mcp.<yourdomain>.com` -> `127.0.0.1:8766`,
which is the hostname the Vercel frontend hits. Confirm with:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://mcp.<yourdomain>.com/synthesis/<id>
```

Should return `200`. Refresh the share URL.

**B. Bridge a quick-mode tunnel to Vercel** (only if you don't want to
touch launchd/DNS):

1. Read the `*.trycloudflare.com` URL from the running cloudflared's
   stdout (it's printed at startup; if it scrolled away, restart with
   `cloudflared tunnel --url http://127.0.0.1:8766 2>&1 | tee /tmp/cf.log`).
2. Set the Vercel app's API base env var (commonly
   `NEXT_PUBLIC_SYNTH_API` or similar — check the council-clip repo's
   `.env` schema) to that URL.
3. Redeploy or use Vercel's preview env override.

Option B is fragile because the quick-tunnel hostname rotates on every
restart. Use A for any non-throwaway use.

## Verification

After applying the fix, refresh `https://council-clip.vercel.app/synthesis/<id>`
in the browser. It should render the synthesis blocks + clip cards.

Also confirm CORS isn't the culprit (it usually isn't for this stack but
worth checking if you see the request go through in DevTools Network
tab but the page still shows "not found"):

```bash
curl -v -H "Origin: https://council-clip.vercel.app" \
  https://mcp.<yourdomain>.com/synthesis/<id> 2>&1 | grep -i "access-control"
```

The default allow-origin regex in `council_mcp/http_server.py:34` is
`^https://council-clip(-[a-z0-9-]+)?\.vercel\.app$` — preview
deployments with longer subdomains match this.

## Notes

- **Other MCP tools still working is the giveaway** that the MCP server
  itself is fine — only the read-side HTTP path or its public exposure
  is broken. `query_council` / `query_speaker` / `find_quote` don't go
  through the Vercel frontend at all; they return chunk metadata
  directly via the MCP protocol.
- The `share_url` host is constructed from `SYNTHESIS_BASE_URL` in
  `council_mcp/synthesise.py:31`, default
  `https://council-clip.vercel.app/synthesis`. Overriding that env var
  is a separate failure mode (the URL won't match the Vercel app at
  all); check it if step 3 looks correct but the URL host is wrong.
- Two ports exist in the codebase: `8766` (current unified runner) and
  `8765` (older standalone). Whichever is listening (`lsof -iTCP -sTCP:LISTEN`)
  is the right one to point cloudflared at.
- Don't proactively run `cloudflared service install`, edit DNS, or
  modify `~/.cloudflared/config.yml` without user authorisation — these
  touch shared infra.

## References

- Local: `council_mcp/http_server.py` (HTTP read service, CORS config)
- Local: `council_mcp/synthesise.py:31` (share_url construction)
- Local: `diagrams/section-08-tunnel.drawio` (named-tunnel setup runbook)
- [Cloudflare Tunnel — Named vs Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
