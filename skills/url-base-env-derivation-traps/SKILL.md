---
name: url-base-env-derivation-traps
description: |
  Two linked traps when centralising or env-deriving a front-end/base URL origin in
  Python. Use when: (1) deriving an app ORIGIN from a configured base URL with
  urllib.parse.urlsplit/urlunsplit and getting an empty string or a path-only
  relative URL (e.g. "/clip" or "/guest/x") for a scheme-less env value like
  "host.com/synthesis"; (2) converting a HARDCODED url-base module constant (e.g.
  CLIP_BASE_URL = "https://prod.com/clip") into one derived from an env var, and
  suddenly pre-existing tests that hardcoded the production domain FAIL with a
  localhost (or other) host because the dev shell exports that env var
  (SYNTHESIS_BASE_URL=http://localhost:3000/...); (3) writing the replacement
  assertion and being tempted to assert startswith(THE_SAME_MODULE_CONSTANT), which
  is circular/vacuous. Covers the urlsplit empty-origin guard and how to write
  non-circular, non-vacuous URL tests.
author: Claude Code
version: 1.0.0
date: 2026-06-23
---

# URL base env-derivation traps

## Problem

When you centralise URL building so every surface (clip page, collection routes,
share links) hangs off ONE configurable origin, two non-obvious things bite you:

1. **`urlsplit`/`urlunsplit` silently yield an EMPTY origin for a scheme-less input.**
   Deriving an origin via `urlunsplit((parts.scheme, parts.netloc, "", "", ""))` returns
   `""` when the input had no scheme, because the host lands in `path`, not `netloc`.
   Downstream you then emit path-only relative URLs (`"/clip?v=..."`, `"/guest/x"`) that
   are not resolvable as standalone links - and nothing raises.

2. **Making a hardcoded URL-base constant env-derived breaks domain-hardcoded tests.**
   The dev shell commonly EXPORTS the driving env var (e.g.
   `SYNTHESIS_BASE_URL=http://localhost:3000/synthesis` for local dev). The moment the
   constant reads that env at import time, every pre-existing test that asserted the old
   hardcoded production domain (`"https://prod.com/clip" in url`) fails with `localhost`.
   The failures look like a regression but are actually the feature working.

## Context / Trigger conditions

- `urlsplit("host.com/path")` -> `scheme=''`, `netloc=''`, `path='host.com/path'`; then
  `urlunsplit(('', '', '', '', ''))` -> `''`.
- A module constant changed from `X = "https://prod/clip"` to
  `X = f"{app_origin()}/clip"` where `app_origin()` reads `os.getenv(...)` at import.
- Tests fail with the WRONG host (often `localhost`) even though the new behaviour is
  correct; running the test file alone still fails (rules out cross-test env leakage).
- `echo $SYNTHESIS_BASE_URL` (or whatever drives it) shows a non-default value exported
  by `.zshrc`/dev tooling.

## Solution

### Trap 1 - guard the origin derivation

Validate the resolved base has BOTH a scheme and a netloc; if not, degrade to a known
canonical default rather than emit a relative URL.

```python
from urllib.parse import urlsplit, urlunsplit
import logging, os

CANONICAL = "https://prod.example.com"
DEFAULT_BASE = f"{CANONICAL}/synthesis"

def base() -> str:
    val = os.getenv("BASE_URL", DEFAULT_BASE)
    parts = urlsplit(val)
    if not parts.scheme or not parts.netloc:        # scheme-less / hostless -> '' origin
        logging.getLogger(__name__).warning(
            "BASE_URL=%r has no scheme/host; using %s", val, DEFAULT_BASE)
        return DEFAULT_BASE
    return val

def app_origin() -> str:
    p = urlsplit(base())
    return urlunsplit((p.scheme, p.netloc, "", "", ""))   # now always scheme://host[:port]
```

Note: the OLD suffix-strip idiom `val[:-len("/synthesis")]` PRESERVED a scheme-less host
(`"host.com/synthesis"` -> `"host.com"`), so swapping to urlsplit-origin is a subtle
behavioural change for malformed input - guard it.

### Trap 2 - write non-circular, env-robust URL tests

- Do NOT assert `url.startswith(THE_MODULE_CONSTANT)` - it reads the same env that built
  the URL, so it is circular and stays green even if the origin collapsed to `""`.
- DO assert the CONCRETE path+query the input should produce, and that the URL is
  absolute. This catches both a wrong host and an empty origin:

```python
url = build_clip_url(row)
assert url.startswith("http")              # absolute -> catches the empty-origin bug
assert "/clip?v=ABCDEFGHIJ1&s=10" in url   # concrete: real video id + padded start
```

- If you must assert against a derived origin, guard it first so an empty origin fails
  loudly instead of passing vacuously:

```python
origin = app_origin()
assert origin                              # non-vacuous
assert url.startswith(origin)
```

- For tests that genuinely need a pinned host, set the env then reload the module
  (the constant is import-time): `monkeypatch.setenv("BASE_URL", ...)` ->
  `importlib.reload(mod)` -> assert -> `finally: importlib.reload(mod)` to restore.
- Updating a pre-existing test that hardcoded the old domain to assert a STRUCTURAL
  property is a legitimate fix, not cheating: the feature deliberately made the host
  deployment-driven, so the old domain pin encoded a now-false assumption.

## Verification

- `python -c "from urllib.parse import urlsplit, urlunsplit as u; p=urlsplit('host.com/x'); print(repr(u((p.scheme,p.netloc,'','',''))))"` prints `''` (reproduces trap 1).
- With the guard: a scheme-less env value resolves to the canonical default.
- Run the suspected test file ALONE; if it still fails with the wrong host, it is an
  ambient exported env var, not cross-test leakage - check `printenv` for the driver.

## Notes

- Both traps share one root: an env value that is well-formed for the happy path but
  degenerate at the edges (scheme-less, path-less, or just different from the hardcoded
  default the tests assumed).
- A path-LESS but scheme-FULL value (`https://host` with no `/synthesis`) is a SEPARATE
  bug the scheme+netloc guard does NOT catch: `f"{base}/{id}"` then drops the expected
  path segment. Handle/track it separately if your base carries a required path.
- Keep one env var as the single source of truth and derive the rest; per-surface
  override env vars can stay for back-compat but should route through the same guard.

## References

- Python docs: `urllib.parse.urlsplit` / `urlunsplit` (a 5-tuple
  `(scheme, netloc, path, query, fragment)`; an empty scheme+netloc yields a relative
  reference).
