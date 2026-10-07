---
name: eli12
description: Explains a topic or rewrites text as if the reader were twelve years old, in a short, simple, casual, human-readable way. Use when the user says "eli12", "explain it simply", "make this simpler", "dumb this down", or chains it after another skill or command to simplify that command's output.
argument-hint: [topic or text; blank = simplify your previous answer]
---

# ELI12

Explain the input as if the reader were a twelve-year-old.

## Input

1. If arguments were given, explain that topic or rewrite that text.
2. If no arguments were given, rewrite your previous answer in this conversation.
3. When chained after another skill or command (e.g. `/summarize-content <url>` then `/eli12`), treat that command's output as the input.

## Style

- Short: a few sentences up to two small paragraphs. No headers, no tables, no bullet walls.
- Simple: everyday words a twelve-year-old knows. If a technical term is unavoidable, explain it in the same sentence.
- Casual and human: write like a friendly older sibling explaining something cool, not a textbook.
- Concrete: one everyday example or comparison beats an abstract definition.
- Honest: simplify by leaving detail out, never by saying something false.

## Output

Only the explanation itself. No preamble ('Sure, here is a simpler version') and no closing summary. British English.
