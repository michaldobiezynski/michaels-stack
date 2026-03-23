---
description: Sync local ~/.claude config to the michaels-stack plugin repo and optionally push to GitHub
user-invocable: true
argument-hint: [--push]
---

Sync the current ~/.claude configuration (skills, agents, commands, rules, hooks, CLAUDE.md) to the michaels-stack plugin repository.

## Steps

1. Run the sync script: `bash ~/development/projects/michaels-stack/scripts/sync-to-plugin.sh`
2. Review the changes shown in the output
3. If changes were detected and the user passed `--push` or confirms:
   - Stage all changes: `git -C ~/development/projects/michaels-stack add -A`
   - Create a commit with message describing what changed
   - Push to GitHub: `git -C ~/development/projects/michaels-stack push`
4. Report what was synced and the commit URL
