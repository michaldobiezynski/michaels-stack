---
name: fly-secrets-append-without-clobber
description: |
  Safely APPEND to (or edit) an existing Fly.io secret whose value is a list
  (comma-separated allowlist, multiple keys, etc.) without clobbering the
  current value. Use when: (1) you need to add an entry to a Fly secret like
  COUNCIL_ALLOWED_EMAILS / ALLOWED_ORIGINS / a CSV of API keys; (2) `fly secrets
  list` shows only NAME + DIGEST + STATUS (never the value), so you cannot read
  what is there to append to it; (3) you are about to run `fly secrets set
  NAME=...` and risk overwriting the whole list with just the new entries.
  Root cause: Fly secrets are write-only via the control plane (the API never
  returns plaintext), but the value IS present as an env var inside the running
  machine, so you can read it back over SSH, append, and write the full value.
author: Claude Code
version: 1.0.0
date: 2026-06-23
---

# Append to a Fly.io secret without clobbering it

## Problem

A Fly secret holds a list (e.g. `COUNCIL_ALLOWED_EMAILS="a@x.com,b@y.com"`). You
want to ADD an entry. But `fly secrets list -a <app>` only shows the name, a
digest, and status, never the value, and `fly secrets set NAME=value` REPLACES
the whole secret. Setting `NAME=newentry` would drop everyone already on the list.

## Key fact

Fly secrets are write-only through the control plane (the API never returns
plaintext), **but the value is injected as an environment variable into the
running machine**. So `fly ssh console` can read the current value back, even
though `fly secrets list` cannot.

## Solution (read live value, append, write back) — one atomic shell block

Do read + append + write in a SINGLE shell invocation (shell vars do not persist
across separate tool calls):

```bash
APP=<app-name>
NAME=COUNCIL_ALLOWED_EMAILS

# 1. Read the current value off the RUNNING machine (not from `fly secrets list`).
raw=$(fly ssh console -a "$APP" -C "printenv $NAME" 2>/dev/null)

# 2. Normalise + append in python (regex-filter so any SSH banner noise is dropped),
#    write the full new value to a temp file so it never lands in argv / `ps`.
python3 - "$raw" <<'PY'
import sys, re
raw = sys.argv[1] if len(sys.argv) > 1 else ""
items = []
for e in re.findall(r'[^@\s,]+@[^@\s,]+\.[^@\s,]+', raw.lower()):  # email regex; adapt per list type
    if e not in items: items.append(e)
if len(items) < 1:                      # GUARD: refuse to write if the read failed
    print("ABORT"); sys.exit(0)
for e in ["new1@x.com", "new2@y.com"]:  # entries to add
    if e not in items: items.append(e)
open("/tmp/_fly_secret_new","w").write(",".join(items))
print("OK count=%d" % len(items))
PY

# 3. Write the FULL value back via `fly secrets import` (reads NAME=VALUE from STDIN,
#    so the value is not exposed in the command line). This stages + deploys.
if [ -s /tmp/_fly_secret_new ]; then
  printf '%s=%s\n' "$NAME" "$(cat /tmp/_fly_secret_new)" | fly secrets import -a "$APP"
fi
rm -f /tmp/_fly_secret_new
```

## Verification

Re-read after the rolling restart completes (the `import`/`set` deploys synchronously,
so the machine is back up when it returns):

```bash
fly ssh console -a "$APP" -C "printenv $NAME"   # confirm new entries present, old kept
```

## Notes / gotchas

- **Always GUARD on a successful read.** If `fly ssh console` returns empty (machine
  asleep, SSH not provisioned, wrong var name), do NOT write, or you will clobber the
  secret to just the new entries. The `len < 1 -> ABORT` check above does this.
- Prefer `fly secrets import` (value via STDIN) over `fly secrets set NAME=value`
  (value in argv, visible in process listing / shell history).
- Both `set` and `import` trigger a release + rolling restart by default. Add `--stage`
  to defer the deploy if you are batching changes.
- `min_machines_running >= 1` in fly.toml means the machine is up to SSH into; if the
  app auto-stops, `fly ssh console` may need to wake it first.
- Privacy: when the list is third-party data (emails), normalise in-shell and report
  only counts / the entries you added, rather than echoing the whole list into logs.
- This generalises to any list-valued secret: CORS origins, comma-separated API keys,
  feature-flag lists, etc.
