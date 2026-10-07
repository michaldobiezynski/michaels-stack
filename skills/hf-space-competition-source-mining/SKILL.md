---
name: hf-space-competition-source-mining
description: |
  Mine a competition/hackathon hosted as a Hugging Face Gradio Space by reading its source
  repo instead of scraping the page. Use when: (1) given an *.hf.space URL or an HF Space
  link for a challenge and you need rules/scoring/deadlines, (2) curl of the hf.space page
  returns an empty Gradio JS shell with no content, (3) a challenge scores submissions
  automatically and you want an offline scorer before spending a limited submission budget,
  (4) you need the exact submission CSV/file format a challenge's parser will accept.
  Covers resolving the subdomain to a repo id, fetching tab sources and evaluation code,
  vendoring the scorer with attribution, and empirically probing scoring mechanics.
author: Claude Code
version: 1.0.0
date: 2026-08-26
---

# HF Space competition source mining

## Problem

Challenges hosted as Gradio Spaces render everything client-side: `curl` of the
`*.hf.space` URL returns a JS shell with zero challenge content. Meanwhile the Space's
source repo is usually public and contains far more than the page shows: the full rules
and FAQ text, the submission parser, the actual scoring code, submission templates, and
config constants (submission limits, private groundtruth/leaderboard repo names).

## Context / Trigger Conditions

- A challenge URL like `https://<org>-<space-name>.hf.space/` or `huggingface.co/spaces/...`
- Rendered page fetch yields only `window.__gradio_mode__ = "app"` boilerplate
- The challenge has automated scoring and a capped submission budget

## Solution

1. **Resolve the subdomain to a repo id** (subdomain munges `/` and `_` to `-`, so guess-
   reconstruction is unreliable): `curl -s https://huggingface.co/api/spaces/<org>/<name>`
   or search `https://huggingface.co/api/spaces?search=<fragment>`. The JSON's `subdomain`
   field confirms the match; `siblings` lists every source file; `cardData` gives licence,
   linked `datasets`, and OAuth/gating flags.
2. **Fetch the readable source**, one raw URL per file:
   `https://huggingface.co/spaces/<org>/<name>/raw/main/<path>`. Priority order: `tabs/*.py`
   or wherever the UI text lives (about/rules/faq are usually markdown strings in Python),
   `evaluation.py`/scoring modules, `config.py` (submission limits, private repo names,
   groundtruth filename), `static/templates/*` (official submission templates), submit-tab
   code (exact server-side validation: accepted file types, URL prefix checks, quota logic).
3. **Vendor the evaluation code** into your kit verbatim with an attribution header
   (source URL, commit sha, date, licence from `cardData.license`; only if the licence
   permits, e.g. CC-BY/MIT/Apache). Wrap it from a separate CLI; never edit the vendored
   file, so it stays diffable against upstream.
4. **Probe the mechanics empirically**, not just by reading: craft minimal CSVs and score
   them against hypothesis ground truths matching the loader's format. Set-equality and
   threshold-sweep details create real traps (verified example: a scorer comparing
   `frozenset` of variants per row gives FULL credit only when a compound-het pair is in
   ONE row; the same two variants as separate rows scored 50/100 instead of 100/100).
5. **Check the linked dataset via API even when gated**:
   `https://huggingface.co/api/datasets/<org>/<name>` leaks the card description (dates,
   sizes, quickstart) even when file access requires the gated-access form.
6. Watch for private repos named in config (groundtruth, leaderboard): you cannot read
   them, but their filenames and the loader code tell you the answer-key schema, which is
   what an offline what-if scorer needs.

## Verification

This workflow produced, in one session: full rules/scoring/deadline extraction for a
challenge whose page curl was empty, a working offline scorer (validated against the
official template: expected 100 pts/F-max 1.0, observed exactly that), and an empirically
confirmed scoring trap worth 50 points.

## Gated dataset access (verified 26/08/2026)

- **Check for existing access FIRST**: an authenticated raw fetch
  (`curl -H "Authorization: Bearer $(cat ~/.cache/huggingface/token)" .../raw/main/README.md`
  returning 200) or the `ACCEPTED` row at https://huggingface.co/settings/gated-repos means
  the account already went through the gate; skip everything below.
- **There is NO programmatic route to request gated access.** Verified exhaustively:
  `POST /api/datasets/<id>/ask-access` and `user-access-request` variants 404;
  `huggingface_hub` 1.24.0 has only repo-OWNER-side access methods
  (accept/reject/cancel/grant); the real form posts to the SITE route
  `https://huggingface.co/datasets/<id>/ask-access` (found by fetching the
  `RepoGatedModal-*.js` chunk via `/front/build/<moonSha>/index.js`), which requires
  session-cookie auth plus a hidden `csrf` input; Bearer tokens are ignored on site
  routes (SSR renders `isLoggedIn:false`, POST 404s).
- **Working fallback**: `agent-browser --session-name hf --headed open
  "https://huggingface.co/login?next=<dataset-path-urlencoded>"`, have the user log in
  themselves (password never transits the agent), then drive the gate form via
  snapshot/fill/check/click. Watch for a stale headless daemon: `--headed` is silently
  ignored unless you `agent-browser close` first. Read the gate's exact fields beforehand
  from `cardData.extra_gated_fields` in `/api/datasets/<id>` and get the user's explicit
  sign-off before ticking legal attestation boxes in their name.
- The gate API card leaks the form schema anonymously; the file tree
  (`/api/datasets/<id>/tree/main` with token) gives sizes so you can download a minimal
  working set instead of the headline ~85 GB.

## Notes

- Upload feedback from auto-scored challenges is an oracle: with a capped budget, treat
  each submission as an information-maximising probe, and ledger them.
- The Space sha from the API pins what you read; re-check `lastModified` near deadlines,
  since organisers edit rules tabs in place.
- Licence check before vendoring is not optional; if the Space card has no licence, quote
  minimally and link instead.

## References

- HF Hub API endpoints used: `/api/spaces/<id>`, `/api/spaces?search=`, `/api/datasets/<id>`,
  and `/spaces/<id>/raw/<rev>/<path>` (verified working 26/08/2026)
