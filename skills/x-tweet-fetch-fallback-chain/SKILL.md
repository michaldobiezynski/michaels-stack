---
name: x-tweet-fetch-fallback-chain
description: |
  Read the content of an X/Twitter post (tweet) without authentication when the user
  shares an x.com or twitter.com status URL. Use when: (1) WebFetch on
  x.com/<user>/status/<id> returns HTTP 403 Forbidden, (2) you need the full text of a
  long-form post and the embed/syndication endpoint cuts it off mid-sentence, (3) you
  need resolved links or media info from a tweet. Fallback chain:
  cdn.syndication.twimg.com (works but truncates long posts) then api.fxtwitter.com
  (full text incl. note tweets, media, resolved URLs).
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# X/Twitter Post Fetch Fallback Chain

## Problem
X blocks unauthenticated page fetches: `WebFetch` on `https://x.com/<user>/status/<id>`
returns HTTP 403 Forbidden, so a shared tweet URL cannot be read directly.

## Context / Trigger Conditions
- User pastes an `x.com` or `twitter.com` status link and asks what it says
- WebFetch returns "The server returned HTTP 403 Forbidden" for the tweet URL
- A tweet fetched via the syndication endpoint ends mid-sentence (long-form/note tweet
  truncation)

## Solution
Extract the numeric status ID from the URL, then try in order:

1. **Syndication endpoint** (X's own embed API, no auth):
   `https://cdn.syndication.twimg.com/tweet-result?id=<id>&token=a`
   - The `token` parameter is required but its value is arbitrary; omitting it fails.
   - Returns author, date, text, media metadata.
   - **Gotcha**: truncates long-form posts (>280 display chars) mid-sentence with no
     ellipsis, so the cut is easy to miss. If the text ends abruptly, go to step 2.

2. **fxtwitter API** (third-party mirror of the public tweet API):
   `https://api.fxtwitter.com/<user>/status/<id>`
   - Returns the complete text including note tweets, resolved (untruncated) URLs,
     media descriptions, and post date.
   - The `<user>` segment is not validated strictly; the ID is what matters.

Both endpoints work with plain `WebFetch` with a prompt asking for full text, author,
date, links, and media.

## Verification
The fxtwitter response text should read as complete sentences and include any trailing
call-to-action or links that the syndication version cut off. Cross-check author and
date match between the two endpoints.

## Example
For `https://x.com/kyutai_labs/status/2092254286772080768?s=20`:
- WebFetch on x.com: 403.
- Syndication endpoint: returned text ending abruptly at "It learns pretty damn".
- `https://api.fxtwitter.com/kyutai_labs/status/2092254286772080768`: returned the full
  multi-paragraph post plus the GitHub link it referenced.

## Notes
- Strip tracking params (`?s=20`) before extracting the ID; the ID is the long numeric
  segment after `/status/`.
- fxtwitter is a third-party service (also reachable by swapping `x.com` →
  `fxtwitter.com` in the URL for a human-readable embed); it can rate-limit or go down,
  in which case `api.vxtwitter.com` is an equivalent alternative.
- Replies/threads: these endpoints return the single status only, not the whole thread.
- Private/protected accounts are not accessible by any of these routes.
