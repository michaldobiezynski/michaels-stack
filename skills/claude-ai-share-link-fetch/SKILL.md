---
name: claude-ai-share-link-fetch
description: |
  Read the content of a public claude.ai/share/<uuid> shared-conversation link from
  Claude Code. Use when: (1) WebFetch on a claude.ai/share URL returns only the SPA
  shell (content is effectively just the word "Claude"), (2) curl on claude.ai gets a
  Cloudflare 403, (3) agent-browser in headless mode lands on a Cloudflare
  "Just a moment..." interstitial for a claude.ai page. Solution: headed agent-browser
  (AGENT_BROWSER_HEADED=1) passes the Cloudflare challenge automatically, no login and
  no interactive click needed; delegate to a subagent that returns a distilled summary.
author: Claude Code
version: 1.0.0
date: 2026-08-28
---

# Fetching claude.ai share links

## Problem

claude.ai shared conversations (`https://claude.ai/share/<uuid>`) are public, but none of the cheap fetch paths work: the page is a client-rendered SPA behind Cloudflare, so tools that read raw HTML see nothing and headless browsers get challenged.

## Context / Trigger Conditions

- WebFetch on the share URL succeeds but the extracted content is empty ("contains only the word Claude" / SPA shell).
- `curl` against claude.ai returns a Cloudflare 403.
- agent-browser in default headless mode shows a Cloudflare "Just a moment..." challenge page instead of the transcript.

Note the distinction: `claude.ai/code/artifact/<uuid>` URLs ARE directly fetchable via WebFetch (documented exception); `claude.ai/share/<uuid>` chat links are not.

## Solution

1. Run agent-browser in **headed** mode: `AGENT_BROWSER_HEADED=1`. The Cloudflare challenge clears automatically, with no interactive click and no login (share links are public).
2. Scroll the whole conversation before extracting; long transcripts render progressively.
3. Delegate the whole read to a `sonnet` subagent using the agent-browser skill and have it return a structured distilled summary (idea, users, features, implementation details, conclusions, key quotes), never the raw transcript, to keep the main context small.
4. Close the browser when done.

## Verification

The subagent's snapshot shows the actual chat turns (user and Claude messages) rather than "Just a moment..." or a bare "Claude" title. Verified 28/08/2026 on a real share link.

## Notes

- Headless failed and headed passed in the same session; if Cloudflare later starts challenging headed sessions too, a persistent profile via [[playwright-cdp-persistent-browser]] is the next escalation.
- Do not try to bypass a challenge that persists in headed mode; ask the user to export the conversation instead.
