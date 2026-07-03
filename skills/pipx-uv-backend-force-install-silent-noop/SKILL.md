---
name: pipx-uv-backend-force-install-silent-noop
description: |
  pipx 1.12+ uses `uv` to create venvs, and `pipx install --force <local-path>`
  silently fails to replace the installed package source when the target venv
  already exists. The CLI output looks successful ("Installing to existing
  venv '<pkg>'") but the installed files in ~/.local/pipx/venvs/<pkg>/ are NOT
  updated — the old code remains, leading to "my edits aren't taking effect"
  confusion. Use when: (1) you ran `pipx install --force <path>` to update a
  locally-developed package after editing source, (2) the installed CLI
  behaves as if your edits did not land, (3) the install output contains
  "A virtual environment already exists" or "Installing to existing venv"
  lines, (4) grepping the installed .py files under
  ~/.local/pipx/venvs/<pkg>/lib/python*/site-packages/<pkg>/ shows the OLD
  source. The fix is to uninstall first: `pipx uninstall <pkg> && pipx install <path>`
  (or a Makefile `reinstall` target that chains both). `--force` alone is
  insufficient when the underlying venv tool refuses to overwrite the venv
  directory.
author: Claude Code
version: 1.0.0
date: 2026-05-17
---

# pipx --force silent no-op with uv backend

## Problem

`pipx install --force <local-package-path>` is supposed to replace any existing
installation. On pipx **1.12.0** (and adjacent versions) the venv-creation step
is delegated to `uv venv`, which refuses to overwrite an existing virtual
environment unless `--clear` is passed. pipx does not pass `--clear` and does
not surface the resulting failure as an error. Instead it logs a warning and
falls through to "Installing to existing venv '<pkg>'" — which sounds like a
recovery but is actually a **no-op for the source code**. The result: your
edits to the source repo do not land in the installed package.

The CLI keeps running with the old code. Debugging from the symptom side
(e.g. "why is my new binding not firing?") leads you away from the real cause
(stale install).

## Trigger conditions

All of the following together:

- pipx 1.12.x with `uv` as the underlying venv tool (Homebrew install on
  Apple Silicon hits this by default; `uv --version` and `pipx --version` will
  confirm).
- A previously-installed pipx package being updated via
  `pipx install --force <local-path>`.
- Console output during install contains:
  - `error: Failed to create virtual environment`
  - `Caused by: A virtual environment already exists at ...`
  - `Use --clear to replace it`
  - `Not removing existing venv ... because it was not created in this session`
  - `'... uv venv ...' failed`
  - `Installing to existing venv '<pkg>'`
- Final pipx exit status is non-zero, but the CLI from the package still works
  (because the prior install is still in place).
- After "installing", running the package gives the **old** behaviour.
- Grep against the installed source shows the old code, not your edit.

## Solution

Always uninstall before reinstalling when updating a locally-developed pipx
package:

```bash
pipx uninstall <pkg>
pipx install <local-path>
```

Or as a Makefile target (matches the `reinstall:` pattern many projects already
have):

```makefile
reinstall:
	-pipx uninstall <pkg>
	pipx install --force .
```

The leading `-` makes the uninstall step non-fatal on first run when the
package isn't yet installed.

If you want a one-liner that always works:

```bash
pipx uninstall <pkg> 2>/dev/null; pipx install <local-path>
```

If you specifically need to keep `--force` working, you can try setting
`PIPX_DEFAULT_PYTHON` or `PIPX_USE_PYTHON_ENSUREPATH=0` to bypass uv — but the
uninstall-first pattern is more reliable across pipx versions.

## Verification

After running the install, grep the installed source for a string from your
edit:

```bash
grep -n '<unique-string-from-your-edit>' \
  ~/.local/pipx/venvs/<pkg>/lib/python*/site-packages/<pkg>/*.py
```

If the match is missing, the reinstall didn't take. Do the
uninstall+install sequence and re-grep.

## Example

Observed during recite (TUI text-to-speech) development. After editing
`recite/app.py` and `recite/synth.py`, `pipx install --force .` printed:

```
error: Failed to create virtual environment
  Caused by: A virtual environment already exists at `/Users/.../recite`. Use `--clear` to replace it
⚠️  Not removing existing venv ... because it was not created in this session
'/opt/homebrew/bin/uv venv --python ... failed
Installing to existing venv 'recite'
```

`recite --help` continued to work, suggesting success. Grep against
`~/.local/pipx/venvs/recite/lib/python3.14/site-packages/recite/app.py` showed
the OLD binding line (no `priority=True`), proving the source had not been
replaced. `make reinstall` (uninstall + install) fixed it on the next try; a
follow-up grep confirmed the new code was present.

## Notes

- This is a pipx-side bug (or at least a UX failure): pipx should either pass
  `--clear` to `uv venv` when invoked with `--force`, or surface the failure
  with a non-zero exit and clear messaging.
- Likely fixed in some future pipx; recheck the behaviour when bumping pipx
  major or minor versions.
- The `make install` target in many Python projects uses `pipx install --force .`
  — those projects will silently fail to update on this version of pipx
  unless they switch to a `reinstall`-style target.
- A clean side-effect of always uninstalling first: you cannot accidentally
  inherit stale entry-point scripts or dangling files from a prior install.

## References

- pipx documentation on `install`: <https://pipx.pypa.io/stable/docs/#pipx-install>
- uv venv `--clear` semantics: <https://docs.astral.sh/uv/reference/cli/#uv-venv>
- Versions observed: pipx 1.12.0, uv 0.10.12 (Homebrew on macOS Apple Silicon).
