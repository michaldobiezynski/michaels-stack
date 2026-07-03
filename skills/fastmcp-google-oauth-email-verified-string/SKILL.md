---
name: fastmcp-google-oauth-email-verified-string
description: |
  Security gotcha when adding a per-user email allowlist on top of FastMCP's
  GoogleProvider OAuth for an MCP server. Use when: (1) writing an allowlist /
  authorisation check that reads the `email_verified` claim from a FastMCP
  GoogleProvider AccessToken, (2) gating MCP connector access by Google
  identity, (3) a guard like `if not claims.get("email_verified"): deny`
  reviews as correct but an unverified Google account still gets in, (4) you
  wrote `email_allowed`/`is_authorized` style logic against Google OAuth
  claims. Root cause: Google's v3 tokeninfo endpoint serialises booleans as
  STRINGS, so `email_verified` can be the string "false", which is truthy in
  Python and fails OPEN. Also covers the seam for enforcing the allowlist
  (wrapping GoogleProvider's private `_token_validator.verify_token`).
author: Claude Code
version: 1.0.0
date: 2026-06-19
---

# FastMCP GoogleProvider: `email_verified` is a string, not a bool (fails open)

## Problem

You add a per-user email allowlist on top of FastMCP's `GoogleProvider`
(Google OAuth) so only invited people can use your MCP server. The natural
guard reads the verified flag from the token claims:

```python
if not claims.get("email_verified"):
    return False  # deny unverified
```

This **fails open**: an unverified Google address can be admitted, silently
violating the "only verified identities" guarantee. Reviewers (and the author)
typically read this line as obviously correct, which is what makes it
dangerous.

## Context / Trigger Conditions

- You are building an MCP server with `fastmcp` and `GoogleProvider`
  (`fastmcp.server.auth.providers.google`) and enforcing an email allowlist.
- Your authorisation function inspects `AccessToken.claims["email_verified"]`.
- Symptom: a test/real Google account whose email is **not** verified
  (or whose `email_verified` is false) still passes the gate when its email
  string matches an allow-listed entry.
- A unit test that feeds the Python bool `False` passes (denies correctly),
  so the gap hides unless you specifically test the string `"false"`.

## Root cause

FastMCP's `GoogleTokenVerifier` builds the token claims from Google's
**v3 tokeninfo** endpoint (`https://oauth2.googleapis.com/tokeninfo`). That
endpoint serialises JSON booleans as **strings**, so `email_verified` arrives
as the string `"true"` or `"false"` (the userinfo endpoint, by contrast,
returns a real JSON boolean named `verified_email`). FastMCP stores
`token_data.get("email_verified") or user_data.get("verified_email")` in
`claims`.

In Python, a **non-empty string is truthy**, so `"false"` is truthy:

```python
bool("false")            # True  <-- the trap
not {"email_verified": "false"}.get("email_verified")  # False -> does NOT deny
```

Because the tokeninfo string `"false"` is truthy, the `or` also
short-circuits and never consults the userinfo boolean fallback.

## Solution

Normalise the claim before testing it. Treat only genuine affirmatives as
verified — never rely on raw truthiness:

```python
def _is_verified(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    if isinstance(value, int):
        return value == 1
    return False

# in the allowlist check:
if not _is_verified(claims.get("email_verified")):
    return False
```

The allowlist itself is best enforced by wrapping the verifier's
`verify_token` (return `None` to deny -> clean 401, no tool runs). FastMCP's
`GoogleProvider` wraps an `OAuthProxy` whose verifier lives at the **private**
attribute `provider._token_validator`, and FastMCP calls
`_token_validator.verify_token(...)` on every request:

```python
provider = GoogleProvider(client_id=..., client_secret=..., base_url=...,
                          required_scopes=["openid", "email"])
verifier = getattr(provider, "_token_validator", None)
if verifier is None:                      # guard: refuse to start, never serve ungated
    raise RuntimeError("FastMCP renamed _token_validator; allowlist cannot be enforced")
original = verifier.verify_token
async def _verify(token):
    validated = await original(token)
    if validated is None or not email_allowed(validated.claims, allowed):
        return None
    return validated
verifier.verify_token = _verify
```

Because `_token_validator` is private and FastMCP is pinned `>=3.3,<4.0`
(it can rename within that range without a major bump), guard with `hasattr`
and **fail closed** (raise at startup) rather than silently serving
unauthenticated.

## Verification

Add a regression test that feeds the **string** `"false"` and asserts denial
(a bool-only test will not catch the bug):

```python
assert email_allowed({"email": "a@x.com", "email_verified": "false"},
                     frozenset({"a@x.com"})) is False   # was True before the fix
assert email_allowed({"email": "a@x.com", "email_verified": "true"},
                     frozenset({"a@x.com"})) is True
```

Reproduced live in a venv before the fix: the `"false"` case returned `True`
(admitted) while the Python `False` case returned `False`.

## Notes

- **Exploitability**: matching is usually exact (`email in allowed`), so the
  attacker needs an unverified Google account whose email string exactly
  matches an allow-listed address. For `@gmail.com` this is effectively
  impossible (Google owns the namespace). The realistic exposure is Google
  Workspace / custom-domain accounts, where an admin-set primary or alias can
  legitimately be unverified and a small-group allowlist often contains such
  work addresses. Treat as medium severity, not theoretical.
- The same string-boolean trap applies to any Google OAuth claim consumed as
  a bool (`hd`, custom claims) and to other providers that proxy tokeninfo.
- An empty allowlist should **deny all**, not allow all: an OAuth server with
  no allowlist admits any Google account.
- For an MCP **enable** flag, an unrecognised value should fail **closed**
  (raise) rather than silently disabling auth — "no auth" is not a safe
  default for a security gate.

## References

- Google sign-in / verifying user info (shows tokeninfo `email_verified` as a
  quoted string `"true"` vs userinfo boolean): https://www.oauth.com/oauth2-servers/signing-in-with-google/verifying-the-user-info/
- FastMCP Google integration: https://gofastmcp.com/integrations/google
- FastMCP OAuth Proxy (the `_token_validator` / verify_token seam): https://gofastmcp.com/servers/auth/oauth-proxy
- FastMCP GoogleProvider + Claude connector scope quirks (test the handshake
  live): FastMCP issues #1794, #2401.
