---
name: summarize-content
description: |
  Summarise web pages, YouTube videos, PDFs, and local files using the summarize CLI tool.
  Use when:
  (1) the user asks to summarise a URL, article, web page, or blog post,
  (2) the user wants a summary of a YouTube video or podcast,
  (3) the user asks to summarise a local file (PDF, text, audio, video),
  (4) the user says "summarise this", "give me a summary", "TLDR", or "what does this page say",
  (5) the user wants to extract clean text from a web page or document.
  Uses the globally installed @steipete/summarize CLI tool.
author: Claude Code
version: 1.0.0
date: 2026-02-15
---

# Summarise Content with summarize CLI

## Problem

Quickly summarising web articles, YouTube videos, podcasts, PDFs, and other content
requires extracting text, handling transcripts, and producing concise output. The
`summarize` CLI tool handles the full extraction pipeline and LLM-powered summarisation.

## Context / Trigger Conditions

- User asks to summarise a URL or web page
- User wants a TLDR of an article or blog post
- User asks to summarise a YouTube video or podcast
- User wants to extract clean text from a URL or file
- User shares a link and asks "what does this say?"
- User wants to summarise a local PDF, text, audio, or video file

## Solution

### Important: Node.js Version

The `summarize` tool requires Node.js >= 22 (uses `node:sqlite`). It is installed under
Node v22.22.0 at `/Users/personal/.nvm/versions/node/v22.22.0/bin/summarize`.

If `summarize` fails with `No such built-in module: node:sqlite`, ensure Node 22 is
in the PATH by prefixing the command:

```bash
PATH="/Users/personal/.nvm/versions/node/v22.22.0/bin:$PATH" summarize "<url>"
```

In new terminal sessions with nvm default set to 22.22.0, `summarize` should work directly.

### Summarise a URL

```bash
summarize "<url>"
```

### Summarise with different lengths

```bash
summarize --length short "<url>"    # Brief summary
summarize --length medium "<url>"   # Moderate detail
summarize --length long "<url>"     # Detailed summary
summarize --length xl "<url>"       # Very detailed (default)
summarize --length xxl "<url>"      # Maximum detail
```

### Summarise a YouTube video

```bash
summarize --youtube auto "<youtube-url>"
```

### Extract clean text only (no summary)

```bash
summarize --extract "<url>"
```

### Summarise a local file

```bash
summarize /path/to/file.pdf
summarize /path/to/document.txt
```

### Summarise from stdin

```bash
cat file.txt | summarize -
echo "Some text to summarise" | summarize -
```

### Specify output language

```bash
summarize --lang en "<url>"   # English
summarize --lang de "<url>"   # German
```

### Get structured JSON output

```bash
summarize --json "<url>"
```

### Choose a specific LLM model

```bash
summarize --model google/gemini-2.5-flash "<url>"
summarize --model anthropic/claude-sonnet-4-5-20250929 "<url>"
summarize --model openai/gpt-4o "<url>"
```

### Include diagnostic metrics

```bash
summarize --metrics "<url>"
```

## Key Options Reference

| Option | Description |
| --- | --- |
| `--length <size>` | Summary length: short, medium, long, xl (default), xxl |
| `--youtube <mode>` | YouTube transcript: auto, web, no-auto, yt-dlp, apify |
| `--extract` | Return cleaned text only, no summary |
| `--json` | Output structured JSON |
| `--model <id>` | LLM model to use (e.g. google/gemini-2.5-flash) |
| `--lang <code>` | Output language: auto, en, de, etc. |
| `--format <fmt>` | Content format: md or text |
| `--timestamps` | Include timestamps in transcripts |
| `--metrics` | Include diagnostic information |
| `--timeout <dur>` | Timeout: 30s, 2m (default), etc. |
| `--max-output-tokens <n>` | Hard cap for LLM output tokens |
| `--force-summary` | Force summary even for short content |
| `--slides` | Extract slides from video |

## Verification

1. Run `summarize --help` to confirm the tool is installed
2. Run `summarize "<url>"` and check that a summary is produced
3. Output streams as markdown to the terminal

## Example

**Scenario**: User asks to summarise a blog post

```bash
summarize --length medium "https://example.com/blog/interesting-article"
```

**Scenario**: User wants a quick TLDR of a YouTube video

```bash
summarize --length short --youtube auto "https://www.youtube.com/watch?v=abc123"
```

**Scenario**: User wants clean extracted text from a page

```bash
summarize --extract "https://example.com/documentation"
```

## Notes

- Requires API keys for LLM providers to be configured (check `~/.summarize/config.json`)
- The tool requires Node.js >= 22 for full compatibility; may show warnings on older versions
- Default summary length is `xl`; use `--length short` for quick summaries
- Use `--extract` when you need the raw text rather than a summary
- Supports Firecrawl as a fallback for difficult-to-scrape sites (`--firecrawl auto` is default)
- The `--json` flag is useful for programmatic consumption of results
- Audio/video transcription uses Whisper as a backup when published transcripts are unavailable
