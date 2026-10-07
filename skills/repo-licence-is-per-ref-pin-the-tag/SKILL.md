---
name: repo-licence-is-per-ref-pin-the-tag
description: |
  When ingesting content (textbooks, datasets, curricula) from a git repository for a
  licence-sensitive build, the LICENSE file at HEAD can differ from the licence of an
  earlier release: projects relicense new editions (often to a NonCommercial variant)
  while older tags stay under the original open licence. Use when: (1) a repo's README
  or website advertises CC BY-SA / GFDL but LICENSE on `main` says NC, (2) you stamp a
  licence on every ingested node and export an 'open subset', (3) a shallow clone of the
  default branch silently pulled a relicensed edition. Fix: read LICENSE at the tag you
  actually clone, pin that commit in a SOURCE file, and have the ingester fail loudly if
  the checkout moves.
author: Claude Code
version: 1.0.0
date: 2026-09-11
---

# A repository's licence belongs to the ref, not the repo

## Problem
Oscar Levin's 'Discrete Mathematics: An Open Introduction' is widely cited as CC BY-SA.
On GitHub the default branch is the 4th edition, relicensed CC BY-NC-SA 4.0. An
ingester that reads LICENSE at HEAD and stamps it on every node quietly puts NC content
into an 'open subset' export, or, worse, stamps the old open licence from memory onto NC
content.

## Context / Trigger Conditions
- Textbook, dataset or curriculum repos with multiple editions or a 'v2' rewrite.
- A build that exports by licence (open vs NC layers) or that must stay redistributable.
- Symptom: website says one licence, LICENSE in the clone says another.

## Solution
1. `git tag` / releases: find the last tag under the licence you need (here `3rd-ed`).
2. Clone that ref: `git clone --depth 1 --branch <tag> <url>`; read LICENSE at that ref.
3. Record repo URL, tag, commit hash and the verbatim licence line in a SOURCE.txt next
   to the clone; stamp the normalised licence string on every node.
4. In the ingester, compare `git rev-parse HEAD` with the recorded commit and refuse to
   run (or warn loudly) if they differ, so a later `git pull` cannot change the licence
   of already-published output.
5. In the licence filter for exports, treat the string per node, never per source.

## Verification
`git -C sources/<slug> rev-parse HEAD` equals the recorded commit; `head -3 LICENSE`
at that ref matches SOURCE.txt; the open-subset export contains no node whose licence
string contains 'NC'.

## Notes
- GFDL and CC BY-SA are both 'open' but not mutually compatible for a single adapted
  work; an open subset of mixed GFDL/BY-SA/CC BY nodes is a collection with per-item
  licences, not one relicensable work.
- The same applies to Hugging Face datasets: the card's licence can change between
  revisions; pin the revision.
