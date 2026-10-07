---
name: uv-run-resyncs-lockfile-reverting-pip-install
description: |
  Fix a dependency upgrade in a uv project that appears to succeed but silently
  reverts. Use when: (1) `uv pip install --upgrade <pkg>` prints "Installed 1
  package" with the new version, but the very next `uv run python -c "import
  pkg; print(pkg.__version__)"` reports the OLD version, (2) you upgraded a
  package to fix a bug and the bug persists under `uv run` even though `uv pip
  list` looked right, (3) a pinned-feeling version keeps coming back after every
  install, (4) you are debugging a stale vendored library (yt-dlp, requests,
  boto3) inside a uv-managed project. Root cause: `uv run` re-syncs the
  environment from uv.lock before executing, discarding any out-of-band `uv pip
  install`. Fix is `uv lock --upgrade-package <pkg>` (or `uv add pkg@latest`).
author: Claude Code
version: 1.0.0
date: 2026-08-15
---

# `uv run` re-syncs from uv.lock, silently reverting `uv pip install`

## Problem

You upgrade a package in a uv-managed project. The install reports success with
the new version. Every subsequent `uv run` still uses the old version, and any
bug you were upgrading to fix is still present. Nothing errors, so it reads as
"the upgrade didn't fix it" rather than "the upgrade didn't happen".

## Context / Trigger conditions

- The project has a `uv.lock` (i.e. it is a uv *project*, not a bare venv).
- `uv pip install --upgrade <pkg>` prints something like:
  ```
  Uninstalled 1 package in 56ms
  Installed 1 package in 9ms
   - yt-dlp==2026.3.17
   + yt-dlp==2026.7.4
  ```
- But immediately after:
  ```
  $ uv run python -c "import yt_dlp; print(yt_dlp.version.__version__)"
  2026.03.17          # <- the OLD version, silently restored
  ```
- Symptom family: "I upgraded the library but the upstream fix isn't there."

## Solution

`uv run` performs an implicit `uv sync` against `uv.lock` before running the
command. Anything installed imperatively with `uv pip install` is *not* in the
lockfile, so the sync removes it and reinstalls the locked version. The install
was real; it just did not survive the next `uv run`.

Update the lockfile instead:

```sh
# upgrade one package, keep everything else pinned
uv lock --upgrade-package yt-dlp
uv run python -c "import yt_dlp; print(yt_dlp.version.__version__)"   # now new

# alternatives
uv add 'yt-dlp@latest'      # also records it as a project dependency
uv lock --upgrade           # upgrade EVERYTHING (usually too blunt)
```

If the dependency is unpinned in `pyproject.toml` (e.g. just `"yt-dlp"`), the
`--upgrade-package` form is all you need; no pyproject edit is required.

## Verification

Verify through `uv run`, never through `uv pip list` or a bare `python`:

```sh
uv run python -c "import yt_dlp; print(yt_dlp.version.__version__)"
```

Confirm the lockfile actually moved:

```sh
git diff uv.lock | grep -E '^\+.*yt-dlp|^-.*yt-dlp'
```

A CLI binary on `$PATH` is a separate installation and does NOT track the
project env. `yt-dlp --version` can report an old Homebrew build while the
project env has a new one, and vice versa. If the code does `import yt_dlp`,
only the `uv run` answer matters.

## Example

Diagnosing YouTube downloads failing with `HTTP Error 403: Forbidden` inside a
uv project:

```sh
$ yt-dlp --version                 # Homebrew CLI, red herring
2026.03.17
$ uv pip install --upgrade yt-dlp  # looks like it worked
 + yt-dlp==2026.7.4
$ uv run python -c "import yt_dlp; print(yt_dlp.version.__version__)"
2026.03.17                          # reverted

$ uv lock --upgrade-package yt-dlp
Updated yt-dlp v2026.3.17 -> v2026.7.4
$ uv run python -c "import yt_dlp; print(yt_dlp.version.__version__)"
2026.07.04                          # sticks
```

## Notes

- This is by design: uv projects treat `uv.lock` as the source of truth, and
  `uv run` guarantees the environment matches it. `uv pip` is the escape hatch
  for non-project venvs.
- `UV_NO_SYNC=1 uv run ...` skips the sync, which will make an imperative
  install appear to work. Do not rely on it to "fix" this — it hides the drift
  and the next normal `uv run` reverts again.
- Same trap applies to `uv pip uninstall`: the package returns on next `uv run`.
- If you are chasing a stale library, check the version through the SAME
  interpreter the failing code uses before concluding the upgrade didn't help.
- Related: [[pipx-uv-backend-force-install-silent-noop]] (a different silent
  no-op in the pipx/uv pairing).

## References

- uv projects and locking: https://docs.astral.sh/uv/concepts/projects/sync/
- `uv lock` CLI reference: https://docs.astral.sh/uv/reference/cli/#uv-lock
- `uv run` (implicit sync): https://docs.astral.sh/uv/reference/cli/#uv-run
