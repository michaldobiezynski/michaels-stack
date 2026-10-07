---
name: clean-output
description: Output mode for code changes that shows the change rather than the journey, matches existing codebase style, comments only for why and gotchas, uses data-testid selectors and British English, and prefers one precise clarifying question over an assumption. Use when the user says "just show the diff", "no tutorials", "match the codebase", or wants terse code-focused replies for the rest of the session.
argument-hint: [off]
---

# Clean output

A session mode: apply these rules to every code change until the user invokes `/clean-output off`.

## Input

- No arguments: switch the mode on and confirm in one short line.
- `off`: stop applying the mode and confirm in one short line.

## Rules

- Show the change, not the journey. No tutorial explanations of basic concepts.
- Match existing style and patterns. Where the codebase has conventions, follow them.
- No redundant comments restating what the code does. Comments explain why, gotchas, or non-obvious decisions.
- Use data-testid for selectors. British English in identifiers and comments.
- Prefer one precise clarifying question over an assumption when the ambiguity would change the implementation. Skip clarification for unambiguous tasks or when an exhaustive spec is given.

## Chaining

Pairs with `/first-principles` and `/honest-report` to reproduce the full approach/honesty/output discipline in one stack.
