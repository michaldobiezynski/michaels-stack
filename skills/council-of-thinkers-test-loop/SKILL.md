---
name: council-of-thinkers-test-loop
description: |
  Bring the council-of-thinkers synthesis pipeline fully online for a test
  session: start the local synthesis http_server, start an ephemeral
  Cloudflare quick tunnel, push the tunnel URL into the council-clip
  Vercel project as SYNTHESIS_API_BASE_URL, redeploy council-clip, and
  verify the share_url renders end-to-end. Use when: (1) user wants to
  test synthesise_council in a fresh Claude Code window or after a
  reboot, (2) the council-clip.vercel.app/synthesis/<id> share link is
  404ing and you need to re-wire the local-to-Vercel chain, (3) the
  previous tunnel died (ephemeral cloudflared --url tunnels die on
  Ctrl-C and the URL is one-shot), (4) any "make the council pipeline
  testable" request. Covers process management for http_server +
  cloudflared, capturing the trycloudflare.com URL programmatically,
  Vercel env-var swap via CLI (rm then add, NOT just add), and the
  redeploy-required-after-env-change gotcha. ALWAYS does a clean slate
  (kills existing http_server + cloudflared first) so re-running is
  idempotent.
author: Claude Code
version: 1.0.0
date: 2026-05-22
---

# council-of-thinkers test loop

## Problem

The council-of-thinkers synthesis pipeline needs three independent
processes wired together before a `synthesise_council` share link renders:

1. `http_server.py` running on `127.0.0.1:8766` (serves SQLite-backed
   synthesis records as JSON)
2. A public HTTPS tunnel pointed at port 8766
3. The `council-clip` Vercel project's `SYNTHESIS_API_BASE_URL` env var
   set to the tunnel URL, and a redeploy fired after the env change

If any link breaks, the share URL 404s. Quick tunnels (`cloudflared --url`)
have ephemeral hostnames that change every restart, so every test session
needs steps 2 + 3 redone.

## Context / Trigger conditions

- User says "test synthesise_council", "verify the council pipeline",
  "is the share link working", "set up the council tunnel"
- `council-clip.vercel.app/synthesis/<id>` returns 404 after a successful
  `synthesise_council` MCP call
- A new Claude Code window is open and the user wants to test
- Previous `cloudflared` process died (Ctrl-C, reboot, terminal closed)
- `~/.cloudflared/` does NOT contain `cert.pem` (user has not set up the
  named-tunnel flow); fall through to quick tunnels

## Pre-flight check

Run these in parallel; they tell you what state to start from:

```bash
pgrep -fl "council_mcp.http_server" || echo "http_server: not running"
pgrep -fl "cloudflared tunnel" || echo "cloudflared: not running"
ls /Users/michaldobiezynski/development/projects/council-clip/.vercel/project.json
which vercel cloudflared
```

If any of `vercel`, `cloudflared`, or the linked council-clip project is
missing, STOP and report. Don't try to install or relink without asking.

## Solution: the 7-step loop

### 1. Clean slate (idempotent: safe to run if nothing is running)

```bash
pkill -f "council_mcp.http_server" 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 1
```

### 2. Start the synthesis HTTP server in background

```bash
cd /Users/michaldobiezynski/development/projects/council-of-thinkers
nohup uv run python -m council_mcp.http_server > /tmp/council-http.log 2>&1 &
sleep 2
```

Verify:

```bash
curl -s http://127.0.0.1:8766/synthesis/__ping__ | head -c 100
# Expect either {"error":"not_found"} or {"detail":"Not Found"} — server is up
```

If it doesn't respond, tail `/tmp/council-http.log` to find the error.
Most common: wrong cwd (must be repo root), missing `.env`, or port 8766
already taken.

### 3. Start the Cloudflare quick tunnel in background

```bash
cloudflared tunnel --url http://127.0.0.1:8766 > /tmp/cf-tunnel.log 2>&1 &
# Poll for the URL with a hard cap; 30s is plenty
for i in {1..30}; do
  TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cf-tunnel.log | head -1)
  [ -n "$TUNNEL_URL" ] && break
  sleep 1
done
echo "tunnel = $TUNNEL_URL"
[ -z "$TUNNEL_URL" ] && { echo "FAILED: no trycloudflare URL"; tail -20 /tmp/cf-tunnel.log; exit 1; }
```

### 4. Verify the tunnel reaches the local server

```bash
curl -s "$TUNNEL_URL/synthesis/__ping__" -o /dev/null -w "%{http_code}\n"
# Expect 404 (route works, record not found). A non-200/404 means
# cloudflared booted but isn't routing yet; wait 5s and retry.
```

If you see `000` (connection failed) wait 5-10s and retry; tunnels take a
moment to propagate after `--url` returns.

### 5. Swap the Vercel env var

Vercel CLI's `env add` errors if the key already exists, so use rm-then-add.
NOTE: trailing slash on the URL produces `https://foo//synthesis/X` (double
slash) and may 404. The `vercel env add` flow stores the value verbatim.

```bash
cd /Users/michaldobiezynski/development/projects/council-clip
vercel env rm SYNTHESIS_API_BASE_URL production --yes 2>/dev/null
printf "%s" "$TUNNEL_URL" | vercel env add SYNTHESIS_API_BASE_URL production
```

`printf "%s"` (NOT `echo`) is critical: `echo` appends a newline that gets
stored as part of the value and breaks the URL.

Optional: also set Preview if you test preview URLs.

```bash
printf "%s" "$TUNNEL_URL" | vercel env add SYNTHESIS_API_BASE_URL preview
```

NOTE: if the previous env entry was scoped "Production, Preview" (single
combined row), `vercel env rm ... production` removes the WHOLE entry, not
just the Production scope. So a subsequent `vercel env rm ... preview`
will return `env_not_found`. That's expected; just `add` for preview if
you need it. The `add` step for Preview may also prompt interactively
for a git-branch scope; pipe `echo ""` in front if you want all branches.

### 6. Redeploy with fresh env baked in

Server-side env vars on Vercel only apply to deployments BUILT AFTER the
env was set. Just clicking "Redeploy" with cached build won't pick up the
new value.

```bash
cd /Users/michaldobiezynski/development/projects/council-clip
vercel --prod --yes
# Capture the deployment URL from stdout — last line is the alias URL
```

Wait until the deployment shows as Ready (the CLI blocks until then).

### 7. End-to-end verification

```bash
# Pick any synthesis id from the local DB
LATEST_ID=$(sqlite3 /Users/michaldobiezynski/development/projects/council-of-thinkers/synthesis.db \
  "SELECT id FROM synthesis ORDER BY rowid DESC LIMIT 1;")
echo "share URL: https://council-clip.vercel.app/synthesis/$LATEST_ID"

# Smoke: tunnel layer
curl -s "$TUNNEL_URL/synthesis/$LATEST_ID" | head -c 200

# Smoke: full chain through Vercel SSR
curl -s "https://council-clip.vercel.app/synthesis/$LATEST_ID" -o /tmp/page.html -w "%{http_code}\n"
grep -c "synthesis" /tmp/page.html
# Expect: 200 status, multiple matches for "synthesis" in the HTML
```

If the page renders but says "Not Found" inside the HTML, Vercel function
log will show whether `fetchSynthesis` is hitting the tunnel or short-
circuiting on a null env. Check via dashboard or:

```bash
vercel logs --since 5m
```

## Verification

The loop is fully working when ALL of these hold:

- `curl http://127.0.0.1:8766/synthesis/<id>` returns full JSON
- `curl $TUNNEL_URL/synthesis/<id>` returns same JSON
- Visiting `council-clip.vercel.app/synthesis/<id>` in a browser shows
  the synthesis (not a 404)
- `total_cost_usd` line appears in `/tmp/council-http.log` after each
  `synthesise_council` call

## Teardown

When you're done testing, free the ports and stop billing the tunnel:

```bash
pkill -f "council_mcp.http_server"
pkill -f "cloudflared tunnel"
```

Optional: leave the Vercel env var set; it'll point at a dead tunnel URL
until the next test loop re-runs.

## Notes

- **Tunnel URL is ephemeral**: `cloudflared --url` generates a fresh
  random `*.trycloudflare.com` hostname every time. The Vercel env var
  MUST be updated each session. If you want a stable hostname, switch to
  the named-tunnel flow (`cloudflared tunnel login` + `tunnel create` +
  DNS routing on a Cloudflare-managed zone).
- **`vercel env add` won't overwrite**: it errors with "Environment
  variable was already added". Always `vercel env rm` first.
- **`printf "%s"` instead of `echo`**: `echo` adds a trailing newline
  that becomes part of the stored value and breaks `${base}/synthesis/<id>`
  URL composition.
- **Production scope only**: setting the env on Preview alone is
  insufficient; `council-clip.vercel.app` is the production alias. Set
  Production. Set Preview ALSO if you test preview URLs.
- **`vercel --prod --yes` blocks until Ready**: no need to add manual
  waiting loops; the CLI returns once the deployment is promoted.
- **Costs nothing on the Vercel side**: redeploy on the Hobby tier is
  free as long as you stay under the build-minute cap (you're nowhere
  near it for this project).
- **Cost per test loop**: $0 for the tunnel + Vercel deploy. Per
  `synthesise_council` call, ~$0.06 of claude.ai subscription credit
  (Pattern 2). Plan accordingly if running many iterations.
- **Idempotency**: running this skill twice in a row is safe; the clean-
  slate step in §1 makes it a true reset.
- **Don't add `NEXT_PUBLIC_` prefix**: `SYNTHESIS_API_BASE_URL` is
  server-only by design. The `lib/synthesisFetch.ts` module is gated
  by `import "server-only"`. Adding the public prefix would leak the
  tunnel URL to the browser and expose your laptop's synthesis records
  to anyone.
- **Server-only import gotcha in tests**: if you run council-clip's
  vitest suite after this, you may need the `vitest.config.ts` alias
  for `server-only` already in place. See related skill
  [nextjs-server-only-vitest-alias-stub].

## When this skill DOES NOT apply

- Named persistent tunnel users (`~/.cloudflared/cert.pem` exists +
  config.yml points at a stable hostname). Those folks just need
  `cloudflared tunnel run <name>`; the Vercel env never changes.
- Production deployment of council-of-thinkers as a service (this is a
  personal-laptop loop; running synthesise_council on someone else's
  laptop won't help).
- Pre-PR-#7 stub-synthesis era (model field was "stub-v1", no actual
  LLM call). If `synthesis.db` rows all say `model = stub-v1`, the LLM
  wiring isn't in place; see the claude-p-subscription-subprocess skill.

## Example: complete loop from a cold start

```bash
#!/bin/bash
# council-test-loop.sh — paste-ready

set -e
PROJECT=/Users/michaldobiezynski/development/projects/council-of-thinkers
CLIP=/Users/michaldobiezynski/development/projects/council-clip

# 1. clean slate
pkill -f "council_mcp.http_server" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1

# 2. http_server
cd "$PROJECT"
nohup uv run python -m council_mcp.http_server > /tmp/council-http.log 2>&1 &
sleep 2

# 3. tunnel + capture URL
cloudflared tunnel --url http://127.0.0.1:8766 > /tmp/cf-tunnel.log 2>&1 &
for i in {1..30}; do
  TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cf-tunnel.log | head -1)
  [ -n "$TUNNEL_URL" ] && break
  sleep 1
done
[ -z "$TUNNEL_URL" ] && { echo "no tunnel URL"; exit 1; }
echo "tunnel: $TUNNEL_URL"

# 4. wait for tunnel to actually route
for i in {1..10}; do
  code=$(curl -s "$TUNNEL_URL/synthesis/__ping__" -o /dev/null -w "%{http_code}")
  [ "$code" = "404" ] && break
  sleep 2
done

# 5. swap Vercel env
cd "$CLIP"
vercel env rm SYNTHESIS_API_BASE_URL production --yes 2>/dev/null || true
printf "%s" "$TUNNEL_URL" | vercel env add SYNTHESIS_API_BASE_URL production

# 6. redeploy
vercel --prod --yes

# 7. confirm
LATEST_ID=$(sqlite3 "$PROJECT/synthesis.db" "SELECT id FROM synthesis ORDER BY rowid DESC LIMIT 1;")
echo "share URL: https://council-clip.vercel.app/synthesis/$LATEST_ID"
echo "open it; should render"
```

## References

- council-of-thinkers PR #7: https://github.com/michaldobiezynski/council-of-thinkers/pull/7
- council-clip fetchSynthesis: `lib/synthesisFetch.ts` (checks
  `process.env.SYNTHESIS_API_BASE_URL`; returns null if unset)
- Vercel CLI env docs: https://vercel.com/docs/cli/env
- Cloudflare quick tunnels: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/
- Related skill: claude-p-subscription-subprocess (the LLM call mechanics
  behind synthesise_council)
