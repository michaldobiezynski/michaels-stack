---
name: claude-code-bypass-permissions-silent-noop
description: |
  Diagnose and fix Claude Code still prompting for Bash/tool permissions despite
  having `"permissions": { "defaultMode": "bypassPermissions" }` set in
  ~/.claude/settings.json. Use when: (1) user says Claude Code keeps asking to
  run commands / batch scripts despite config changes, (2) bypassPermissions is
  configured in settings.json but prompts still appear, (3) user's work machine
  runs autonomously but personal machine does not with seemingly identical
  settings, (4) skipDangerousModePermissionPrompt is set but doesn't seem to do
  anything. Root cause: `bypassPermissions` CANNOT be set as a persistent
  defaultMode — settings.json accepts the value silently but it falls back to
  `default` mode at runtime. Fix is a shell alias with --dangerously-skip-permissions.
author: Claude Code
version: 1.0.0
date: 2026-04-11
---

# Claude Code: bypassPermissions defaultMode is a silent no-op

## Problem

A user configures Claude Code to run autonomously by setting:

```json
{
  "skipDangerousModePermissionPrompt": true,
  "permissions": { "defaultMode": "bypassPermissions" }
}
```

…in `~/.claude/settings.json`, expecting Claude Code to launch straight into
bypass mode and execute Bash commands without prompting. **It doesn't work.**
Claude Code still prompts before each tool call as if the config weren't there.

The config looks correct. The schema accepts it. No error is logged. But the
mode silently falls back to `default`, and the user is left confused — often
comparing against a "work laptop" where hands-off mode works, not realising
that machine is almost certainly launched via a CLI flag.

## Context / Trigger Conditions

Activate this skill when ANY of these symptoms appear:

1. User reports: "Claude Code keeps asking me to run commands / batch scripts /
   npm install / etc. on my personal machine, but on my work laptop it just runs"
2. `~/.claude/settings.json` already contains `"defaultMode": "bypassPermissions"`
   and/or `"skipDangerousModePermissionPrompt": true`
3. User has tried setting the mode in settings.json and it "isn't being applied"
4. User is confused why `skipDangerousModePermissionPrompt` seems to do nothing
5. User compares two machines and assumes it must be a CLAUDE.md rule or hook
   difference, when the real cause is settings.json vs launch flag

## Root Cause

Per the Claude Code permission-modes documentation:

> "You cannot enter `bypassPermissions` from a session that was started without
> one of the enabling flags; restart with one to enable it."

This restriction applies to `defaultMode` in `settings.json` too. The valid
persistent defaultMode values are:

- `"default"` — standard permission prompts
- `"acceptEdits"` — auto-approves edits and safe Bash
- `"plan"` — read-only plan mode
- `"dontAsk"` — only pre-approved tools (requires enabling flag)
- `"auto"` — requires `--enable-auto-mode` at startup
- `"bypassPermissions"` — **SILENTLY IGNORED as defaultMode; requires CLI flag**

And `skipDangerousModePermissionPrompt: true` only suppresses the one-time
"are you sure?" warning that appears WHEN you launch with the CLI flag. It
does NOT enable bypass-as-default-mode on its own.

Neither of these two settings, alone or together, makes Claude Code launch
in bypass mode. Only the CLI flag does.

## Solution

Add a shell alias so every `claude` invocation launches with the required flag:

```bash
# ~/.zshrc (or ~/.bashrc)
alias claude='claude --dangerously-skip-permissions'
```

Then reload the shell:

```bash
source ~/.zshrc
```

The existing `"skipDangerousModePermissionPrompt": true` in `settings.json`
will now take effect and suppress the one-time warning, so the session
launches silently into full bypass mode.

### Alternative — keep an escape hatch

If you want a safe-mode escape for sessions where bypass feels risky:

```bash
alias claude-yolo='claude --dangerously-skip-permissions'
# leave bare `claude` as the safe default
```

### Clean up the dead config

The now-useless `"defaultMode": "bypassPermissions"` entry in settings.json
should be either removed or replaced with a weaker but actually-working
fallback for sessions launched without the alias:

```json
"permissions": { "defaultMode": "acceptEdits" }
```

`acceptEdits` auto-approves file edits and safe Bash, which is a useful
middle ground when the alias isn't applied.

## Verification

After setting up the alias and reloading the shell:

1. Launch Claude Code: `claude`
2. Confirm NO "bypass mode warning" prompt appears on startup (proves
   `skipDangerousModePermissionPrompt` is working)
3. Ask Claude Code to run any command that would normally require approval,
   e.g. `ls ~/Downloads` or `curl https://example.com`
4. Command executes without a permission prompt → fix verified

If prompts still appear, check:

- Is the alias actually loaded? Run `type claude` — it should show
  `claude is an alias for claude --dangerously-skip-permissions`
- Is there a project-level `.claude/settings.json` or
  `.claude/settings.local.json` overriding the launch flag?
- Is `~/.claude/settings.local.json` narrowing the allow list? (It won't
  override the launch flag, but worth a look.)

## Example

**Diagnostic conversation:**

> User: "Claude Code keeps asking me to run batch scripts on my personal
> machine, but on my work laptop it just runs. My settings look identical."

**Investigation:**

1. Read `~/.claude/settings.json` → observe `defaultMode: "bypassPermissions"`
   and `skipDangerousModePermissionPrompt: true` are set
2. Initially suspect hooks or a CLAUDE.md "clarify first" rule — a common
   false lead
3. Confirm with claude-code-guide that `bypassPermissions` as defaultMode is
   a silent no-op
4. Realise the work laptop is almost certainly launching via a shell alias
   or `--dangerously-skip-permissions` flag that isn't present on personal
5. Add the alias to `~/.zshrc`

**Fix delivered:**

```bash
echo "alias claude='claude --dangerously-skip-permissions'" >> ~/.zshrc
source ~/.zshrc
```

## Notes

- **Security implication**: `--dangerously-skip-permissions` means Claude
  Code will run ANY tool without asking. Only use this on machines and in
  contexts where that blast radius is acceptable. The flag name is "dangerously"
  for a reason.
- **Settings precedence**: managed settings > CLI flags > project
  `settings.local.json` > project `settings.json` > user `~/.claude/settings.json`.
  A project-level setting CAN override a user-level defaultMode, but nothing
  short of the CLI flag enables bypass mode.
- **Red herrings to rule out first**: before assuming this gotcha, check that
  the prompts are actually from the harness (tool approval dialogues) and not
  from Claude itself asking clarifying questions per a CLAUDE.md directive.
  The symptoms look similar but the fixes are completely different.
- **Why `skipDangerousModePermissionPrompt` exists at all**: it's for users
  who already launch with the CLI flag and find the startup warning noisy.
  Its existence misleads users into thinking it unlocks the mode.
- **The settings.json schema accepting `bypassPermissions` silently is
  arguably a UX bug** — a validation warning would save this confusion.
  Until/unless that changes, this skill is the compensating knowledge.

## References

- Claude Code permission modes: https://code.claude.com/docs/en/permission-modes
- Claude Code settings: https://code.claude.com/docs/en/settings
- Claude Code permissions & precedence: https://code.claude.com/docs/en/permissions
