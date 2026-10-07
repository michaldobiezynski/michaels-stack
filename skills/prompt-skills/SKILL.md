---
name: prompt-skills
description: Lists the user's chainable prompt-transform skill set (eli5, eli12, explain-analogy, plain-english, straight-answer, red-team, fact-check, fan-out, first-principles, honest-report, clean-output) with descriptions read live from disk. Use when the user asks "what prompt skills do I have", "list my skills", "show my modes", "which explain skills are there", or wants a reminder of the chainable skill set.
argument-hint: (no arguments)
---

# Prompt skills

Show the user their chainable prompt-transform skill set.

## Steps

1. Run `bash ~/.claude/skills/prompt-skills/scripts/list.sh`.
2. Present the script output verbatim in a fenced code block; it is already grouped and aligned. Add nothing except, if any line says MISSING, one sentence noting that skill has been removed or renamed.

## Maintenance

Group membership lives in `scripts/list.sh`. When a new transform or mode skill joins the set, append its directory name to the right `print_group` call. Descriptions and argument hints are read live from each skill's SKILL.md, so wording changes there need no edits here.
