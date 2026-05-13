---
name: project-claude-md-pr-update-hook
description: |
  Install a UserPromptSubmit hook in a project's .claude/settings.json that
  reminds Claude to check whether CLAUDE.md needs updating before opening a
  pull request. Use when: (1) adding a project-level CLAUDE.md and you want
  it kept current without relying on Claude to remember, (2) the user asks
  to "trigger Claude to update CLAUDE.md on PR", (3) adopting a running-log
  section in CLAUDE.md that decays if not maintained, (4) setting up any
  keyword-gated UserPromptSubmit hook that should fire only on specific
  phrases (not every message). Covers the JSON-stdin payload shape, the
  $CLAUDE_PROJECT_DIR expansion, jq-based prompt extraction, and a tested
  keyword regex for PR-intent phrases.
author: Claude Code
version: 1.0.0
date: 2026-04-14
---

# Project CLAUDE.md PR-Update Hook

## Problem
A project-level `CLAUDE.md` with a running log of decisions decays if no one
remembers to update it. Adding text to CLAUDE.md saying "update me when you
open a PR" is unreliable - it's just a hint the model may or may not follow.
A `UserPromptSubmit` hook is deterministic: it runs on every prompt and can
deterministically inject a reminder when PR-intent keywords appear.

## Context / Trigger Conditions
- Project has (or is about to have) a `CLAUDE.md` with a running-log section
- User wants CLAUDE.md updates reliably proposed at PR-creation time
- User asks for keyword-triggered prompts/reminders scoped to one repo
- Generic case: any UserPromptSubmit hook that should be silent on most
  prompts but fire on specific keywords

## Solution

### 1. Hook payload shape

Claude Code sends the hook a JSON object on **stdin**:

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../projects/.../transcript.jsonl",
  "cwd": "/path/to/project",
  "permission_mode": "default",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "the user's message text"
}
```

Stdin is consumed on first read. Cache the payload, then extract fields:

```bash
PAYLOAD=$(cat)
PROMPT=$(echo "$PAYLOAD" | jq -r '.prompt // empty')
CWD=$(echo "$PAYLOAD" | jq -r '.cwd // empty')
```

### 2. Hook script (`.claude/hooks/pr-claude-md-check.sh`)

The hook has **two emit modes** gated by whether `CLAUDE.md` exists at the
project root (from the `cwd` field of the payload):

- **CLAUDE.md exists** → emit the full 5-step "Update protocol" reminder
- **CLAUDE.md missing** → emit a lighter nudge suggesting the user create
  one (propagates the pattern to new projects)
- **No PR-intent match** → silent exit 0

```bash
#!/bin/bash
set -euo pipefail
PAYLOAD=$(cat)

if ! command -v jq >/dev/null 2>&1; then
  exit 0   # fail silent if jq missing
fi

PROMPT=$(echo "$PAYLOAD" | jq -r '.prompt // empty')
CWD=$(echo "$PAYLOAD"    | jq -r '.cwd    // empty')

# PR-intent regex: open/create/draft/raise/make + pr|pull request,
# "gh pr create", "ready to merge", "merge this"
if ! echo "$PROMPT" | grep -iqE '(open|create|draft|raise|make)[[:space:]]+.*\b(pr|pull[-[:space:]]*request)\b|gh[[:space:]]+pr[[:space:]]+create|ready[[:space:]]+to[[:space:]]+merge|merge[[:space:]]+this'; then
  exit 0
fi

if [ -n "$CWD" ] && [ -f "$CWD/CLAUDE.md" ]; then
  cat <<'EOF'
📘 PROJECT CLAUDE.md UPDATE CHECK
Before opening this PR, follow CLAUDE.md § "Update protocol":
  1. Review branch commits: git log --oneline <base>..HEAD
  2. Identify new conventions, architectural decisions, skill-worthy findings
  3. PROPOSE the CLAUDE.md update to the user BEFORE committing it
  4. Append to "Running log of decisions" with today's date (YYYY-MM-DD)
  5. Prune entries older than ~6 months absorbed into code/skills/conventions
If nothing warrants an entry, say so and proceed.
EOF
else
  cat <<'EOF'
📘 NO PROJECT CLAUDE.md FOUND
This project has no CLAUDE.md at the repo root. Consider creating one to
capture repo-specific conventions and a running log of decisions that
future Claude sessions can load automatically.

Recommended structure: Stack, Commands, Conventions, Skill pointers,
Workflow, Running log, Update protocol.

Template: see skill `project-claude-md-pr-update-hook`.

If you choose not to create one, ignore this reminder and proceed.
EOF
fi

exit 0
```

Make executable: `chmod +x .claude/hooks/pr-claude-md-check.sh`

### 3. Register in `.claude/settings.json`

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/pr-claude-md-check.sh"
          }
        ]
      }
    ]
  }
}
```

`$CLAUDE_PROJECT_DIR` is expanded by Claude Code to the session's project
root, making the hook portable across clones.

### 4. Add an "Update protocol" section to `CLAUDE.md`

The hook reminds the model; CLAUDE.md tells the model what to do. Example:

```markdown
## Update protocol - read before opening a PR

1. Review branch commits: `git log --oneline master..HEAD`
2. Identify anything that is:
   - A new repo-wide convention
   - A non-reversible architectural choice
   - A skill-worthy discovery (use claudeception, not CLAUDE.md)
3. PROPOSE the update to the user BEFORE committing it. No silent edits.
4. Append to "Running log of decisions" with today's date (YYYY-MM-DD).
5. Prune entries older than ~6 months whose content is now absorbed elsewhere.
```

## Verification

Test each branch directly from a shell before relying on the hook:

```bash
HOOK=.claude/hooks/pr-claude-md-check.sh

# 1. PR-intent + CLAUDE.md exists → full reminder
echo '{"prompt":"please open a pr","cwd":"'"$PWD"'"}' | "$HOOK"

# 2. PR-intent + no CLAUDE.md → lighter nudge
echo '{"prompt":"please open a pr","cwd":"/tmp"}'     | "$HOOK"

# 3. No PR-intent → silent
echo '{"prompt":"what does this function do","cwd":"/tmp"}' | "$HOOK"

# Tested positive matches (all emit one of the two reminders):
# - "please open a pr for this"
# - "gh pr create --title foo"
# - "can you draft a pull request"
# - "create pr" / "raise a pr" / "make a pr"
# - "ready to merge"
# - "merge this"
```

If the hook fails silently inside Claude Code, check:

- File is executable (`chmod +x`)
- `jq` is on `$PATH` (install via Homebrew if needed)
- `$CLAUDE_PROJECT_DIR` is the expected project root (echo it from the hook
  and check Claude's system-reminder output)

## Example

Full layout for a project adopting this pattern:

```
<project-root>/
├── CLAUDE.md                         # § Update protocol points here
├── .claude/
│   ├── settings.json                 # committed: hook registration
│   ├── settings.local.json           # local: permissions, gitignored via *.local
│   └── hooks/
│       └── pr-claude-md-check.sh     # committed, executable
```

Concrete working example: `pawn-au-chocolat` repo, created 2026-04-14.

## Notes

- Exit code 0 = non-blocking (hook just emits text). Exit code 2 = block the
  prompt with an error. Use 0 for reminders, 2 only for hard gates.
- The hook output is injected into the conversation as a system-reminder,
  exactly like the existing `claudeception-activator.sh` pattern.
- Project-level `settings.json` hooks **add to** global `~/.claude/settings.json`
  hooks - they don't replace them. Both fire on UserPromptSubmit.
- Keyword regex should be tight enough to skip casual uses ("pr" in "apr" or
  "spring" shouldn't match) but loose enough to catch natural phrasing. The
  provided regex requires a verb (`open|create|draft|raise|make`) or a command
  (`gh pr create`), not just the word "pr".
- `*.local` in `.gitignore` means `settings.local.json` stays private while
  `settings.json` is committed - put machine-specific permissions in
  `settings.local.json`, repo-wide hooks in `settings.json`.
- The hook fires on **every** prompt and pays the jq roundtrip regardless.
  Keep the match logic cheap; don't do network or disk work.

## References
- Claude Code hooks documentation (UserPromptSubmit, payload shape, exit codes)
- Related skill: `claudeception` - extracts reusable knowledge; the running
  log in CLAUDE.md covers the complementary case of project-scoped decisions
  that aren't reusable enough to be their own skill
