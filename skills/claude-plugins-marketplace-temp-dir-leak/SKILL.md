---
name: claude-plugins-marketplace-temp-dir-leak
description: |
  Recover tens of GB of disk space leaked by Claude Code plugin marketplace refreshes.
  Use when: (1) a Mac's disk is mysteriously full and ~/.claude is huge (multi-GB to
  60+ GB), (2) `du -sh ~/.claude/plugins` is far larger than expected, (3)
  ~/.claude/plugins/marketplaces contains many directories named temp_<epoch-ms>
  (e.g. temp_1786976756407), or on newer CLIs temp_git_<epoch-ms>_<rand> (some with a
  `..clone` suffix; 146 of them, 4 GB in total, seen 06/10/2026 on 2.1.289), alongside
  the real marketplace dirs. Each temp_* dir is a
  leftover marketplace clone (~24 MB each) that was never cleaned up; thousands can
  accumulate. Safe fix: delete only the temp_* dirs, keep the named marketplace dirs.
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# Claude Code Plugin Marketplace temp_* Directory Leak

## Problem
Claude Code's plugin marketplace refresh creates temporary clone directories under
`~/.claude/plugins/marketplaces/` named `temp_<epoch-ms>` and does not always remove
them. Over months they accumulate silently: one observed machine had 2,827 temp dirs
at ~24 MB each, totalling 60 GB, making `~/.claude` one of the largest directories on
the disk.

## Context / Trigger Conditions
- Investigating "what is taking up my storage" on a machine that runs Claude Code
- `du -xsh ~/.claude` reports many GB (plugins dominate: `~/.claude/plugins` ≈ total)
- `ls ~/.claude/plugins/marketplaces` shows rows like `temp_1786976756407` mixed with
  real marketplace names (`anthropics-skills`, `claude-code-plugins`,
  `claude-plugins-official`)

## Solution
1. Confirm the leak and its size:
   ```bash
   ls ~/.claude/plugins/marketplaces | grep -c '^temp_'
   du -sh ~/.claude/plugins/marketplaces
   ```
2. Delete only the temp clones (never the named marketplace dirs):
   ```bash
   rm -rf ~/.claude/plugins/marketplaces/temp_*
   ```
   Prefer running while Claude Code is not mid-refresh; a temp dir created seconds ago
   could belong to an in-flight refresh, so skipping the newest one is the cautious
   variant.
3. The named marketplace dirs and `installed_plugins.json` are untouched, so installed
   plugins keep working; a future refresh re-clones anything it needs.

## Verification
`du -sh ~/.claude/plugins` drops to a few tens of MB and
`ls ~/.claude/plugins/marketplaces` lists only the named marketplaces. Claude Code
still lists and runs installed plugins afterwards.

## Notes
- The dir count grows with usage; expect the leak to recur until the upstream bug is
  fixed, so re-check when disk fills again.
- Sizes observed 26/08/2026 on Claude Code with three configured marketplaces.
