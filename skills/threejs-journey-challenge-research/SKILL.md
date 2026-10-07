---
name: threejs-journey-challenge-research
description: |
  Research the Three.js Journey challenges (threejs-journey.com/challenges) and their entries for
  award-level three.js / WebGL / WebGPU reference work: find every challenge, its winners and each
  entry's live URL, choose what to study, capture it, and turn it into techniques to adopt. Use when:
  (1) asked to research, screenshot or record Three.js Journey challenges or entries, (2) looking for
  "challenge-winning" references for a 3D site, game or interface, (3) agent-browser, Playwright or curl
  gets HTTP 429 or an o2switch "Tiger Protect" page from threejs-journey.com, (4) /challenges/ (with a
  trailing slash) returns 404. Pairs with webgl-demo-capture (capturing) and webgl-award-rubric (judging).
author: Claude Code
version: 1.0.0
date: 2026-09-27
---

# Researching Three.js Journey challenges

## Problem
The challenge pages are the index to ~24 themed challenges and hundreds of live demos, but the site
rate-limits browsers hard, the entries live on other hosts, and raw captures are useless until they are
distilled into techniques you can adopt.

## Context / Trigger Conditions
- The user points at https://threejs-journey.com/challenges or a challenge such as
  https://threejs-journey.com/challenges/024-stylized-nature and asks for research, screenshots or clips.
- Opening threejs-journey.com in agent-browser/Playwright from this machine returned **HTTP 429** after a
  handful of requests (o2switch Tiger Protect, 27/09/2026). It is a rate limit, not an auth wall.

## Solution
1. **Never drive a browser at threejs-journey.com.** Read its pages with **WebFetch** (it runs from
   another network and was not rate-limited): `https://threejs-journey.com/challenges` for the list and
   `https://threejs-journey.com/challenges/<nnn>-<slug>` for each challenge. No trailing slash on
   `/challenges` (the slashed form 404s). If the user offers to log in, it is not needed: the pages are public.
2. **Build one master list** (`entries.md`): per challenge, the three winners (ranks 1-3) and every
   entry's title, author and live URL, plus a shortlist of entries close to your own theme. A cached copy
   from 27/09/2026 (24 challenges, all 26 #024 entries, every challenge's winners and a themed shortlist)
   is in `reference/entries-2026-09-27.md`; refetch only if it is stale for the task.
3. **Choose what to study, in this order:** the winners of every challenge (they show what the judges
   reward); entries on your own theme; for interfaces, UI-heavy challenges (#011 Futuristic UI, #016
   Tamagotchi, #001 Game Boy); for games, game-like entries (#004/#014 Halloween, #006 Christmas's Great
   Gift Hunt, #017 Island Battleship, #022 Spaceship).
4. **Capture** each entry with the `webgl-demo-capture` skill: headless, one browser per agent, at most two
   capture agents at once, a folder per entry with `1-load.png`, `2-after.png`, `clip.webm` and a report.
   Batch 8-10 entries per Sonnet subagent (about 20-25 minutes and ~220k tokens each).
5. **Distil** with the `webgl-award-rubric` skill: for each technique, which entries show it (with a
   High/Moderate/Low confidence label: seen, inferred, guessed), what it would take in your stack, and a
   ranked backlog (impact on a judge's first minute, visibility, effort).
6. **Licensing and honesty:** never copy an entry's code or assets. If an entry links its source, note the
   repo and its licence (one #024 entry, Hex Tile Board, is AGPL-3.0) and re-implement the technique
   yourself. Say plainly which entries failed to load, were login-gated, or crashed.

## Verification
- The master list has a URL for every entry you plan to capture, and every capture folder has non-zero
  files (`ls -la`).
- The synthesis cites entries by name for every technique it recommends.

## Example
Chess Explosion (27/09/2026): WebFetch of /challenges and /challenges/024-stylized-nature built the
master list; four Sonnet capture agents covered all 26 Stylized Nature entries, the Castle and Island
winners and eight themed entries, then two more covered cosy-room/isometric winners and #024 17-26.
Adopted from them: hover route preview and contextual prompts (Lumen Vale), onboarding note + quest
tracker (Coral Shallows, Utanomori), layered sound with separate switches (Drysland), tilt-shift + grain
(Lego, AEDENA), candle flames and warm light pools (Cozy Reading Room), glass crystal ball (Terrarium),
a hidden creature to find (Floating Island), loading progress (Lumen Vale, Caatinga).

## Notes
- Most winners run WebGL2 even where WebGPU is available; React Three Fiber + drei is common (several
  load drei's HDRIs from the pmndrs drei-assets CDN).
- Many entries reset to their title screen under fast automated drags or wheel input; do not read that as
  a site bug without a slow, human-paced retry.
- Some entries are login-gated (SATORI) or Electron-only (Abstract Hiking crashes to about:blank in a
  browser tab); note and move on.
- Keep research agents' browsers headless; headed windows interrupt the user.
