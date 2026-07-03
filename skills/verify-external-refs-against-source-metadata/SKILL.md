---
name: verify-external-refs-against-source-metadata
description: |
  Verify human-written labels/comments that describe an EXTERNAL resource
  (YouTube video IDs, URLs, package names, dataset/doc links) against that
  resource's OWN metadata, instead of trusting the label or an LLM
  web-search summary. Use when: (1) reviewing config/data where a comment
  names the show/author/title/host for a URL or ID (e.g. a speakers.yaml
  entry "# Diary of a CEO (host: Steven Bartlett)" beside a YouTube link),
  (2) you are about to wire/act on a human-written label, (3) two research
  or web-search agents return CONFLICTING identities for the same external
  resource and you need to resolve it (do not average them), (4) a label
  may have drifted or been wrong from the start. Solution: query the
  resource's own metadata deterministically (yt-dlp --print, HTTP/registry
  API) and treat that as ground truth. Catches mislabelled references that
  would otherwise be propagated into config or downstream logic.
author: Claude Code
version: 1.0.0
date: 2026-05-28
---

# Verify external-reference labels against the source's own metadata

## Problem

Config and data files routinely reference external resources by an opaque
ID or URL with a human-written label alongside:

```yaml
- url: https://www.youtube.com/watch?v=QBznUHAopxU
  # Diary of a CEO 2025 (host: Steven Bartlett)
```

The label is unverified prose. It can be wrong from the start, or drift as
the resource changes. Acting on the label (wiring it into logic, building a
speaker/candidate list, generating attributions) silently propagates the
error. Worse: when you ask an LLM web-search agent to "confirm who is in
video X", it can confidently match the right *title* to the *wrong* source
(wrong podcast, wrong host), because titles are reused across shows and
search snippets are ambiguous. Two agents can disagree, and averaging or
trusting the more confident one gives a wrong answer.

## Context / Trigger conditions

- Reviewing config/data where a comment or field names the author / show /
  host / title for a URL or opaque ID.
- About to wire or act on a human-written label for an external resource.
- A YAML/JSON/code comment asserts a fact about an external link.
- Two agents (or an agent and a comment) DISAGREE on a resource's identity.
- A label might be stale (the resource was re-uploaded, renamed, or the
  comment was copy-pasted from a similar entry).

## Solution

Go to the primary source and read its own metadata. Treat that as ground
truth over any comment or LLM summary. Pick the deterministic query for the
resource type:

- **YouTube video/playlist:**
  ```bash
  yt-dlp --skip-download --no-warnings \
    --print "channel=%(channel)s" --print "uploader=%(uploader)s" \
    --print "title=%(title)s" "https://www.youtube.com/watch?v=<ID>"
  ```
  The `channel` / `uploader` fields are authoritative for "which show / who
  published this", which is exactly what host/source labels usually claim.
- **Generic URL:** `curl -sIL <url>` (final URL + content-type after
  redirects); fetch the page `<title>`/`og:site_name` if needed.
- **Package:** query the registry API (npm `npm view <pkg> name version`,
  PyPI `https://pypi.org/pypi/<pkg>/json`) rather than trusting a lockfile
  comment.

When two agents disagree, do NOT average or pick the more confident one.
Run the deterministic query yourself and let the primary source arbitrate.

## Verification

The query returns the resource's real identity. Compare it field-by-field
against the label. If they differ, the label is wrong: fix the label AND
anything derived from it (lists, attributions, downstream wiring). Re-run
any test/gate that consumed the old label.

## Example

A config review claimed a YouTube ID was a "Diary of a CEO" episode hosted
by Steven Bartlett, and that host had been wired into a per-video speaker
list. One review agent confirmed it (matched the title to DOAC); a second
agent said it was a different show. Resolved deterministically:

```bash
$ yt-dlp --skip-download --print "channel=%(channel)s" --print "title=%(title)s" \
    "https://www.youtube.com/watch?v=QBznUHAopxU"
channel=The Knowledge Project Podcast
title=Marketing Expert: The Playbook Behind Every Great Campaign | Rory Sutherland
```

Ground truth: it is **The Knowledge Project** (host Shane Parrish), not
Diary of a CEO. The label was wrong and had already been wired into config;
the deterministic check caught it where the two agents had disagreed. Fix:
correct the comment, remove the wrongly-attributed host from the derived
list, and re-run the gate/tests.

## Notes

- A deterministic primary-source query beats a research agent for IDENTITY
  questions ("which show / who published this / what version"). Agents are
  still useful for things the metadata does NOT capture (e.g. "is a fourth
  person audible in the background" needs show notes / transcripts).
- Distinguish the resource's *own* metadata from third-party descriptions.
  The YouTube channel/uploader fields are first-party; a blog claiming
  "this video is from podcast X" is not.
- Titles are reused across shows and re-uploads. Match on the publisher
  (channel/uploader/registry owner), not just the title string.
- Batch the check across all referenced IDs when one is found wrong; a
  mislabel often indicates copy-paste from a sibling entry, so siblings are
  suspect too.

## References

- yt-dlp output template / `--print` fields:
  https://github.com/yt-dlp/yt-dlp#output-template
