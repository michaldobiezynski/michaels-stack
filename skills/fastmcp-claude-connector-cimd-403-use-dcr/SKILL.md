---
name: fastmcp-claude-connector-cimd-403-use-dcr
description: |
  Connecting Claude Code / claude.ai to a self-hosted FastMCP OAuth server
  (e.g. GoogleProvider) fails on the server's consent page with "Client Not
  Registered — the client ID https://claude.ai/oauth/claude-code-client-metadata
  was not found in the server's client registry". Use when: (1) a remote MCP
  connector OAuth flow dies at /authorize with that message and the client_id
  shown is a claude.ai URL, (2) server logs show "CIMD fetch failed ... HTTP 403
  fetching https://claude.ai/oauth/..." (FastMCP cimd.py), (3) you host a
  FastMCP server on a datacenter box (Fly.io/Render/VPS) and Claude won't
  connect, (4) the connector "worked then broke after a restart/redeploy".
  Root cause: Claude uses CIMD (client-id-as-URL) and the server must fetch
  that URL, but claude.ai/Cloudflare returns 403 to server-side datacenter
  fetches (UA-independent). Fix: disable CIMD so Claude falls back to Dynamic
  Client Registration, and put OAuthProxy client_storage on a persistent volume.
author: Claude Code
version: 1.0.0
date: 2026-06-20
---

# FastMCP Claude connector: CIMD fetch 403 → disable CIMD, use DCR (+ persist storage)

## Problem

You stand up a self-hosted MCP server on FastMCP with OAuth (commonly
`GoogleProvider`, which wraps `OAuthProxy`) and try to add it as a remote
connector from **Claude Code** (`claude mcp add --transport http <name> <url>`)
or **claude.ai** (custom connector). The browser OAuth step fails on the
**server's own** page:

> **Client Not Registered.** The client ID
> `https://claude.ai/oauth/claude-code-client-metadata` was not found in the
> server's client registry. ... your client should automatically re-register.

Clearing tokens and retrying does **not** help — it fails the same way every
time.

## Context / Trigger conditions

- The client_id in the error is a **claude.ai URL**, not an opaque string.
- Server logs (FastMCP) show, at the moment of the failed `/authorize`:
  ```
  httpx GET https://[...]/oauth/claude-code-client-metadata "HTTP/1.1 403 Forbidden"
  WARNING  CIMD fetch failed for https://claude.ai/oauth/claude-code-client-metadata: HTTP 403 fetching ...   (cimd.py)
  INFO     Unregistered client_id=https://claude.ai/oauth/claude-code-client-metadata, returned HTML error response   (authorize.py)
  GET /authorize?...client_id=https%3A%2F%2Fclaude.ai%2Foauth%2F... 400 Bad Request
  ```
- The server is hosted on a datacenter box (Fly.io, Render, a VPS, etc.).

## Root cause

Claude Code/claude.ai default to **CIMD** (Client ID Metadata Document, MCP
SEP-991): instead of registering, the client's `client_id` *is* an HTTPS URL
(`https://claude.ai/oauth/claude-code-client-metadata`) pointing at a JSON
metadata document. A CIMD-aware server must **fetch that URL server-side** to
learn the client, then admit it.

FastMCP supports CIMD and enables it by default, so it tries the fetch — but
**claude.ai (Cloudflare) returns HTTP 403 to the server-to-server fetch from a
datacenter IP**. This is not an egress problem (you get a 403 HTTP response,
not a timeout) and is **not fixed by spoofing a browser User-Agent** (still
403). FastMCP swallows the failed fetch and returns `None` from
`OAuthProxy.get_client()`, which renders the "Client Not Registered" page. So
CIMD can never resolve from a self-hosted datacenter box against claude.ai.

(Distinct, secondary failure with the same error text: a **restart wiping the
client registry** — see persistence fix below. If the error client_id is an
*opaque* string rather than the claude.ai URL, that's the cause instead.)

## Solution

Make Claude fall back to **Dynamic Client Registration (DCR)** — the original
MCP connector flow — which registers the client directly via `/register` and
needs **no** outbound fetch from the server. In FastMCP, disable CIMD on the
provider:

```python
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.stores.filetree import FileTreeStore  # already a fastmcp dep
from pathlib import Path

storage_dir = Path("/data/oauth-proxy")          # a PERSISTENT volume path
storage_dir.mkdir(parents=True, exist_ok=True)

provider = GoogleProvider(
    client_id=..., client_secret=..., base_url="https://your-host",
    required_scopes=["openid", "email"],
    enable_cimd=False,                            # <-- forces DCR; no claude.ai fetch
    client_storage=FileTreeStore(data_directory=storage_dir),  # <-- survives restarts
)
```

Two parts, both needed for a durable fix:

1. **`enable_cimd=False`** — stops the server advertising
   `client_id_metadata_document_supported`, so Claude uses DCR. DCR client_ids
   are opaque (filename-safe), which also sidesteps FastMCP's FileTreeStore
   URL-as-path bug (#3574). This is the actual unblock.
2. **Persistent `client_storage`** — FastMCP's default `OAuthProxy` storage is
   a `FileTreeStore` under `user_data_dir('fastmcp')` on the container's
   **ephemeral root filesystem**, so every restart/redeploy wipes the DCR
   registry and logins break again (this time with an *opaque* client_id).
   Point `client_storage` at a mounted persistent volume. Leave
   `jwt_signing_key` default — it's derived from the OAuth client secret and is
   already stable across restarts, so issued tokens stay valid; only the
   *storage location* needed fixing.

After deploying the fix, the client must clear its cached (broken CIMD) state:

```bash
claude mcp remove <name>
claude mcp add --transport http <name> https://your-host/mcp
# then in Claude Code: /mcp  → Google login
```

## Verification

- The OAuth discovery doc no longer advertises CIMD and exposes DCR:
  ```bash
  curl -s https://your-host/.well-known/oauth-authorization-server \
    | python3 -c "import sys,json; d=json.load(sys.stdin); \
      print('cimd=', d.get('client_id_metadata_document_supported')); \
      print('register=', d.get('registration_endpoint'))"
  # expect: cimd= None    register= https://your-host/register
  ```
- The persistent store dir is created and populated after a successful connect
  (`ls /data/oauth-proxy`).
- Re-running the connect succeeds: Google consent, then tools listed.

## Notes

- Confirm which failure you have by reading the **client_id in the error**:
  a claude.ai **URL** ⇒ CIMD-fetch 403 (this skill); an **opaque** id ⇒
  registry wiped by a restart (the persistence half alone).
- The claude.ai 403 was reproduced directly from the host with both a default
  and a browser User-Agent, so don't waste time on UA spoofing or egress
  debugging — it's a deliberate Cloudflare block of the metadata-doc fetch.
- DCR is a fully official MCP OAuth flow (predates CIMD); disabling CIMD is a
  legitimate, not a hacky, fix for self-hosted servers.
- Verified to fix BOTH connector surfaces from one server-side change: Claude
  Code (`claude mcp add --transport http`) and the claude.ai browser custom
  connector both fall back to DCR and connect (the known FastMCP GoogleProvider
  scope quirks #1794/#2401 did not block either). You do not need a separate
  fix per client.
- `client_storage` is unencrypted on disk unless you wrap it (FastMCP's default
  wraps `FileTreeStore` in `FernetEncryptionWrapper`). On a single-tenant,
  encrypted-at-rest volume this is usually acceptable; layer Fernet if the
  threat model needs it.
- Verified on FastMCP 3.3.1; `enable_cimd` / `client_storage` are constructor
  params on both `OAuthProxy` and `GoogleProvider`.

## References

- FastMCP OAuth Proxy (client_storage, enable_cimd, Linux ephemeral default): https://gofastmcp.com/servers/auth/oauth-proxy
- FastMCP CIMD docs: https://gofastmcp.com/clients/auth/cimd
- FastMCP HTTP deployment (jwt_signing_key + client_storage for production): https://gofastmcp.com/deployment/http
- FastMCP issues: #3398 ("Client Not Registered" for CIMD URL), #3574 (FileTreeStore URL-as-path), #1794/#2401 (GoogleProvider + Claude connector scope/consent)
