---
name: verify-steam-traction-appreviews-api
description: |
  Re-check Steam review counts and ratings that a research subagent, web page or memory
  reported, using Steam's public appreviews JSON endpoint, before quoting them in competitive
  research. Use when: (1) a subagent's competitive survey lists Steam review totals or
  "X% positive" figures, (2) two sources disagree on a game's review count, (3) a title shows
  0 reviews and you need to know whether that is a wrong appid, an unreleased listing, or
  real absence of traction, (4) you need live traction for a batch of appids in one shell
  loop. Covers the three traps observed on 20/09/2026: English-only counts understating
  totals by 30-50%, the endpoint returning an all-zero summary when language and
  purchase_type are omitted, and "coming soon" listings legitimately returning zero.
author: Claude Code
version: 1.0.0
date: 2026-09-20
---

# Verify Steam traction with the appreviews API

## Problem

Web-research subagents report Steam review counts from store pages, SteamDB snapshots or
articles. On 20/09/2026 two agents' figures for ten chess titles were understated by 30 to 50
percent against the live API, one rating was a critic score presented as a user score, and one
title was reported with 237 reviews when its Steam listing had none. Quoting those numbers
would have misled a positioning decision.

## Trigger conditions

- A subagent or page says "N reviews, X% positive" for a Steam game.
- You are about to put Steam traction numbers in a table or a recommendation.
- A game shows 0 reviews and you are tempted to call it "no traction".

## Solution

Run the bundled script once per batch, then use its numbers instead of the reported ones:

```bash
~/.claude/skills/verify-steam-traction-appreviews-api/scripts/steam_reviews.sh \
  2021910:"FPS Chess" 1972440:"Shotgun King" 3202290:"Chess Arena"
```

It calls, for each appid:

- `https://store.steampowered.com/appreviews/<appid>?json=1&language=all&purchase_type=all&num_per_page=0`
  and reads `query_summary.total_reviews`, `total_positive`, `review_score_desc`.
- `https://store.steampowered.com/api/appdetails?appids=<appid>&filters=basic,release_date`
  to print the listing's name and whether it is `coming_soon`.

Rules learnt:

1. **Always pass `language=all` and `purchase_type=all`.** With no parameters the summary comes
   back with `total_reviews: 0` for a game that has 44k reviews. `language=english` gives the
   English-only count, which is what the agents had quoted (30,948 vs 44,213 for FPS Chess).
2. **Treat 0 reviews as a question, not an answer.** Check the appdetails release state. Chess
   Arena (3202290) returned 0 because the Steam listing is "coming soon"; the agent's 237
   figure came from elsewhere. A wrong appid also returns 0 or a different `name`.
3. **User score is not critic score.** An agent reported Gambonanza as "critics ~57% mixed";
   the live user summary was 75% positive of 1,704. Say which one you mean.
4. **Print the Steam `name` next to each row** so a mistyped appid is caught by eye.

## Verification

Observed 20/09/2026, all-language totals: FPS Chess 44,213 (84%), Shotgun King 7,442 (91%),
Gambonanza 1,704 (75%), Battle Chess: Game of Kings 377 (52%), Chess Gambit 4 (25%). Rankings
matched the agents' reports; magnitudes did not.

## Notes

- `num_per_page=0` returns the summary only, so the loop is fast and pulls no review text.
- The endpoint is unauthenticated and rate-limited generously; ten titles took under two
  seconds.
- Review counts are not sales. Shotgun King's maintainer reported over 500k copies against
  7.4k reviews. Use reviews for ranking and rough scale, never as unit sales.

## References

- Steamworks docs, User Reviews - Get List: https://partner.steamgames.com/doc/store/getreviews
- Store app details endpoint (undocumented but stable): https://store.steampowered.com/api/appdetails?appids=<id>
