---
name: claude-config-broken-symlinks
description: |
  Fix broken symlinks in ~/.claude/ that cause install scripts and backup operations to fail.
  Use when: (1) cp -r fails with "No such file or directory" on ~/.claude paths,
  (2) install scripts abort during backup steps with set -euo pipefail,
  (3) skills show as symlinks pointing to non-existent directories like ~/.agents/,
  (4) debug/latest symlink points to wrong user profile path.
  Covers finding, diagnosing, and fixing broken symlinks, plus hardening backup commands.
metadata:
  author: Claude Code
  version: 1.0.0
  date: 2026-03-23
---

# Claude Config Broken Symlinks

## Problem

Install scripts (like the ECC selective installer) that back up `~/.claude/` using
`cp -r` fail when broken symlinks exist in the directory tree. Combined with
`set -euo pipefail`, the entire script aborts before any components are installed.

## Context / Trigger Conditions

- `cp: /Users/<user>/.claude/skills/<name>: No such file or directory` during backup
- `cp: /Users/<user>/.claude/debug/latest: No such file or directory`
- Any install script that runs `cp -r ~/.claude/ <backup-dir>` with `set -euo pipefail`
- Skills that were previously symlinked from external directories (e.g. `~/.agents/skills/`)
  where the source has since been removed
- `debug/latest` symlinks pointing to a different user profile path

## Solution

### Step 1: Find all broken symlinks

```bash
find ~/.claude -type l ! -exec test -e {} \; -print
```

### Step 2: Inspect what they point to

```bash
ls -la <broken-symlink-path>
```

This reveals whether the target was an external directory (recoverable by re-cloning)
or genuinely lost content.

### Step 3: Remove or fix broken symlinks

If the content is lost and can be re-fetched (e.g. from a GitHub repo):
```bash
rm <broken-symlink>
mkdir -p ~/.claude/skills/<name>
# Re-download the content
```

If the content is unrecoverable and unneeded:
```bash
rm <broken-symlink>
```

### Step 4: Harden the backup command

Replace `cp -r` with `rsync` in install scripts to tolerate broken symlinks:

```bash
# Before (fragile)
cp -r "$CLAUDE_DIR" "$BACKUP_DIR"

# After (resilient)
rsync -a --copy-links --ignore-errors "$CLAUDE_DIR/" "$BACKUP_DIR/"
```

## Verification

1. Run `find ~/.claude -type l ! -exec test -e {} \; -print` — should return empty
2. Re-run the install script — backup step should succeed
3. Verify installed components with `ls ~/.claude/agents/ ~/.claude/skills/ ~/.claude/commands/`

## Example

```
# Script fails:
[INFO]  Backing up existing ~/.claude to ~/.claude-backup-20260323_124745...
cp: /Users/michaldobiezynski/.claude/skills/vercel-react-best-practices: No such file or directory

# Diagnosis:
$ ls -la ~/.claude/skills/vercel-react-best-practices
lrwxr-xr-x  1 user  staff  48 Jan 24 10:48 ... -> ../../.agents/skills/vercel-react-best-practices

# Fix:
$ rm ~/.claude/skills/vercel-react-best-practices
$ mkdir -p ~/.claude/skills/vercel-react-best-practices
# Re-download content from source repo
```

## Common Sources of Broken Symlinks

| Location | Typical cause |
|---|---|
| `~/.claude/skills/<name>` | Linked from `~/.agents/skills/` which was later removed |
| `~/.claude/debug/latest` | Symlink to another user profile path (e.g. `/Users/personal/`) |
| `~/.claude/rules/<name>` | Linked from a git repo that was deleted or moved |

## Notes

- Always run the broken symlink check before any install/backup operation on `~/.claude/`
- The `vercel-labs/agent-skills` repo is the source for `vercel-react-best-practices` and `web-design-guidelines` skills — fetch directly from GitHub raw URLs if re-downloading
- `rsync --ignore-errors` will still copy everything it can, skipping only the broken links
