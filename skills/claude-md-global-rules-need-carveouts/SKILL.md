---
name: claude-md-global-rules-need-carveouts
description: |
  Checklist for adding or editing global MUST/always/never-style rules in CLAUDE.md or
  rules files. Use when: (1) adding quality gates, verification mandates, or style bans
  to CLAUDE.md, (2) a stated rule keeps being violated or overtriggering (e.g. tests run
  for docs-only edits, subagents stalling on ask-the-user rules), (3) reviewing someone
  else's CLAUDE.md for slop guardrails. Current models follow instructions literally, so
  every unconditional rule needs explicit context carve-outs or it misfires.
author: Claude Code
version: 1.0.0
date: 2026-07-03
---

# CLAUDE.md Global Rules Need Context Carve-outs

## Problem

Rules added to CLAUDE.md as unconditional MUSTs ("always verify before claiming done",
"never use generic fonts", "always ask clarifying questions") misfire on
literal-instruction-following models: they force fake verification on docs-only edits,
stall subagents waiting for a user who isn't there, or ban words that are accurate
technical terms. The rule author pictured the common case; the model applies the rule
everywhere.

## Context / Trigger Conditions

- Adding definition-of-done, review-gate, taste, or clarification rules to CLAUDE.md
- A rule is being violated repeatedly (often a bloat/dilution symptom, not disobedience)
- Ceremony appearing on trivial tasks: tests for comment fixes, review subagents for renames
- Subagents or workflow stages stalling on rules that require user input

## Solution

Before shipping any global MUST-rule, test it against these four contexts and add the
carve-out where it fails:

1. **No-runtime-surface exemption** (for verification/done rules): docs, comments,
   renames, pure test edits have nothing to "run". Exempt them explicitly and name the
   cheap static check to use instead (build, lint, typecheck).
2. **Non-interactive carve-out** (for any rule requiring user input): subagents,
   workflow stages, scheduled and loop runs have nobody to ask. Instruct: state
   assumptions or pick the most defensible option, note it, and proceed.
3. **Domain scoping** (for taste/writing bans): scope bans to generated prose and
   user-facing copy; exclude code identifiers, product names, quoted material, and
   literally-accurate technical uses ('seamless failover').
4. **Existing-convention override** (for design/style rules): a project's established
   design system or codebase convention beats the global aesthetic rule; say so in the
   rule itself.

Then verify the edit the same way it was discovered: spawn two fresh-context reviewers
(one for contradictions with existing rules and dangling skill/agent references, one
specifically hunting overtriggering with concrete misfire scenarios), and action only
findings that come with a reachable misfire scenario.

## Verification

Reviewer findings must themselves be checked against ground truth before acting: in the
originating session an opus auditor confidently claimed the `security-reviewer` agent
did not exist — it did. One wrong finding in an otherwise-strong review is normal;
verify, don't transcribe.

## Example

Before: "A change is done when you have exercised it and observed the result."
After: "A change **with a runtime surface** is done when you have exercised it and
observed the result... Changes with no runtime surface (docs, comments, renames, pure
test edits) are exempt: state what you changed and run the cheap static check where one
exists."

## Notes

- Bloat is the other half of the failure: Anthropic's docs state bloated CLAUDE.md files
  cause instructions to be silently ignored, so pay for every added rule by cutting
  reference material that duplicates a skill.
- Dial back CRITICAL/MUST emphasis generally — current models overtrigger on aggressive
  language written for older, less-compliant models.

## Compressing an oversized CLAUDE.md

Worked examples are the cheapest cut: models don't need a good/bad pair to follow a
one-sentence rule, so a 559-line file compresses to ~180 by deleting examples and
collapsing multi-bullet elaborations into dense sentences (rules survive, prose doesn't).
Verify the compression with a fresh-context reviewer doing a rule-by-rule diff of old vs
new, restricted to three finding types: LOST RULE (behavioural instruction with no
equivalent), MEANING DRIFT (stronger/weaker/narrower in a behaviour-changing way), and
BROKEN REFERENCE. In the originating session this review caught a silently-dropped
guard on a destructive action (confirm before deleting remote branches on shared repos)
that self-review missed. Keep the old version reachable in git so the diff is trivial.

## References

- https://code.claude.com/docs/en/best-practices (concise CLAUDE.md, evidence-based done, fresh-context review)
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices (overtriggering on aggressive language, over-engineering snippet)
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents (instruction altitude)
