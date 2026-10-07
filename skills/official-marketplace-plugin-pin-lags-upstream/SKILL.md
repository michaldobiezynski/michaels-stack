---
name: official-marketplace-plugin-pin-lags-upstream
description: |
  Check whether a third-party plugin listed in claude-plugins-official is pinned to an
  old commit before installing it. Use when: (1) about to run `/plugin install
  <name>@claude-plugins-official` for a community plugin (mattpocock-skills,
  superpowers, etc.) and you want its latest release, (2) a changelog or blog post
  announces new skills or commands that are missing after installing from the official
  marketplace, (3) choosing between the official marketplace, the author's own
  marketplace and `npx skills`. The official marketplace pins url-sourced plugins to a
  fixed git `sha`, which can trail upstream tags by weeks.
author: Claude Code
version: 1.0.0
date: 2026-10-06
---

# Official marketplace plugin pin lags upstream

## Problem
`anthropics/claude-plugins-official` lists some community plugins with
`"source": {"source": "url", "url": "...git", "sha": "<commit>"}`. The pin is updated by
hand and can be weeks behind the author's latest release. Installing from the official
marketplace then gives you an older version, missing whatever the latest changelog
announced.

Observed 06/10/2026: `mattpocock-skills` was pinned to `c55ee46` (18/09/2026). That commit
predates v1.3.0 and v1.3.1, so `/retro` and `/pr` were absent from it even though
aihero.dev had already announced them.

## Solution
1. Read the pin:
   ```bash
   python3 -c "import json,os;d=json.load(open(os.path.expanduser('~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json')));print([p['source'] for p in d['plugins'] if p['name']=='<plugin>'])"
   ```
2. Clone the upstream repo with tags into the scratchpad (`git clone --depth 200 <url>`).
3. Check whether the release you want is in the pin:
   ```bash
   git merge-base --is-ancestor <tag> <pinned-sha> && echo included || echo stale
   ```
   Or check for one file directly: `git show <sha>:skills/.../SKILL.md`.
4. If the pin is stale, install from the author's own marketplace, when the repo ships a
   `.claude-plugin/marketplace.json`:
   ```
   /plugin marketplace add <owner>/<repo>
   /plugin install <plugin>@<marketplace-name-from-that-json>
   ```
   For skill packs you can also cherry-pick individual skills with `npx skills@latest add <owner>/<repo>`.

## Verification
After installing, the new skills or commands appear in the skill listing. For
`mattpocock-skills` they are namespaced, for example `mattpocock-skills:retro`.

## Notes
- Installing through a plugin namespaces the skills, so they cannot collide with your own
  same-named commands (such as a personal `/code-review`). `npx skills` installs
  unnamespaced folders into `~/.agents/skills` and symlinks them into `~/.claude/skills`,
  so collisions are possible there.
- Watch for skills that depend on other skills. Matt Pocock's `retro` calls the
  `writing-for-agents` skill in its first step, so cherry-picking `retro` alone leaves
  that call dangling.
- `/plugin marketplace update` refreshes the official marketplace clone but cannot move a
  pin that Anthropic has not bumped.
- See also [[claude-plugins-marketplace-temp-dir-leak]]: each marketplace refresh can
  leave a stray clone behind.
