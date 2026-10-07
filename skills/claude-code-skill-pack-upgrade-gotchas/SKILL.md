---
name: claude-code-skill-pack-upgrade-gotchas
description: |
  Gotchas when upgrading, swapping or pruning third-party skill packs and plugins in
  Claude Code (Matt Pocock's skills, superpowers, etc.). Use when: (1) replacing a
  skill that was renamed upstream (to-issues -> to-tickets, diagnose -> diagnosing-bugs)
  and commands, rules or other skills call the old name, (2) the replacement declares
  `disable-model-invocation: true` and an autonomous command relies on the Skill tool
  calling it, (3) applying an approved ecosystem clean-up in auto mode, where
  `claude plugin install/uninstall` is denied as [Self-Modification] and
  `npx skills remove` as [Irreversible Local Destruction].
author: Claude Code
version: 1.0.0
date: 2026-10-06
---

# Skill pack upgrade gotchas

## Problem
Upgrading a skill pack looks like a delete-and-install. Two things break that plan
silently:
1. A renamed upstream skill can change who is allowed to invoke it. If the new version
   declares `disable-model-invocation: true`, the model can no longer load it through
   the Skill tool. Any command or workflow that told the model to "use the X skill"
   then fails at run time, and nothing warns you.
2. In auto mode the permission classifier sorts these operations differently, so a
   bundle the user approved only partly goes through.

## Solution
1. Before deleting or renaming a skill, grep every place that might call it:
   ```bash
   grep -rnE '\b(old-skill-a|old-skill-b)\b' ~/.claude/CLAUDE.md ~/.claude/rules ~/.claude/commands ~/.claude/agents ~/.claude/skills/*/SKILL.md
   ```
2. For each caller, check the replacement's frontmatter. If it has
   `disable-model-invocation: true` and the caller is model-driven (an autonomous
   `/feature` phase, for example), keep the old skill. Otherwise, rewrite the caller.
3. Under auto mode, sort the operations up front (observed on CLI 2.1.289, 06/10/2026):

   | Operation | Classifier |
   |---|---|
   | `npx skills add <repo> -g -y -a claude-code --skill a b c` | allowed |
   | Edit to `~/.claude/settings.json` (non-permission keys) | allowed |
   | Edit to `~/.claude/rules/*.md` | allowed |
   | `rm` of leaked `~/.claude/plugins/marketplaces/temp_*` dirs | allowed |
   | `claude plugin install` / `claude plugin uninstall` | denied (Self-Modification) |
   | `npx skills remove -g ...` | denied (Irreversible Local Destruction) |

   Hand the denied ones to the user as ready-to-run commands. Do not route around a
   denial by editing `enabledPlugins` or `rm`-ing skill folders yourself.

## Verification
- `diff -rq <upstream-clone>/skills/<path>/<name> ~/.claude/skills/<name>` reports
  that the installed files are identical to the upstream release.
- New skills that the model can invoke show up in the live skill listing
  straight away. Skills limited to the user (`disable-model-invocation: true`) never
  appear there, so an empty listing for them is expected.

## Notes
- `npx skills add -a claude-code` copies folders into `~/.claude/skills`, while older
  installs symlinked them from `~/.agents/skills`. Expect both layouts side by side.
- `--skill` takes several space-separated names in a single `add` call.
- Before publishing a mirror of `~/.claude/skills` (a public dotfiles or plugin repo), exclude
  `skills/synced/` and `skills/.trash/`. With claude.ai skill sync on, they hold Anthropic's
  skills (`morning`, `computer-use`, `built-in-browser`), not yours. Also leave out copied
  third-party skills whose folders lack their licence notice.
- Related: [[official-marketplace-plugin-pin-lags-upstream]],
  [[claude-plugins-marketplace-temp-dir-leak]].
