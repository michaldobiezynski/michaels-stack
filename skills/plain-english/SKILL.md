---
name: plain-english
description: Rewrites text or explains a topic for a smart adult who is not a specialist, jargon-free and precise without being childlike. Use when the user asks for plain English, "explain for a layperson", "no jargon", "explain to a non-technical stakeholder", or chains it after another skill or command to de-jargonise that command's output.
argument-hint: [topic or text; blank = rewrite your previous answer]
---

# Plain English

Explain the input for an intelligent adult outside the field.

## Input

1. If arguments were given, explain that topic or rewrite that text.
2. If no arguments were given, rewrite your previous answer in this conversation.
3. When chained after another skill or command, treat that command's output as the input.

## Style

- Audience: a founder reading an engineering doc, a doctor reading a legal clause. Smart, but not in this field.
- Replace jargon with everyday equivalents. Where a term must stay because the reader will meet it again, define it once in passing.
- Keep the nuance a child-level version would drop: caveats, trade-offs, and rough orders of magnitude survive the rewrite.
- Short paragraphs, plain sentence structure, active voice. No headers unless the input is long.
- Do not pad: the rewrite should usually be shorter than the original.

## Output

Only the explanation or rewrite itself, no preamble. British English.
