---
name: grep-rn-pipe-v-excludes-by-path-prefix
description: |
  Fix for a residual/audit grep that silently reports CLEAN (empty) and makes you
  believe a codebase-wide rename/scrub/secret-sweep is complete when matching lines
  still exist. Use when: (1) you pipe a recursive grep into an exclusion grep, e.g.
  `grep -rn PATTERN dir | grep -viE "foo|bar"`, and it returns nothing; (2) the
  exclusion term is ALSO a directory or filename component on the path you are scanning
  (excluding `council_mcp` while scanning `council_mcp/`, excluding `test` while scanning
  `tests/`, excluding `lib` under `lib/`); (3) a residual scan says CLEAN but you have
  prior evidence the term exists; (4) verifying a rename, deprecation removal, secret
  sweep, or "no TODO left" check. Root cause: `grep -rn` prefixes every result line with
  `path:line:`, and the second `grep -v` matches against the WHOLE line including that
  path, so an exclusion term that appears in the directory/file path nukes EVERY line
  regardless of content. CLEAN from a filtered grep is necessary, not sufficient.
author: Claude Code
version: 1.0.0
date: 2026-06-21
---

# Recursive grep piped into `grep -v` excludes by path prefix

## Problem

A common "is the scrub complete?" check looks like:

```bash
grep -rinE "the council|council's" council_mcp | grep -viE "council-clip|council_mcp"
```

The intent: find every line containing the generic term, minus lines whose **content**
mentions the import path / project name. It returns nothing, so you conclude the scrub
is complete.

It is not. The result is empty because **every** result line was excluded, not because
no line matched. A live, matching, user-facing string (`f"A concept from the council:"`)
was still in the tree and was missed; only an independent adversarial review caught it.

## Root cause

`grep -rn` (and `-rln`, `git grep -n`) prefixes every result line with `path:line:`:

```
council_mcp/collections.py:426:    definition = ... f"A concept from the council: ..."
```

The downstream `grep -viE "council_mcp"` matches against the **entire** line, and the
directory you are scanning is literally named `council_mcp`, so the path prefix
`council_mcp/...` matches the exclusion on **every** line. The `-v` therefore drops all
output. The same trap fires whenever the exclusion token is any path component:
`tests/` while excluding `test`, `lib/` while excluding `lib`, a file `config.py` while
excluding `config`.

## Trigger conditions

- `grep -rn ... | grep -v <term>` (or `-vE`, `-vi`) returns empty/CLEAN.
- `<term>` is also a directory name or filename on the search path.
- You are verifying a rename, scrub, secret sweep, dead-code removal, or a "no X remains"
  audit, and a CLEAN result is load-bearing.
- You have prior evidence (an earlier scan, a known occurrence) that the term still exists.

## Solution

Make the exclusion match **content only**, not the `path:line:` prefix, or filter paths
with path-aware flags instead of `grep -v`:

1. Anchor the exclusion past the `path:line:` prefix:
   ```bash
   grep -rnE "the council" council_mcp | grep -vE ':[0-9]+:.*(council-clip|import council_mcp)'
   ```
2. Filter paths with grep's own flags, content with the pattern:
   ```bash
   grep -rnE "the council" council_mcp --include='*.py' | grep -vE 'import|from '
   ```
3. Use `git grep` with pathspec excludes for path filtering:
   ```bash
   git grep -nE "the council" -- 'council_mcp' ':(exclude)council_mcp/__init__.py'
   ```
4. Strip the prefix before excluding (`-h` drops filenames, but you lose location):
   ```bash
   grep -rhE "the council" council_mcp | grep -vE "council-clip"
   ```

Then **cross-check**: a residual scan that returns CLEAN must be confirmed with an
independent, simpler re-grep (no `-v`, count the raw hits) before you declare done.

## Verification

Re-run the first stage WITHOUT the `-v` and count:

```bash
grep -rnE "the council" council_mcp | wc -l        # raw matches
grep -rnE "the council" council_mcp | grep -v ...  # after exclusion
```

If the raw count is non-zero but the filtered count is zero, the `-v` is over-matching
(almost always on the path prefix). A correct filter drops a *few* lines, not all of them.

## Example

```
# What you ran (BUG): returns nothing
grep -rinE "the council|council's" council_mcp | grep -viE "council-clip|council_mcp"
# -> (empty)  "CLEAN"   <-- false; council_mcp/ path matched the -v on every line

# Reality without the broken -v: three live matches
council_mcp/collections.py:293: ... "What the council says about ..."
council_mcp/collections.py:426: ... "A concept from the council: ..."
council_mcp/collections.py:471: ... "How the council weighs ..."
```

## Notes

- This is silent: the exit status of the pipe is "success with no output", which reads
  identically to a genuine CLEAN. Nothing errors.
- It is worst on a rename/scrub where the OLD name and the directory/module share a stem
  (`council` the brand vs `council_mcp` the package, `auth` the word vs `auth/` the dir).
- The broader lesson: a CLEAN residual grep is necessary but not sufficient proof a scrub
  is complete. Pair it with an independent re-grep (different pattern, count cross-check)
  and, for anything user-facing, an adversarial review. Related: tests/reviews catch what
  a self-authored verification command structurally cannot.
- See also `pipe-masks-exit-code-in-gated-chains` for the cousin failure where a pipe
  hides a non-zero exit code.
