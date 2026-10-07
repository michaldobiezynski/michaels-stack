---
name: explain-analogy
description: Explains a topic or previous answer through one extended real-world analogy, explicitly mapping each part of the concept onto the analogy. Use when the user asks for an analogy or metaphor, says "explain it like something I know", or chains it after another skill or command to reframe that command's output.
argument-hint: [topic or text; blank = reframe your previous answer]
---

# Explain by analogy

Carry the whole explanation with one extended real-world analogy.

## Input

1. If arguments were given, explain that topic or rewrite that text.
2. If no arguments were given, reframe your previous answer in this conversation.
3. When chained after another skill or command, treat that command's output as the input.

## Method

1. Pick one familiar domain for the analogy (kitchens, football, traffic, school, a post office). Choose it for structural fit, not novelty.
2. Tell the analogy as a short, casual narrative, a paragraph or two at most.
3. Map the parts explicitly: 'the X here is the Y in our problem' for each moving part that matters.
4. Close with one sentence on where the analogy breaks down, so it cannot mislead.

## Style

Casual, human-readable, short. One analogy only; do not stack metaphors. Keep it accurate: if the analogy forces a false claim, change the analogy.

## Output

Only the analogy explanation itself, no preamble. British English.
