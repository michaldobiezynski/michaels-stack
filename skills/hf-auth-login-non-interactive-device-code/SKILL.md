---
name: hf-auth-login-non-interactive-device-code
description: |
  Explains why `hf auth login` (Hugging Face CLI, formerly `huggingface-cli`) fails with
  exit 1 and "Login failed: Device code expired (timeout)" while `hf auth whoami` still
  shows a valid logged-in user. Use when: (1) `hf auth login` run via Claude Code's `!`
  prefix, a backgrounded command, CI, or any non-TTY context prints "open
  https://hf.co/oauth/device and enter the code XXXX-XXXX" then times out after 300s,
  (2) a user believes they logged in but the command exited 1, (3) you need to tell whether
  the active HF credential is an OAuth token vs a fine-grained write PAT, (4) a challenge/
  workflow needs a WRITE-scoped token but the stored one came from the browser device flow.
  Covers: non-TTY -> device-code fallback, "failed" != "logged out", and verifying token
  type via the whoami-v2 API.
author: Claude Code
version: 1.0.0
date: 2026-07-21
---

# `hf auth login` device-code timeout in non-interactive contexts

## Problem
`hf auth login` exits 1 with:
```
Ask the user to open https://hf.co/oauth/device in a browser and enter the code XXXX-XXXX.
The code expires in 300 seconds. Waiting for authorization...
Error: Login failed: Device code expired (timeout). Please try again.
```
yet `hf auth whoami` returns a valid `user=... orgs=...`. The "failure" looks like the user
is not logged in, but they are — from a *different* credential.

## Context / Trigger Conditions
- `hf auth login` was launched **without an interactive terminal**: Claude Code's `!`
  prefix (which backgrounds the command), a `run_in_background` Bash call, CI, or any
  subprocess with no TTY on stdin.
- The command printed a `hf.co/oauth/device` URL + short code and waited 300s.
- The user thought they "logged in" but never opened that URL, so it expired -> exit 1.
- `hf` is the current CLI name (Homebrew formula `hf`, v1.24+; the old name is
  `huggingface-cli`, same `huggingface_hub` package).

## Root cause
With a normal TTY, `hf auth login` prompts you to **paste a token** (hidden input). With no
TTY it cannot prompt, so it silently falls back to the **OAuth device-code flow**: print a
URL + code, poll for ~300s, fail if nobody authorises. Two consequences people miss:

1. **"Login failed" does NOT mean logged out.** A pre-existing token in
   `~/.cache/huggingface/token` (or `HF_TOKEN` env) is untouched by the failed attempt, so
   `whoami` keeps working. Don't tell the user to "log in again" without checking `whoami`.
2. **If the device flow DID succeed, you get an OAuth token, not a PAT.** OAuth tokens show
   `auth.type: oauth` with a ~30-day `expiresAt`, and carry the CLI OAuth app's scopes —
   NOT the fine-grained, explicitly write-scoped, revocable personal access token that many
   guides (and this challenge) ask you to create at huggingface.co/settings/tokens.

## Solution
1. **First check whether you are actually authenticated** — ignore the exit code:
   ```bash
   hf auth whoami        # user=... orgs=...  => you ARE logged in
   ```
2. **Identify the credential TYPE** (read vs write vs oauth) via the API, printing only the
   type, never the token:
   ```bash
   TOKEN="$(tr -d '[:space:]' < "$HOME/.cache/huggingface/token")"   # or $HF_TOKEN
   curl -s https://huggingface.co/api/whoami-v2 -H "Authorization: Bearer $TOKEN" \
     | python3 -c "import sys,json;d=json.load(sys.stdin);a=d.get('auth',{});print('type:',a.get('type'));print('expiresAt:',a.get('expiresAt'));at=a.get('accessToken');print('role:', at.get('role') if isinstance(at,dict) else None)"
   ```
   - `auth.type: oauth` -> browser device-flow token (~30-day expiry, no explicit role).
   - `auth.type: access_token` with `accessToken.role` in `read`/`write`/`fineGrained` ->
     a personal access token; check the role/scope for write access.
3. **To force the token-paste flow (get a specific write PAT):** run `hf auth login` in a
   REAL interactive terminal (the user's own Terminal app, not Claude Code's `!`), and paste
   a fine-grained **write** token when prompted. Alternatives: `export HF_TOKEN=hf_xxx`
   (session-scoped), or `hf auth login --token hf_xxx` (AVOID — leaks the token into shell
   history).

## Verification
- `hf auth whoami` prints the user and orgs -> authenticated regardless of the earlier
  exit 1.
- The whoami-v2 `auth.type` tells you oauth vs PAT; for a PAT, `accessToken.role` tells you
  read vs write.

## Example
A user ran `! hf auth login`, saw it exit 1 ("Device code expired"), but said "I've logged
in". `hf auth whoami` returned `user=michaldobiezynski orgs=...,ICML-2026-agent-repro`, and
whoami-v2 showed `auth.type: oauth, expiresAt: 2026-08-20`. Conclusion: authenticated via a
pre-existing OAuth token; the backgrounded login was a redundant device-flow attempt that
timed out. Caveat surfaced to the user: the active token is OAuth, not the fine-grained
write PAT their task needed for publishing — swap it in via an interactive terminal when the
write step arrives.

## Notes
- Never put a token on the command line or echo it; read from the token file / env and send
  it only to the official `huggingface.co/api` endpoint.
- The `!`-prefix / background-command TTY limitation is general: any CLI whose login prompts
  for hidden input (many `* auth login` commands) may behave differently when backgrounded.
  For interactive logins, direct the user to run the command in their own terminal.

## References
- HF CLI auth docs: https://huggingface.co/docs/huggingface_hub/guides/cli
- Related skill: `feature-review-verify-phase-auth-expiry` (another "auth-related failure
  that isn't what it looks like" case).
