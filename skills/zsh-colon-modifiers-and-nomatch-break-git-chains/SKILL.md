---
name: zsh-colon-modifiers-and-nomatch-break-git-chains
description: |
  Two zsh behaviours that silently break one-line git/shell chains run through Claude Code's Bash tool (which
  uses zsh on macOS). Use when: (1) `git show $SHA:path/to/file` fails with "fatal: ambiguous argument
  '<sha>...ks.tsx': unknown revision" or the SHA comes out mangled (zsh read `$SHA:s...` as a history-style
  modifier), (2) a command fails with "zsh: no matches found: dir/*" and the rest of an `&&` chain never ran
  (an unmatched glob is an error in zsh, not a literal), (3) `?` in a URL argument triggers "no matches found",
  (4) `echo ===` fails with "== not found", (5) a stash/apply/commit sequence ended in an unexpected state after
  one of these, (6) `set -- $pair` or `for x in $list` sees one word instead of several (zsh does not split
  unquoted parameters), so a loop's command fails with "argument required" or gets the whole string.
author: Claude Code
version: 1.1.0
date: 2026-09-29
---

# zsh colon modifiers and nomatch in git chains

## Problem
Claude Code's Bash tool runs zsh on macOS. Five zsh rules differ from bash, and each can break a chained
command half-way, leaving git (stash, index, working tree) in a state the rest of the chain assumed would not
happen:
- `$VAR:x...` applies a modifier when `x` is a modifier letter (`s`, `h`, `t`, `r`, `e`, `a`, `A`, `l`, `u`,
  `q`...). `git show $SHA:src/fx/File.tsx` becomes a substitution (`:s` with `r` as the delimiter), mangling the
  revision.
- An unmatched glob (`rm -f dir/*.png` in an empty dir) is an error ("no matches found"), and `&&` stops there.
- `?` and `*` in unquoted arguments are globs: `node x.mjs http://host/page?intro=0` fails.
- `==` at the start of a word is `=cmd` expansion: `echo ===` fails.
- Unquoted parameters are not word-split: with `r="repo 8"`, `set -- $r` sets one argument, and
  `for x in $list` loops once over the whole string.

## Solution
- Brace or quote every `rev:path`: `git show "${SHA}:src/fx/File.tsx"` or `git show 'HEAD:src/file'`.
- Clear directories without globs: `rm -rf dir && mkdir -p dir`, or `find dir -name '*.png' -delete`, or
  `setopt null_glob` for that command.
- Quote URLs and patterns: `'http://host/page?intro=0'`.
- Quote separators: `echo "---"` or `echo '== x'`.
- Split explicitly: `set -- ${=r}` or `for x in ${=list}`, or loop over a real array
  (`for pair in "repo-a 8" "repo-b 15"; do read -r name n <<< "$pair"; ...`). Simplest of all, write out
  the two or three commands.
- **When a chain fails, inspect before retrying:** `git status`, `git log --oneline -3`,
  `git stash list --format='%H %gd %gs'`. A stash entry survives a failed `apply`; recover a file from it by SHA
  (`git checkout "<sha>" -- path`), then drop that entry by finding its current `stash@{n}` from its unique tag.

## Verification
The command runs with the intended revision, or the glob matches or is skipped. After any failure, `git status`
and `git stash list` show the expected state before you continue.

## Example
Chess Explosion, 28/09/2026: a chain to split a fix into "measure" and "fix" commits used
`git show $SHA:src/fx/CaptureSparks.tsx`. zsh mangled it ("ambiguous argument
'1ea9c8...ks.tsx'"), part of the chain still committed, and the stash apply failed quietly. Recovery was:
inspect, amend the missing probe line into the first commit, `git checkout "<stash sha>" -- src/fx/CaptureSparks.tsx`
for the fix, commit, and drop the tagged stash entry. Earlier that day, `rm -f $S/film/*.png` on an empty
directory skipped a whole chain, and an unquoted `?intro=0` URL and `echo ===` failed the same way.

## Notes
- Never use a bare `git stash`/`pop` in repos with worktrees or parallel sessions (the stack is shared). Tag
  entries uniquely and apply by SHA.
- Related: `gh-pr-merge-delete-branch-fails-in-worktree`.
