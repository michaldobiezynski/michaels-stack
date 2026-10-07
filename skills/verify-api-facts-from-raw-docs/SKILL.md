---
name: verify-api-facts-from-raw-docs
description: |
  Verify exact API facts (package versions, constructor option names, env vars, endpoint
  fields, tool names) for planning or coding against a fast-moving SDK, broker API or MCP
  server. Use when: (1) a research brief or memory states API names that code will depend on,
  (2) WebFetch/WebSearch summaries give plausible but unsourced details (they invented an OAuth
  client id and a docker command on 25/09/2026), (3) the docs are a ReadMe.io site
  (docs.<vendor>.com/reference/...), (4) you fan research out to a teammate that spawns its own
  subagents. Covers raw-source recipes (npm registry, unpkg tarball README, raw GitHub,
  pkg.go.dev HTML, ReadMe.io embedded OpenAPI) and the delegation hand-back trap.
author: Claude Code
version: 1.0.0
date: 2026-09-25
---

# Verify API facts from raw sources, not summaries

## Problem
Summarising fetch tools paraphrase and sometimes fabricate: in one session WebFetch implied a
bare `docker run` for an MCP server that actually needs clone + build, and a WebSearch summary
produced an OAuth client id that exists nowhere in the vendor's pages. Code planned on such
facts fails at the first spike.

## Recipes (exact, fast)
- npm version and metadata: `curl -s https://registry.npmjs.org/<pkg>/latest`
  (npmjs.com pages often 403 to fetchers).
- Published README of an exact version: `https://unpkg.com/<pkg>@<version>/README.md`
  (the repo's main branch may document an unreleased breaking API, e.g. a new class name).
- GitHub docs: `https://raw.githubusercontent.com/<org>/<repo>/<branch>/README.md`, plus
  `LLMS.md` / `MIGRATION.md` when present (SDKs increasingly ship an LLM-oriented summary).
- Go APIs: curl `https://pkg.go.dev/<module>/<pkg>` and grep the HTML for
  `id="<Type>.<Field>"` spans and `func (c *Client) <Name>` signatures.
- ReadMe.io reference pages (docs.<vendor>.com/reference/<op>): the HTML embeds the full
  OpenAPI spec as inline JSON; grep it for `"servers"`, field names, `"required"` and response
  codes (this is how 207 Multi-Status on cancel-all was found).
- Count or absence checks (tool counts, removed fields such as `pattern_day_trader`) are done
  by grepping the raw text, never by asking a summariser.

## Delegation trap
If a teammate agent spawns its own subagents, their final hand-back can fail with "the agent
that spawned you is no longer running"; they then message the MAIN session directly, and the
teammate waits forever for reports it will never receive. When helpers' reports arrive at
main, tell the teammate so and give it the remaining work directly.

## Verification
Every fact in the plan carries its source URL; anything not found in a raw page is written as
UNVERIFIED and turned into an M0 spike rather than assumed.

## Note: ReadMe.io slugs do not match operation ids
Guessed slugs such as `/reference/deleteallorders` 404 while the operation (`deleteAllOrders`)
sits in the spec embedded on any page that does resolve (for example `/reference/postorder`).
Dump one page's embedded spec and read paths and operationIds from it instead of guessing URLs.
