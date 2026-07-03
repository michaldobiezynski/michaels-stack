---
name: pipe-masks-exit-code-in-gated-chains
description: |
  A command piped into tail/grep/tee reports the LAST pipe stage's exit code,
  so `pytest -q | tail -1 && commit` commits on a FAILING suite and
  `release.sh | tee log` reports success on a failed release. Use when:
  (1) any gated chain (`&&`, `if`, `rc=$?`) consumes a piped command's
  status, (2) a commit/merge/deploy went through despite red tests,
  (3) `echo "exit=$?"` after a pipe always prints 0, (4) writing agent/CI
  shell where the next action depends on the previous command's success.
  Fix patterns: capture to a file first (`cmd > /tmp/out 2>&1; ec=$?`),
  or `set -o pipefail` (bash/zsh), or test the real producer not the pipe.
author: Claude Code
version: 1.0.0
date: 2026-06-12
---

# Pipes Mask Exit Codes Exactly Where You Gate On Them

## Problem

`$?` and `&&` see the exit status of the LAST command in a pipeline. The
moment output is prettified through `| tail`, `| grep`, or `| tee`, the
producer's failure is invisible to the gate: `tail` exits 0, the chain
continues, and the failure ships. The trap is worst in agent loops and
scripts because the textual output still SHOWS the failure ("3 failed")
while the control flow says success - the very next step (commit, merge,
deploy, delete) runs anyway.

## Context / Trigger Conditions

- `uv run pytest -q | tail -1 && git commit ...` - commits red suites.
- `cmd 2>&1 | tail -5; echo "exit=$?"` - always prints 0.
- `xcrun notarytool ... | tee log` in a release script - non-zero exit
  swallowed, release "succeeds" (see apple-notarytool-agreement-expired).
- Any `if cmd | filter; then` gate.

## Solution

Pick one, in order of preference for gated chains:

1. **Capture first, gate on the real status, display after**:
   ```bash
   uv run pytest -q > /tmp/suite.out 2>&1; ec=$?
   tail -1 /tmp/suite.out
   if [ $ec -eq 0 ]; then git commit -qm "..."; fi
   ```
2. **pipefail** when the pipeline must stay inline:
   ```bash
   set -o pipefail
   cmd | tail -5 && next   # now fails when cmd fails
   ```
   (zsh: also `setopt PIPE_FAIL`; POSIX sh lacks it.)
3. **PIPESTATUS** when you need per-stage codes: `${PIPESTATUS[0]}` (bash)
   / `${pipestatus[1]}` (zsh).

## Verification

Force a failure and confirm the gate blocks: `false | tail -1; echo $?`
prints 0 (broken) vs the captured pattern printing 1.

## Example

Same session, twice: a slice-3 commit landed on a red suite via
`pytest | tail -1 && git commit` (caught one step later, amended), and a
"suite-exit=0" line printed under "3 failed" because the echo gated on
tail. The capture-first pattern fixed both and was used for every
subsequent gate.

## Notes

- Displaying THROUGH the pipe is fine; deciding through it is not.
- Agent harnesses time out long commands; `> file 2>&1` capture also
  keeps the full log greppable after truncated tool output.
