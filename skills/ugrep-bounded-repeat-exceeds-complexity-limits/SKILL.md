---
name: ugrep-bounded-repeat-exceeds-complexity-limits
description: |
  Fix for `grep -oE '.{0,60}needle.{0,60}'` context-extraction regexes failing with
  "ugrep: error: error at position N ... exceeds complexity limits" on this Mac, where
  `grep` is a shell function wrapping ugrep (not BSD/GNU grep). Use when: (1) a grep call
  with a bounded repeat `{0,N}` (N above ~30) errors instead of matching, (2) the error
  shows an expanded UTF-8 class like `[\x80-\xbf]*){0,60}`, (3) `grep -o` context
  snippets work with small bounds but not larger ones. Fix: add `-P` (PCRE2 JIT), or
  call `/usr/bin/grep`, or pipe `grep -m N needle | cut -c1-200`.
author: Claude Code
version: 1.0.0
date: 2026-09-02
---

# ugrep rejects bounded repeats above ~30 with "exceeds complexity limits"

## Problem
On this machine `grep` is a zsh function that wraps **ugrep 7.8.x**, captured in Claude
Code's shell snapshot. ugrep compiles `-E` patterns into a DFA, and `.` is expanded into a
multi-byte UTF-8 alternation. A bounded repeat on that alternation, `.{0,N}` with N above
roughly 30, blows the DFA size budget and ugrep aborts with an error instead of matching.
The habitual "show 60 chars of context around a hit" idiom therefore fails.

## Context / Trigger Conditions
- Command shape: `grep -i -o -E '.{0,60}needle.{0,60}' file`
- Output:
  ```
  ugrep: error: error at position 82
  bf][\x80-\xbf]*){0,60}
                        \___exceeds complexity limits
  ```
- `grep --version` prints `ugrep 7.8.4 aarch64-apple-macosx ...`
- `type grep` prints `grep is a shell function from ~/.claude/shell-snapshots/...`
- Same pattern with `{0,20}` or `{0,30}` works; `{0,40}` and above fails (two bounded
  repeats in the pattern; a single one tolerates a slightly larger bound).

## Solution
Pick one, in order of preference:

1. **Add `-P`** (PCRE2 JIT backend, no DFA size limit). Verified with bounds up to 200:
   ```bash
   grep -P -i -o '.{0,60}needle.{0,60}' file
   ```
2. **Bypass the wrapper** with BSD grep:
   ```bash
   /usr/bin/grep -i -o -E '.{0,60}needle.{0,60}' file
   ```
3. **Skip the regex context trick** and truncate the matching line instead:
   ```bash
   grep -i -m 3 needle file | cut -c1-200
   ```

Things that do NOT help: `-U` (binary/ASCII mode) still fails, just at a different
position; `[^\n]{0,60}` instead of `.` fails the same way.

## Verification
The command prints matching snippets instead of `ugrep: error:`. Tested 02/09/2026 on
`pawn-au-chocolat/src-tauri/data/b.tsv` searching for `mongo`: `-E` with `{0,60}` errors,
`-P` with `{0,60}` and `{0,200}` prints both matching lines, `/usr/bin/grep -E` prints both.

## Example
```bash
# fails on this Mac
grep -i -o -E '.{0,80}mongo.{0,80}' processed.jsonl
# works
grep -P -i -o '.{0,80}mongo.{0,80}' processed.jsonl
```

## Notes
- ugrep's `-P` needs the pcre2jit build, which `grep --version` lists as `-P:pcre2jit`.
- ugrep otherwise accepts GNU-style flags, so most grep calls work unchanged; this only
  bites on large bounded repeats and, per ugrep docs, on other DFA-heavy constructs.
- Related: the `grep-rn-pipe-v-excludes-by-path-prefix` skill covers a different
  grep-on-this-machine gotcha.
