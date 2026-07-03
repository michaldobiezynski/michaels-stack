---
name: tui-piped-stdin-reattach-dev-tty
description: |
  Fix for a Python TUI / interactive CLI that launches via piped stdin
  (e.g. `echo X | mytui`, `pbpaste | mytui`, `cat file | mytui`) and then
  silently refuses to respond to ANY keystroke — q, Esc, Ctrl+C, mouse —
  even though the UI renders normally. Use when: (1) a Textual / urwid /
  blessed / prompt_toolkit / Rich.Live app reads piped text successfully
  but won't accept keyboard input afterwards, (2) raw escape sequences
  like `^[[113;5u` (Kitty keyboard-protocol key reports) or `^[[<35;…M`
  (SGR mouse motion) leak into the terminal alongside the rendered UI,
  proving the terminal is sending input that the app isn't consuming,
  (3) the same TUI works fine when launched without a pipe (`mytui`,
  `mytui file.txt`) but is unresponsive whenever stdin is redirected,
  (4) the program reads piped input via `sys.stdin.read()` and then
  hands control to a TUI driver. Root cause: after the pipe is
  consumed, fd 0 is at EOF; the TUI tries to read keys from fd 0 and
  gets nothing, while the user's actual keystrokes go to the
  controlling tty which the TUI isn't reading. Fix: open `/dev/tty`
  and `os.dup2` it over fd 0 BEFORE handing off to the TUI driver.
  Same trick that `less`, `vim -`, and `git --interactive` use.
author: Claude Code
version: 1.0.0
date: 2026-05-18
---

# TUI unresponsive when launched via piped stdin — reattach /dev/tty

## Problem

A Python CLI accepts piped text input (`echo X | myprog`) and then transfers
control to an interactive TUI driver (Textual, urwid, blessed, prompt_toolkit,
Rich.Live, etc.). The UI renders correctly. But **no keystroke ever reaches
the app** — no bindings fire, q/Esc/Ctrl+C/Ctrl+Q all appear ignored, and the
user has to `Ctrl-Z + kill %1` or `pkill` from another shell.

In some terminals the user can SEE the unread input bytes leaking onto the
screen as raw escape sequences (Kitty keyboard protocol, SGR mouse reports)
alongside the rendered UI.

Why it happens:

1. `echo X | myprog` redirects `myprog`'s fd 0 to the read end of the pipe.
2. `myprog` reads the pipe to EOF and stores the text.
3. fd 0 is now a closed pipe — readable but yields EOF immediately.
4. The TUI driver starts and reads from fd 0 expecting keystrokes. It only
   gets EOF.
5. The user's actual keypresses arrive on the controlling tty (`/dev/ttysNNN`),
   which the TUI isn't reading from.
6. Most TUI drivers don't fall back to `/dev/tty` automatically. The app sits
   there rendering forever, deaf to input.

## Trigger conditions

ALL of the following:

- Python TUI launched via piped stdin: `cmd | mytui`, `pbpaste | mytui`,
  `cat f.txt | mytui`, `mytui < f.txt`.
- The UI renders correctly (synth/process/data pipeline visibly works).
- Q, Esc, Ctrl+C, Ctrl+Q, and any other key binding do nothing.
- Running the same TUI without a pipe (`mytui`, `mytui file.txt`) works
  perfectly — keys respond, quit cleanly.
- (Strong supporting signal) In a modern terminal with Kitty keyboard
  protocol or SGR mouse enabled, escape sequences like the following appear
  in the terminal alongside the TUI render:
  - `^[[113;5u` — Kitty kbd-protocol "Ctrl+Q" (keycode 113, modifier 5).
  - `^[[<35;18;18M` — SGR mouse motion event (button 35, row 18, col 18).
  - Literal `qqqq` between sequences — plain q presses also not consumed.
- The CLI code reads piped input via `sys.stdin.read()` or similar.

## Solution

After consuming the piped input but BEFORE invoking the TUI driver, reopen
`/dev/tty` and use `os.dup2` to point fd 0 at the terminal. Replace
`sys.stdin` with a Python file object backed by the new fd 0.

```python
import os
import sys


def _reattach_stdin_to_tty() -> None:
    """Swap fd 0 for /dev/tty so the TUI can read keystrokes after piped
    input has been consumed. Silently no-ops when there is no controlling
    tty (cron, daemonised, CI runner)."""
    try:
        tty_fd = os.open("/dev/tty", os.O_RDONLY)
    except OSError:
        return
    os.dup2(tty_fd, 0)
    os.close(tty_fd)
    sys.stdin = os.fdopen(0, "r")


def load_text(file_arg: str | None) -> str:
    if file_arg:
        return open(file_arg, encoding="utf-8").read()
    if not sys.stdin.isatty():
        text = sys.stdin.read()
        _reattach_stdin_to_tty()   # ← critical
        return text
    # ... fall back to clipboard, prompt, etc. ...
    return ""
```

The `os.dup2(tty_fd, 0)` does the heavy lifting. After it:

- fd 0 IS the controlling tty.
- Any C-level code (including Textual's terminal driver, which often uses
  `os.read(0, ...)`) will read from the terminal.
- `sys.stdin = os.fdopen(0, "r")` keeps `sys.stdin` consistent with fd 0
  so subsequent Python code (e.g. `input()`) also works.

This is the same trick used by:

- `less` (e.g. `git log | less` — less reads piped text but still responds to
  `q`, arrow keys, etc.)
- `vim -` (`cat file | vim -`)
- `git add -i` and `git rebase -i` when invoked in scripts.

## Verification

Two ways to verify the fix:

1. **Live test** in a real terminal:

   ```bash
   echo "hello world. test sentence two." | mytui
   ```

   Press the TUI's quit key (e.g. `q`). It should exit immediately.

2. **Pty-based unit test** — spawn the program inside a pty and assert that
   keys still drive it. Standard library: `pty.openpty()` + subprocess wiring,
   or use `pyte`/`pexpect` for higher-level assertions. Example with
   pexpect:

   ```python
   import pexpect
   child = pexpect.spawn("bash -c 'echo hi | mytui'")
   child.expect("hi")          # UI rendered
   child.sendline("q")         # send quit
   child.expect(pexpect.EOF)   # cleanly exited
   ```

   Before the fix: `pexpect.EOF` never arrives (timeout). After: clean exit.

## Example

Real-world fix from recite (Textual TUI text-to-speech player):

`recite/__main__.py` (BEFORE):

```python
def _load_input(file_arg: str | None) -> str:
    if file_arg:
        return Path(file_arg).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    # ... clipboard fallback ...
```

Symptom: `echo "hi how are you?" | recite` rendered the UI ("hi how are you?"
with the current word highlighted) but `q` did nothing. In Warp (which has
Kitty kbd protocol on), the literal bytes `^[[113;5u^[[113;5uqqqq^[[<35;…M`
leaked into the terminal — Warp was sending input that recite wasn't reading.

Fix: added `_reattach_stdin_to_tty()` and called it after the
`sys.stdin.read()`. Same behaviour now works:

```python
if not sys.stdin.isatty():
    text = sys.stdin.read()
    _reattach_stdin_to_tty()
    return text
```

After the fix, `echo X | recite` accepts q/space/arrow keys exactly like
`recite file.txt`.

## Notes

- **Always silently no-op on OSError when opening /dev/tty.** In headless
  environments (cron, systemd unit without TTYPath, GitHub Actions, Docker
  without `-t`), there is no controlling tty and `open("/dev/tty")` raises
  `OSError: [Errno 6] No such device or address`. The TUI will fail to start
  anyway in those environments; don't blow up at the reattach step.
- **Windows note**: `/dev/tty` is POSIX-only. On Windows, the equivalent is
  `CONIN$` (`open("CONIN$", "r")`). For cross-platform code, gate the call
  on `os.name == "posix"` or use a try/except.
- **Doesn't help if the terminal itself is non-interactive** (IDE Run pane
  with no PTY allocated, JetBrains "Run" tab without "Emulate terminal in
  output console", etc.). In those cases, there IS no `/dev/tty` to reattach
  to. Symptom is the same (no keystrokes) but the fix is "run it in a real
  terminal", not this trick.
- **Order matters**: reattach BEFORE calling into the TUI driver. Many
  drivers cache the input source at init time; reassigning `sys.stdin` after
  the driver starts may have no effect. Always do the dup2 first.
- **Don't reassign sys.stdin alone — must dup2 fd 0.** Most TUI drivers read
  via `os.read(0, ...)` or `select.select([0], ...)` directly, NOT via
  `sys.stdin`. Reassigning `sys.stdin` to a `/dev/tty` file object without
  also fixing fd 0 leaves the driver still reading the closed pipe.

## References

- POSIX spec for `/dev/tty`:
  <https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap10.html>
- Python `os.dup2` docs:
  <https://docs.python.org/3/library/os.html#os.dup2>
- `less(1)` source — see `ch.c` for the `/dev/tty` open used after piped input.
- Related Stack Overflow Q&A:
  <https://stackoverflow.com/questions/3999114/how-to-detach-from-the-controlling-terminal-in-bash>
- `pexpect` for pty-based testing: <https://pexpect.readthedocs.io/>
