---
name: lancedb-launchd-fd-exhaustion-compaction
description: |
  Fix a long-running LanceDB job that dies with "Too many open files (os error 24)"
  (lance error / LanceError(IO)), especially under macOS launchd. Two compounding
  causes: (1) launchd's default soft NOFILE is 256, far too low; (2) a table grown
  by frequent small appends accumulates thousands of fragment files + versions, so a
  single full-table scan opens them all at once and blows the limit. Use when: a
  daily/scheduled Python+LanceDB pipeline crashes on .to_list()/.to_arrow()/scan; an
  app works when run by hand but crashes under launchd/cron; ls of <table>.lance/data
  shows tens of thousands of .lance files. Fix = raise the FD limit (plist
  SoftResourceLimits + ulimit) AND compact_files + cleanup_old_versions (needs the
  pylance package pinned to lancedb's bundled lance-core version).
author: Claude Code
version: 1.0.0
date: 2026-06-18
---

# LanceDB "Too many open files" under launchd: FD limit + fragment compaction

## Problem

A scheduled Python job that scans a LanceDB table crashes with:

```
RuntimeError: lance error: LanceError(IO): Too many open files (os error 24), .../lance-io-<ver>/src/local.rs
```

It often runs fine by hand but dies under launchd/cron, and gets worse over weeks.

## Context / Trigger conditions

- The crash is on a full-table read: `.to_list()`, `.to_arrow()`, a `.search()...`
  scan, or `cleanup`/`compact`.
- The job is launched by **launchd** (a `LaunchAgent` plist) or cron, not your shell.
- `ls <db>/<table>.lance/data | wc -l` is in the thousands/tens-of-thousands, and
  `ls <db>/<table>.lance/_versions | wc -l` is similarly huge (one manifest per
  append). `du -sh` on the table is large despite a modest row count.

## Root cause (two compounding)

1. **launchd default soft `NOFILE` is 256.** Your interactive shell may show
   `ulimit -n` of 1048576, but a launchd job inherits ~256 unless the plist sets
   `SoftResourceLimits`. Check: `plutil -p <plist> | grep -i NumberOfFiles` — if
   absent, it's 256.
2. **Fragment/version bloat.** Frequent small appends (e.g. a daily incremental
   ingest) each write a new data fragment + a new manifest version, none compacted.
   A scan of the current version opens *every* current-version fragment file at
   once; with thousands of fragments that alone exceeds 256, and even with a high
   limit it's slow and memory-hungry. (Most of the on-disk `.lance` files are
   orphaned data from old versions; `cleanup_old_versions` reclaims those.)

## Solution

### A. Raise the FD limit (stops the crash)

In the LaunchAgent plist, add (and `launchctl bootout` + `bootstrap` to reload):

```xml
<key>SoftResourceLimits</key>
<dict><key>NumberOfFiles</key><integer>131072</integer></dict>
<key>HardResourceLimits</key>
<dict><key>NumberOfFiles</key><integer>262144</integer></dict>
```

Belt-and-braces, also add near the top of the shell entrypoint so manual runs are
covered: `ulimit -n 131072 2>/dev/null || true`.

### B. Compact the table (removes the pathology)

`compact_files()`/`cleanup_old_versions()` delegate to the standalone **`lance`**
Python package (pylance), which lancedb does NOT bundle. If it's missing you get:
`ImportError('The lance library is required ... pip install pylance')`.

**Pin pylance to lancedb's bundled lance-core version** (read it from the original
crash path, e.g. `lance-io-4.0.0` → install `pylance==4.0.0`). A mismatched pylance
can upgrade the on-disk format so lancedb can no longer read it.

```bash
uv pip install 'pylance==4.0.0'   # match lancedb's bundled core; venv has no pip
```

Then compact with a **row-count safety gate before the irreversible cleanup**:

```python
import lancedb
from datetime import timedelta
t = lancedb.connect(DB).open_table("chunks")
n0 = t.count_rows()
t.compact_files()                      # merges current-version fragments -> few/1
assert lancedb.connect(DB).open_table("chunks").count_rows() == n0  # readback OK
t.cleanup_old_versions(older_than=timedelta(hours=1), delete_unverified=True)
```

If the readback row count differs, STOP and restore from backup — do not cleanup.
Always back up first (a plain recursive copy of `<db>/<table>.lance` is a valid
snapshot since LanceDB is append-only/manifest-versioned).

## Verification

- `lance.dataset("<db>/<table>.lance").get_fragments()` returns 1 (or a few), not
  thousands — this is the count a scan opens, the real fix.
- `_versions/` collapses to ~2, `du -sh` drops dramatically, row count unchanged.
  (Verified case: 26 GB / 20,874 fragments / 19,273 versions → 331 MB / 1 fragment
  / 2 manifests, 38,509 rows preserved; compact ~10 s, cleanup ~4 min.)

## Notes

- `compact_files`/`cleanup_old_versions` are deprecated in newer lancedb in favour
  of `Table.optimize()`, but still work; `optimize()` also rebuilds the vector index
  (heavier). For a pure FD/scan fix, compact + cleanup is enough.
- The data-dir file count can stay high right after compaction (orphans pending
  delete); trust `get_fragments()` for the current version, and a second
  `cleanup_old_versions` pass clears the orphans.
- Backgrounding gotcha: `( … ) &` inside an already-backgrounded launcher returns
  instantly; the real Python keeps running. Poll a sentinel file / `pgrep`, not the
  launcher's exit code.
