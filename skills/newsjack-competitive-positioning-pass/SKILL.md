---
name: newsjack-competitive-positioning-pass
description: |
  Run a "find similar projects and tell me how to improve mine" pass on a product using the
  Newsjack PR skill pack (elvisun/newsjack) without its CLI or a Medialyst login. Use when:
  (1) the user says "use Newsjack" for competitor research, positioning, launch timing or
  "how do I improve/market my project", (2) `which newsjack` finds nothing and no
  mcp__newsjack tools exist (Newsjack is a plugin of Markdown skills, NOT a repo-similarity
  tool), (3) `news-search` has to run in host-search fallback mode. Covers the plugin
  install path that avoids the interactive curl installer, which skills need no credentials,
  the three-sweep fan-out, live verification of subagent numbers, and running the
  pr-strategist decision tree in the main loop.
author: Claude Code
version: 1.0.0
date: 2026-09-20
---

# Newsjack competitive positioning pass

## Problem

"Use Newsjack to find similar projects" sounds like a GitHub-similarity tool. It is not:
Newsjack (https://github.com/elvisun/newsjack, MIT) is ~30 plain-Markdown PR skills plus an
optional Go CLI. Nothing local matches `newsjack`, and the curl installer
(`curl -fsSL newsjack.sh | bash`) hands off to an interactive `newsjack setup`. The useful
skills for "similar projects + improve mine" are `news-search`, `pr-strategist` and
`newsworthiness-check`, and only `news-search` benefits from credentials.

## Trigger conditions

- User names Newsjack for research, positioning, launch or PR on one of their projects.
- `which newsjack` empty, no `mcp__newsjack__*` tools, no skill named newsjack.
- A Newsjack skill says "run `newsjack news search`" and the CLI is absent.

## Solution

1. **Install as a plugin, not via the curl script** (reversible, no interactive setup):
   ```bash
   claude plugin marketplace add elvisun/newsjack
   claude plugin install newsjack@newsjack --scope user
   ```
   The `/pr-strategist` etc. slash commands appear in the NEXT session. In the current one,
   `git clone --depth 1 https://github.com/elvisun/newsjack` into the scratchpad and follow
   `skills/<name>/SKILL.md` directly; they are instructions, not code.
2. **Credentials are optional.** `pr-strategist`, `newsworthiness-check`, `angle-generator`,
   `headline-generator`, `meanest-editor` need nothing. `news-search` prefers Medialyst
   (`newsjack login`, needs the CLI) and otherwise falls back to WebSearch/WebFetch; the
   skill requires you to recover `published_at` from each page and to say "host search,
   reduced freshness confidence". `newsjack-monitor-setup` and `coverage-tracker-setup`
   need the CLI; offer them as follow-ups.
3. **Build the product dossier first** (memory file, landing copy, repo, screenshots, live
   URLs, real signup counts from the production DB, repo visibility). pr-strategist runs on
   evidence and "hypothesises, doesn't interrogate".
4. **Fan out three sonnet subagents in parallel**, each returning a compact table:
   - commercial alternatives (Steam, consoles, hardware, licensed products);
   - open-source/indie lookalikes (`gh search repos`, itch.io);
   - `news-search` in fallback mode for live pegs (dated, attributed, "Live pegs" section).
5. **Verify before quoting.** Steam counts via the `verify-steam-traction-appreviews-api`
   skill; GitHub stars/push dates via `gh repo view`; any single-outlet peg via a second
   WebSearch; any "X has no feature Y" claim via a direct search (an agent wrongly said
   Lichess has no 3D board: it has pseudo-3D pieces, just no animated captures).
6. **Run pr-strategist in the main loop** on the combined evidence: Step 0 short-circuits,
   Step 1 diagnose (audience, nearest dated moment, buyer), Step 2 positioning gate
   (alternatives, the one thing they can't do, proof, wedge), Step 3 newsworthiness gate,
   Step 4 archetype menu (main play + two backups), Step 5 the 90% default path, Step 6 one
   metric. Product improvements fall out of the gaps the sweeps found.
7. Report with confidence labels; offer `/newsjack-monitor-setup` and `newsjack login` as
   next steps rather than running them.

## Verification

20/09/2026: plugin install printed "Successfully installed plugin: newsjack@newsjack (scope:
user)"; three sweeps returned in ~10 minutes; every Steam figure matched the live API and
every GitHub figure matched `gh repo view`; the news agent's strongest peg (a licensed $999
robotic wizard's chess set) was corroborated by four further outlets.

## Notes

- Keep Newsjack's ETHICS.md in mind: no tragedy pegs, no invented proof.
- Do not brand a product with a third-party trademark when riding a licensed-IP peg;
  describe the inspiration in editorial copy only.
- Related: `verify-steam-traction-appreviews-api`, memory `reference-newsjack-plugin`.

## References

- https://github.com/elvisun/newsjack (README "What runs where" table, docs/getting-started.md)
- https://medialyst.ai/blog/newsjack-install-walkthrough
