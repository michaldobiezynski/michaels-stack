---
name: herdr-pane-probe-key-delivery-and-tui
description: |
  Diagnose "keys/menus don't work inside a herdr pane" reports (Claude Code slash-command
  or skill autocomplete, Tab, Shift+Tab, Escape, arrows, shifted punctuation) with hard
  evidence instead of guessing, from a Claude Code session that is itself running inside
  herdr (HERDR_ENV=1, Bash tool has no tty). Use when: (1) the user says a TUI feature is
  broken "in herdr" but works in a bare terminal, (2) you need to see the exact bytes herdr
  delivers to a pane app with and without the kitty keyboard protocol, (3) you want to drive
  a throwaway Claude Code (or other agent) in a side pane with `herdr agent start` /
  `send-keys` / `read` and inspect the rendered screen, (4) `herdr agent start` returns
  `agent_not_ready` immediately. Covers the keydump-in-a-pane recipe, the Ctrl+C-under-kitty
  gotcha, the folder-trust dialog gotcha, what `herdr api snapshot` does NOT expose, the open
  herdr key-path issues to cite, and the difference between the herdr claude *integration*
  (hook only) and the `/herdr` *skill* (separate npx install).
author: Claude Code
version: 1.0.0
date: 2026-09-02
---

# Probe key delivery and TUI rendering inside a herdr pane

## Problem

A user running Claude Code (or another TUI) inside herdr says something like "herdr doesn't
allow auto-complete for Claude skills". You cannot press keys yourself: the Bash tool inside
a herdr-managed Claude session has no tty (`tty` prints "not a tty", `/dev/tty` is
"device not configured"). Guessing from herdr's issue tracker is unreliable because most
key-path bugs there are layout-, host-terminal- or protocol-specific.

## Context / Trigger conditions

- `env | grep HERDR_` shows `HERDR_ENV=1`, `HERDR_PANE_ID`, `HERDR_SOCKET_PATH`.
- Process chain is `herdr -> herdr server -> zsh -> claude`.
- Symptom is about keys or popups: `/` menu, Tab completion, Shift+Tab mode cycling,
  Escape, arrows, `?`, `:` or other shifted punctuation.

## Solution

### 1. Byte-level keydump in a side pane (mirrors the keyboard path)

herdr's own maintainers accept `herdr pane send-keys` as equivalent to physical keypresses
for key-encoding bugs (issue #3146 reproduces the bug both ways). So:

```bash
SP=<scratchpad dir>
cat > "$SP/keydump.py" <<'EOF'
import sys, os, tty, termios, select, time
flags = sys.argv[1] if len(sys.argv) > 1 else "0"
fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); tty.setraw(fd)
if flags != "0": sys.stdout.write("\x1b[>%su" % flags)      # push kitty flags like the app would
sys.stdout.write("READY flags=%s\r\n" % flags); sys.stdout.flush()
end = time.time() + 12                                       # time deadline, NOT "break on \x03"
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.3)
    if r:
        b = os.read(fd, 1024); sys.stdout.write("GOT " + repr(b) + "\r\n"); sys.stdout.flush()
if flags != "0": sys.stdout.write("\x1b[<u")
sys.stdout.write("DONE\r\n"); sys.stdout.flush(); termios.tcsetattr(fd, termios.TCSADRAIN, old)
EOF
pid=$(herdr pane split --current --direction down --cwd "$SP" --no-focus | jq -r .result.pane.pane_id)
sleep 3
for flags in 0 1; do
  herdr pane send-text "$pid" "clear; python3 keydump.py $flags"; herdr pane send-keys "$pid" enter
  herdr pane wait-output "$pid" --match "READY flags=$flags" --timeout 6000
  for k in / tab shift+tab up down enter escape 'shift+/'; do herdr pane send-keys "$pid" "$k"; sleep 0.25; done
  herdr pane wait-output "$pid" --match DONE --timeout 15000
  herdr pane read "$pid" --source visible --format text | grep -E '^(READY|GOT|DONE)'
done
herdr pane close "$pid"
```

Healthy output on herdr 0.8.2 / macOS / iTerm2 host: `/`, `\t`, `ESC[Z` (legacy) or
`ESC[9;2u` (kitty), `ESC[A`, `ESC[B`, `\r`, `ESC` or `ESC[27u`.

### 2. Drive a throwaway Claude Code and read its screen

```bash
PJ=<an already-trusted project dir>          # NOT the scratchpad, see gotchas
pid=$(herdr pane split --current --direction down --cwd "$PJ" --no-focus | jq -r .result.pane.pane_id)
sleep 4
herdr agent start probe --kind claude --pane "$pid" --timeout 60000
herdr agent wait probe --until idle --timeout 40000
herdr agent send-keys probe /            ; sleep 1.5; herdr agent read probe --source visible --format text | tail -25
herdr agent send-keys probe f e a        ; sleep 1.2; herdr agent read probe --source visible --format text | tail -16
herdr agent send-keys probe down tab     ; sleep 1.2; herdr agent read probe --source visible --format text | tail -12
herdr agent send-keys probe escape; herdr agent send-keys probe escape
herdr agent send-keys probe ctrl+c; sleep 0.4; herdr agent send-keys probe ctrl+c; sleep 2
herdr pane close "$pid"
```

Expected: `/` opens the skill/command list, `/fea` filters it, Down moves the highlight,
Tab replaces the input with the highlighted command. If this passes, herdr's server-to-pane
path and its VT emulator are fine and the fault is upstream of the server (host terminal,
keyboard layout, herdr client decode) or a misunderstanding.

### 3. Gotchas discovered the hard way

- **Ctrl+C under kitty flags is `ESC[99;5u`, not `\x03`.** A dump loop that breaks on
  `\x03` never exits once flags are pushed; the next `send-text` then lands inside the still
  running dumper. Use a time deadline plus `pane wait-output --match DONE`.
- **`herdr agent start` returns `agent_not_ready` ("blocked during startup")** when
  Claude Code shows the folder-trust dialog. Starting in a scratchpad dir triggers it every
  time. Use a directory Claude already trusts, or send `down` then `enter`, then `agent wait`.
- **`herdr api snapshot` does not expose input state.** It only carries agents, layouts and
  panes; there is no keyboard_protocol_flags / bracketed_paste field despite those names
  existing in the binary. Use the keydump instead.
- **Bash `grep` may be ugrep here**: `.{0,90}` context regexes on a 200 MB binary fail with
  "exceeds complexity limits". Use a Python `re` scan on bytes instead.
- **Panes you split appear in the user's tab.** Always `--no-focus` and `pane close` at the end.

### 4. Known open herdr key-path issues worth citing (as of 0.8.2, 02/09/2026)

| Issue | Symptom | When it bites |
| --- | --- | --- |
| #3146 | shifted punctuation delivered as `ESC[<code>;2u` or dropped once the pane app pushes kitty flags | `/` on layouts where it is Shift+7 (German, Slovenian, ...), `?` `:` everywhere |
| #2556 | Shift+Tab dead on some host terminals | Claude Code mode cycling |
| #3480 | clicking a pane sends a bare Escape | closes an open autocomplete menu, interrupts a working agent |
| #2968 | synchronized-output frames tear on keystrokes while other panes stream | popup half-drawn, fixed by Ctrl+L |
| #2640 | agent input line invisible when pane height is small | tiny splits |

Also: Claude Code's terminal-setup for Shift+Enter is per host terminal; herdr panes inherit
`TERM_PROGRAM` from the host (iTerm.app) with `TERM=xterm-256color`.

### 5. Integration vs skill

`herdr integration install claude` installs only `~/.claude/hooks/herdr-agent-state.sh` on
SessionStart (session identity for restore). It does **not** install a `/herdr` skill, so
`/herdr` never appears in Claude's slash autocomplete unless the user ran
`npx skills add herdrdev/herdr --skill herdr -g` (herdr docs, agent-skill page).

## Verification

Ran on 02/09/2026, herdr 0.8.2, Claude Code 2.1.258, macOS, iTerm2 3.6.11 host: keydump
bytes all correct at flags 0 and 1; throwaway Claude Code showed the menu on `/`, filtered on
`/fea`, Tab completed to `/feature-review`.

## References

- https://github.com/herdrdev/herdr/issues/3146 (shifted punctuation under kitty protocol)
- https://github.com/herdrdev/herdr/issues/2556, /3480, /2968, /2640
- https://herdr.dev/llms.txt (docs index), keyboard and troubleshooting pages under docs/next/website/src/content/docs/
