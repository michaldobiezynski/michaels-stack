---
name: llm-cli-stdin-arg-max-long-prompts
description: |
  Fix for `OSError: [Errno 7] Argument list too long` (E2BIG) when calling
  an LLM CLI (`claude -p`, `gemini`, `ollama run`, `llm`, etc.) from a
  Python subprocess with a large prompt passed via argv. Use when:
  (1) the subprocess.run call works fine for short prompts but fails on
  long ones, (2) the failing input is typically a long document, full
  podcast transcript, large file dump, or codebase concatenation embedded
  in the prompt, (3) the error message specifically says "Argument list
  too long" (errno 7, ENAMETOOLONG variant E2BIG), (4) you're on macOS
  with ARG_MAX = 262144 bytes or a Linux distro with similar limits,
  (5) you only see the failure for SOME items in a batch (the ones whose
  prompt exceeds the limit), succeeding silently for shorter ones.
  Fix: switch from `["cli", "-p", prompt]` argv form to `["cli", "-p"]`
  + `input=prompt` stdin form. Stdin has no argv-style limit. Works for
  every well-behaved CLI that reads stdin when no positional prompt is
  given.
author: Claude Code
version: 1.0.0
date: 2026-05-11
---

# LLM CLI prompts blowing past macOS ARG_MAX: pipe via stdin instead

## Problem

You're calling an LLM CLI from Python:

```python
proc = subprocess.run(
    ["claude", "-p", prompt],   # prompt is a large string
    capture_output=True,
    text=True,
    check=False,
)
```

This works for short prompts. For long ones (a full podcast transcript,
a large file dump, a code-base concatenation) it blows up with:

```
OSError: [Errno 7] Argument list too long: 'claude'
```

The traceback ends in `subprocess.py` at `_execute_child`. The CLI itself
is never invoked. The error comes from the kernel rejecting `execve()`.

If you're batch-processing N items, you might see this hit *some* items
and silently succeed on others, leaving a confusing mix of "13 of 36
videos failed".

## Context / Trigger conditions

All of the following typically apply:

- Calling an LLM CLI: `claude -p`, `gemini`, `ollama run <model>`,
  Simon Willison's `llm`, `aichat`, OpenAI's `chatgpt`, etc.
- Prompt assembled from variable-length input (a transcript, a file
  contents dump, a long context window).
- macOS (`getconf ARG_MAX` returns 262144) or many Linux distros
  (commonly 2097152 but still bounded).
- The total combined size of argv + environment exceeds ARG_MAX. The
  environment counts: long PATH, locale vars, etc. take up budget.
- Errno is 7 (`E2BIG`). Message reads "Argument list too long".

## Root cause

`execve()` and friends pass argv as one contiguous block, capped by
`ARG_MAX`. On macOS that's 262144 bytes (~256KB) for the COMBINED size of
all argv strings, all environment strings, and pointer overhead. A 200KB
prompt easily breaks this on its own; a 100KB prompt can break it once
the environment is included.

There is no portable way to raise this from inside the calling process.

## Solution

Read stdin instead of argv. Every well-behaved LLM CLI accepts the prompt
on stdin when no positional prompt is given:

```python
proc = subprocess.run(
    ["claude", "-p"],          # NO prompt argument
    input=prompt,              # piped via stdin
    capture_output=True,
    text=True,
    check=False,
)
```

The kernel imposes no ARG_MAX-style limit on what flows through a pipe.
Megabyte-scale prompts work fine.

CLI-specific notes:

| CLI | Stdin form |
|---|---|
| `claude -p` (Claude Code) | `["claude", "-p"]` + `input=prompt` |
| `gemini` | `["gemini"]` + `input=prompt` (or `gemini --stdin`) |
| `ollama run <model>` | `["ollama", "run", model]` + `input=prompt` |
| `llm` (Simon Willison) | `["llm"]` + `input=prompt` |
| `chatgpt` (community) | varies; check `--help` |

To verify on the shell first, just pipe:

```bash
echo "what is 2 plus 2? answer with just the number" | claude -p
# → 4
```

If that prints a sensible answer, the CLI reads stdin.

## Verification

```python
# Re-run the batch. Items that failed with errno 7 should now succeed.
# Sanity check: count outputs vs inputs.
assert len(output_files) == len(input_items)
```

A quick numerical check: macOS `getconf ARG_MAX` and Python `len(prompt)`:

```python
import os, subprocess
arg_max = int(subprocess.check_output(["getconf", "ARG_MAX"]).decode().strip())
print(f"ARG_MAX = {arg_max:,} bytes")
print(f"prompt  = {len(prompt):,} bytes")
print(f"env     = {sum(len(k)+len(v)+2 for k,v in os.environ.items()):,} bytes")
```

If `prompt + env` exceeds `ARG_MAX`, the argv form WILL fail.

## Example

In a clip-extraction pipeline that processes podcast transcripts:

```python
# Before — fails on 13 of 36 videos with OSError [Errno 7]
def call_claude(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout

# After — works for all 36
def call_claude(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p"],
        input=prompt,
        capture_output=True, text=True, check=False,
    )
    return proc.stdout
```

The failing transcripts were 250KB+ (8000+ second long-form podcast
interviews). The combined prompt exceeded 262144 bytes once template
text and environment vars were included.

## Notes

- The bug is silent in the sense that the CLI never runs and emits no
  error message of its own. The only signal is the Python-side OSError
  from `subprocess`.
- The argv limit applies even with `shell=False`. Quoting / escaping
  does not help. `shell=True` only makes it worse (the shell parses
  the args itself and counts against the limit).
- A common workaround that does NOT scale: writing the prompt to a temp
  file and using `cli -f file.txt` or `cat file.txt | cli`. The latter
  is fine; the former requires the CLI to support a `-f`/`--file` flag.
  Stdin is the cleanest cross-CLI fix.
- This is unrelated to the model's token / context limit. The argv limit
  trips BEFORE the model ever sees the prompt.
- If the CLI buffers stdin and your prompt is enormous (>10MB), watch
  for the CLI's own internal limits. But practically, anything that
  fits in a model's context window fits comfortably through a Unix pipe.

## References

- [POSIX execve E2BIG](https://pubs.opengroup.org/onlinepubs/9699919799/functions/execve.html) -
  "The number of bytes used by the new process image's argument list
  and environment list is greater than the system-imposed limit of
  {ARG_MAX} bytes."
- [Apple `getconf` docs](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man1/getconf.1.html) -
  macOS ARG_MAX is 262144 by default.
- [Python subprocess.run](https://docs.python.org/3/library/subprocess.html#subprocess.run) -
  the `input` parameter for piping stdin.
