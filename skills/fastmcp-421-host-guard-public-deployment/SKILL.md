---
name: fastmcp-421-host-guard-public-deployment
description: |
  Fix for a FastMCP server on a public hostname (Fly.io, Cloud Run, any reverse
  proxy) rejecting every request with HTTP 421 "Misdirected Request" after a
  routine redeploy, surfacing in claude.ai as "Connection issue — Couldn't
  connect to the server. Check that the URL points to a valid MCP server" for a
  custom connector. Use when: (1) curl to ANY path on the server (including /)
  returns 421 with the 19-byte body "Misdirected Request", (2) the platform
  status looks healthy (machine started, deploy green) so it pattern-matches to
  a proxy/routing fault, (3) app access logs (fly logs) show uvicorn lines like
  'POST /mcp HTTP/1.1" 421 Misdirected Request' proving the APP emits the 421,
  (4) fastmcp was installed with an unpinned range (>=3.3,<4.0) and a rebuild
  pulled fastmcp >= 3.4, (5) claude.ai's OAuth discovery probes
  (/.well-known/oauth-protected-resource/mcp, /register) all 421. Root cause:
  fastmcp >= 3.4 ships HostOriginGuardMiddleware (DNS-rebinding protection,
  default ON) that only trusts localhost/127.0.0.1/::1; fix is
  FASTMCP_HTTP_ALLOWED_HOSTS. Also covers the sibling 403 "Forbidden Origin"
  failure (browser POST to the OAuth /consent form 403s because uvicorn behind
  a TLS-terminating proxy sees scheme http, so the same-origin check compares
  http:// vs https:// — fix: FORWARDED_ALLOW_IPS=* plus
  FASTMCP_HTTP_ALLOWED_ORIGINS) and the fly ssh console -C no-shell gotcha.
author: Claude Code
version: 1.1.0
date: 2026-07-10
---

# FastMCP 421 Host Guard on Public Deployments

## Problem

A FastMCP server deployed behind a public hostname suddenly rejects every HTTP
request with `421 Misdirected Request`. In claude.ai the custom connector shows
"Connection issue — Couldn't connect to the server. Check that the URL points
to a valid MCP server." The 421 is easy to misread as a platform routing fault
(Fly proxy, load balancer, TLS SNI mismatch) because it hits every path and the
deployment looks healthy.

## Context / Trigger Conditions

- `curl -s https://<app-host>/mcp` (and `/`) returns HTTP 421, body exactly
  `Misdirected Request` (19 bytes).
- Platform reports the app healthy: machine `started`, IPs allocated, DNS
  resolving, recent deploy green.
- App access logs show the app itself emitting the 421s, e.g. uvicorn lines:
  `INFO: 172.16.x.x:NNNN - "POST /mcp HTTP/1.1" 421 Misdirected Request`.
  This is the decisive check: a proxy-generated 421 never appears in the
  app's own access log.
- The image installs fastmcp with an open range (e.g. `"fastmcp>=3.3,<4.0"`)
  rather than a lockfile, and a rebuild silently crossed the 3.4 boundary.
- claude.ai's whole connection dance 421s in order: `POST /mcp`,
  `GET /.well-known/oauth-protected-resource/mcp`,
  `GET /.well-known/oauth-authorization-server`, `POST /register`.

## Root Cause

fastmcp >= 3.4 adds `HostOriginGuardMiddleware`
(`fastmcp/server/http.py`) — DNS-rebinding protection that is **enabled by
default** (`host_origin_protection=True` in `create_streamable_http_app`).
It validates the `Host` header against
`DEFAULT_HOSTS = ("127.0.0.1", "localhost", "::1")` plus any configured
`allowed_hosts`, and returns `Response("Misdirected Request", 421)` on
mismatch. The server's bind address is only appended if it is not unspecified,
so binding `0.0.0.0` adds nothing. A public hostname like `myapp.fly.dev`
therefore fails for every request, including OAuth discovery routes, which sit
behind the same middleware.

The setting plumbing (verified in fastmcp 3.4.3):
`FastMCP.http_app()` → `TransportMixin` falls back to
`fastmcp.settings.http_allowed_hosts` (`fastmcp/settings.py`, pydantic-settings
with `env_prefix="FASTMCP_"`) → passed to `HostOriginGuardMiddleware`.
Host patterns support `fnmatchcase` wildcards (`*.fly.dev` works; `*` disables
the check — do not use in production).

## Solution

1. **Confirm the app emits the 421** (not the platform): check the app's own
   access logs. On Fly: `fly logs -a <app> --no-tail | tail -30`.
2. **Confirm the deployed fastmcp version**:
   `fly ssh console -a <app> -C "python -c \"import importlib.metadata as im; print(im.version('fastmcp'))\""`
   Gotcha: `fly ssh console -C` does NOT run a shell — pipes, `;`, `&&` and
   multiple commands fail with confusing errors. Issue one plain command per
   call (grep accepts multiple file arguments if needed).
3. **Immediate fix without redeploy** (Fly): update the machine env in place —
   restarts the machine, keeps image and volume:
   ```bash
   fly machine update <machine-id> -a <app> \
     --env 'FASTMCP_HTTP_ALLOWED_HOSTS=["myapp.fly.dev"]' --yes
   ```
   The value is a JSON list (pydantic-settings parsing for `list[str]`).
4. **Persist in config** so the next deploy keeps it — `fly.toml`:
   ```toml
   [env]
     FASTMCP_HTTP_ALLOWED_HOSTS = '["myapp.fly.dev"]'
   ```
5. **Prevent recurrence**: pin fastmcp in the image to the version you tested
   (the root cause is an unpinned `uv pip install "fastmcp>=3.3,<4.0"` in the
   Dockerfile drifting past a behaviour change while the repo's `uv.lock` said
   otherwise). Alternatively pass `allowed_hosts=[...]` explicitly to
   `mcp.run(transport="streamable-http", ...)` / `http_app()` — but note that
   kwarg only exists from fastmcp 3.4, so the env var is safer across versions.

## Verification

- `curl -s -o /dev/null -w "%{http_code}" https://<host>/mcp` → **401** (with
  OAuth enabled) or a JSON-RPC/406 response — anything but 421 means the host
  guard passed.
- The 401 must carry
  `WWW-Authenticate: Bearer resource_metadata="https://<host>/.well-known/oauth-protected-resource/mcp"`.
- `curl https://<host>/.well-known/oauth-protected-resource/mcp` → **200** with
  resource metadata JSON.
- Reconnect the connector in claude.ai (it re-runs discovery; a session that
  cached the failure needs a fresh connect, and re-auth may be prompted).

## Sibling Failure: 403 "Forbidden Origin" on the OAuth consent POST

After fixing the 421, the OAuth flow can then fail at the consent screen: the
browser's `POST /consent?txn_id=...` returns **403 "Forbidden Origin"** (from
the same middleware, `_origin_allowed`). This is NOT a cross-origin request —
it is the guard mis-detecting the scheme:

- The middleware allows an origin if it is in `allowed_origins`, OR loopback,
  OR equal to `request_origin = f"{scope['scheme']}://{host}"`.
- Behind a TLS-terminating proxy (Fly edge, Cloud Run, nginx), uvicorn sees
  `scheme=http` unless it trusts `X-Forwarded-Proto`. Uvicorn's
  `proxy_headers=True` default only trusts `forwarded_allow_ips=127.0.0.1`,
  and Fly's proxy connects from a private `172.16.x.x` address — so the
  browser's `Origin: https://myapp.fly.dev` is compared against
  `http://myapp.fly.dev` and fails.

Fix (both, one machine update):

```bash
fly machine update <machine-id> -a <app> \
  --env 'FORWARDED_ALLOW_IPS=*' \
  --env 'FASTMCP_HTTP_ALLOWED_ORIGINS=["https://myapp.fly.dev"]' --yes
```

`FORWARDED_ALLOW_IPS=*` is read by uvicorn directly from the environment
(fastmcp passes nothing, so uvicorn's env fallback applies) and fixes scheme
detection at the root; the explicit origin allowlist is belt-and-braces.
Persist both in `fly.toml [env]`.

Verify: `curl -X POST https://<host>/mcp -H "Origin: https://<host>" -d '{}'`
→ 401 (guard passed), and with `-H "Origin: https://evil.example"` → 403
(guard still active). Note the machine restart voids any in-flight OAuth
transaction — restart the connector flow in claude.ai from the beginning.

## Notes
- The low-level MCP Python SDK has its own equivalent
  (`TransportSecuritySettings` in `mcp/server/transport_security.py`, also 421
  on bad Host). If the server uses the raw SDK rather than fastmcp, configure
  `allowed_hosts` there instead.
- Local development is unaffected (localhost is always allowed), which is why
  the breakage only shows up in deployed environments — local testing gives a
  false all-clear.
- Kill switch `FASTMCP_HTTP_HOST_ORIGIN_PROTECTION=false` exists but drops the
  DNS-rebinding protection entirely; prefer the allowlist.

## References

- [MCP Python SDK issue #1798 — Guide: Resolving "421 Invalid Host Header" (DNS rebinding protection)](https://github.com/modelcontextprotocol/python-sdk/issues/1798)
- [How an unbounded fastmcp version constraint took down production with 421 Misdirected Request](https://dev.to/toyama0919/how-an-unbounded-fastmcp-version-constraint-took-down-production-with-421-misdirected-request-1mh1)
- [GHSA-9h52-p55h-vw2f — DNS rebinding protection advisory for the MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-9h52-p55h-vw2f)
- [Deploying a FastMCP server to Google Cloud Run: fixing "Invalid Host Header" and 421 errors](https://medium.com/@egekasal/deploying-a-fastmcp-server-to-google-cloud-run-how-to-fix-the-invalid-host-header-and-421-errors-bbfc8d121e26)
