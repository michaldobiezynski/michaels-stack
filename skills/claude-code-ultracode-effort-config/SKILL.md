---
name: claude-code-ultracode-effort-config
description: |
  Configure Claude Code's effort level and enable "ultracode" persistently via
  ~/.claude/settings.json. Use when: (1) you want ultracode (xhigh effort +
  standing dynamic-workflow orchestration) to be the DEFAULT for all sessions,
  (2) /effort reports "CLAUDE_CODE_EFFORT_LEVEL=<x> overrides effort this session
  — clear it and ultracode takes over" or "...still controls this session", (3) a
  chosen effort level won't stick / ultracode never activates despite being
  selected, (4) you tried setting effortLevel:"ultracode" or effortLevel:"max" in
  settings.json and it was rejected or ignored, (5) you want to know why an env
  var keeps overriding the saved effort every session. Covers the effortLevel
  enum, the separate `ultracode` boolean key, and the CLAUDE_CODE_EFFORT_LEVEL
  env-block trap. Related: [[claude-code-bypass-permissions-silent-noop]].
author: Claude Code
version: 1.0.0
date: 2026-05-28
---

# Claude Code: ultracode / effort-level configuration

## Problem

You want a specific effort level — especially **ultracode** — to be the default
for all Claude Code sessions, but:

- Setting `"effortLevel": "ultracode"` or `"effortLevel": "max"` in
  `settings.json` does not work (the enum rejects them).
- `/effort` keeps warning that an env var is overriding your choice and that the
  change is "session-only", so ultracode never actually takes over.
- The override persists across restarts, so it feels like the setting is stuck.

The root cause is three separate, easily-confused controls plus one trap.

## Context / Trigger Conditions

Any of:

- `/effort` prints one of (verified strings in v2.1.154):
  - `CLAUDE_CODE_EFFORT_LEVEL=<x> overrides effort this session — clear it and ultracode takes over`
  - `Not applied: CLAUDE_CODE_EFFORT_LEVEL=<x> overrides effort this session, and <y> is session-only (nothing saved)`
  - `<y> saved from settings, but CLAUDE_CODE_EFFORT_LEVEL=<x> still controls this session`
- You edited `settings.json` to set the effort to `max`/`ultracode` and it had no effect.
- Ultracode (multi-agent workflows by default) never activates even though you selected it.

## Solution

There are **three distinct controls**. Do not conflate them:

| Control | Where | Accepts | Role |
|---|---|---|---|
| `effortLevel` | top-level `settings.json` key | enum **only** `["low","medium","high","xhigh"]` | persisted base effort |
| `ultracode` | top-level `settings.json` key | **boolean** | xhigh effort **+ standing dynamic-workflow orchestration** |
| `CLAUDE_CODE_EFFORT_LEVEL` | env var | `low\|medium\|high\|xhigh\|max\|ultracode\|auto` (`auto`/`unset` → no override) | **session-only** override, highest precedence |

Key facts (from the v2.1.154 binary schema and resolution logic):

- `"max"` and `"ultracode"` are **not** valid values for the persisted `effortLevel`
  key — its enum is only the four above. `/effort max` / `/effort ultracode` route
  to the env override / the `ultracode` boolean respectively, not to `effortLevel`.
- **Ultracode is a boolean**, not an effort tier: `"ultracode": true` means
  "xhigh effort + standing dynamic-workflow orchestration". The workflow-by-default
  behaviour is gated on `settings.ultracode === true`, and when true the effort
  resolves to `xhigh`.
- `CLAUDE_CODE_EFFORT_LEVEL` is documented as **session-only ("nothing saved")** and
  takes precedence over the saved settings. The trap: if it lives in the **`env`
  block of `settings.json`**, it is injected into *every* session, so it silently
  overrides your saved effort and **blocks ultracode permanently** until removed.

**To make ultracode the default for all sessions**, edit `~/.claude/settings.json`:

1. **Remove** `CLAUDE_CODE_EFFORT_LEVEL` from the `env` block (this is what `/effort`
   means by "clear it").
2. **Add** the top-level boolean `"ultracode": true`.
3. Leave `effortLevel` at `"xhigh"` (or omit it) — ultracode resolves to xhigh anyway,
   so they are consistent. Do **not** try `effortLevel:"ultracode"`.

```jsonc
{
  "env": {
    // CLAUDE_CODE_EFFORT_LEVEL removed — it was a per-session override blocking ultracode
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "effortLevel": "xhigh",
  "ultracode": true
}
```

**Current-session caveat:** editing `settings.json` cannot change the already-running
process. The live session keeps `CLAUDE_CODE_EFFORT_LEVEL` in its environment, and a
child shell **cannot unset a parent process's env var**, so the change only takes
effect on **restart** (or in any newly-started session).

## Verification

```bash
# 1. JSON is valid and keys are correct
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); \
print('ultracode =', d.get('ultracode')); \
print('effortLevel =', d.get('effortLevel')); \
print('env has CLAUDE_CODE_EFFORT_LEVEL =', 'CLAUDE_CODE_EFFORT_LEVEL' in d.get('env',{}))"
# expect: ultracode = True / effortLevel = xhigh / env has ... = False
```

After **restarting** Claude Code, `/effort` should report current effort as
`ultracode (xhigh + dynamic workflow orchestration)` with no override warning.

## Example

Symptom: `/effort` returns `CLAUDE_CODE_EFFORT_LEVEL=max overrides effort this session
— clear it and ultracode takes over`, and `settings.json` `env` block contains
`"CLAUDE_CODE_EFFORT_LEVEL": "max"`.

Fix: delete that env line, add `"ultracode": true`, restart. Future sessions start in
ultracode; `/effort xhigh` (etc.) can still temporarily dial it back per session.

## Notes

- **Version-specific**: the enum and key names were read from the bundled binary at
  `~/.local/share/claude/versions/<version>`. Re-grep if Claude Code updates and the
  behaviour changes: `grep -aoE 'effortLevel:[a-z_$]+\.enum\(\[[^]]*\]' <binary>` and
  `grep -aoE 'ultracode:[a-z_$]+\.boolean\(\)[^,}]*' <binary>`.
- `CLAUDE_CODE_EFFORT_LEVEL=auto` or `=unset` is treated as **no override** (null), not
  as a literal level.
- Enabling ultracode globally means a multi-agent **workflow runs by default for every
  substantive task** — high token cost. Intended trade-off; dial back per session with
  `/effort` if needed.
- This is the same class of bug as a `settings.json` key silently not applying — cf.
  [[claude-code-bypass-permissions-silent-noop]] (where `bypassPermissions` as a
  persistent `defaultMode` is accepted but silently falls back).

## References

- Source of truth: bundled Claude Code binary schema/resolution logic
  (`~/.local/share/claude/versions/2.1.154`), inspected via `grep -a`. No external docs
  cover the `effortLevel` enum vs `ultracode` boolean distinction at this granularity.
