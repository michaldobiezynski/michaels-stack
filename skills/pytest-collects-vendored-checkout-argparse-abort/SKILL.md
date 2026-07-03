---
name: pytest-collects-vendored-checkout-argparse-abort
description: |
  Fix pytest aborting with INTERNALERROR/SystemExit: 2 and "no tests ran" when
  a vendored/cloned third-party repo sits inside the project root. Use when:
  (1) `pytest` output shows another tool's argparse usage text (e.g. "usage:
  gdown ..." or "usage: pytest [-h] [--videoName ...]") followed by
  "pytest: error: unrecognized arguments" and INTERNALERROR SystemExit, (2) the
  suite ran fine before a repo was cloned into the project (even if
  gitignored — pytest collection ignores .gitignore), (3) the vendored repo
  contains files matching test discovery patterns (`*_test.py` /
  `test_*.py`, e.g. TalkNet/LR-ASD's `Columbia_test.py`) that call
  argparse.parse_args() or shell out at IMPORT time. Fix: pin
  `[tool.pytest.ini_options] testpaths = ["tests"]` in pyproject.toml (or
  norecursedirs). Gitignoring the directory is NOT enough.
author: Claude Code
version: 1.0.0
date: 2026-07-02
---

# pytest collects vendored checkouts and aborts on import-time argparse

## Problem

Cloning a third-party research repo into the project root (for an experiment)
silently breaks the ENTIRE test suite later: pytest's default collection walks
every directory under rootdir, and any file matching `test_*.py` or `*_test.py`
is imported. Research repos often run `argparse.parse_args()` (and even network
downloads) at module import, so collection dies with a confusing error that
looks like pytest itself rejecting its own flags.

## Trigger conditions

- `INTERNALERROR> SystemExit: 2`, "no tests ran".
- The usage text printed belongs to the vendored tool, then pytest re-prints
  its OWN usage with the vendored parser's options mixed in (the foreign
  argparse consumed `sys.argv`).
- Example: `LR-ASD/Columbia_test.py` (matches `*_test.py`) parses args and
  auto-downloads a model via gdown at import.

## Solution

Pin collection to the real suite directory in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

`norecursedirs = ["LR-ASD", ...]` also works but rots as new checkouts appear;
`testpaths` is the durable form. Note `.gitignore` does not protect you —
pytest does not consult it.

## Verification

Re-run the full suite; collection proceeds and the count matches the suite's
real size.

## Notes

- The failure appears only on FULL-suite runs (targeted `pytest tests/...`
  invocations never touch the vendored dir), so it can lie dormant until the
  next repo-wide run — often blamed on unrelated recent changes.
- Same class of hazard: vendored `conftest.py` files, which pytest also
  imports during collection.
