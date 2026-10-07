---
name: gh-code-search-zero-results-clone-and-grep
description: |
  GitHub code search via `gh api search/code` or `gh search code` silently returns
  total_count 0 for the user's own repos (private AND small public ones) even when the
  searched string is known to exist in the default branch. Do not read 0 as "no matches".
  Use when: (1) auditing which of the user's GitHub repos reference a dependency, host,
  or secret name (mongoose, herokuapp, MONGODB_URL), (2) a code search returns 0 for a
  string you can see in a local clone, (3) you need to know where a deployed Vite/React
  SPA's backend is hosted and the repo only has a VITE_* env var. Fix: shallow-clone the
  repos into the scratchpad and grep; for the SPA backend host, grep the live bundle.
author: Claude Code
version: 1.0.0
date: 2026-09-02
---

# GitHub code search returns 0 for your own repos: clone and grep instead

## Problem
GitHub's REST code search (the legacy `search/code` endpoint that both `gh api search/code`
and `gh search code` use) only returns hits from repos GitHub has indexed. The user's repos
were not indexed, so every query came back `total_count: 0` with no error, which looks
exactly like a genuine "no matches". Trusting it would have produced a wrong answer to
"which of my apps use Heroku".

## Context / Trigger Conditions
- `gh api -X GET search/code -f q='needle user:<owner>' --jq .total_count` prints `0`
- `gh search code needle --repo <owner>/<repo> --json path --jq length` prints `0`
- The same string is visible in a local clone or via `gh api repos/<owner>/<repo>/contents/<file>`
- Verified 02/09/2026: `heroku-postbuild repo:michaldobiezynski/AdvanceNode` returned 0
  although `AdvanceNode/package.json` contains it; two small public repos also returned 0
  for `import`.

## Solution
1. **Enumerate candidate repos** with the repo list API, which does work:
   ```bash
   gh repo list <owner> --limit 200 --json name,url,isPrivate,pushedAt
   ```
2. **Cheap first pass without cloning**: list root files and read `package.json` per repo.
   ```bash
   gh api repos/<owner>/<repo>/contents/ --jq '.[].name'
   gh api repos/<owner>/<repo>/contents/package.json --jq .content | base64 -d | grep -iE 'mongo|heroku'
   ```
3. **Definitive pass**: shallow-clone into the scratchpad (never into the user's project
   folder unless asked) and grep, excluding lockfiles and vendored READMEs.
   ```bash
   S=<scratchpad>/repos; mkdir -p $S; cd $S
   for r in repoA repoB; do [ -d $r ] || gh repo clone <owner>/$r $r -- --depth 1 --quiet; done
   grep -rIn -i -E 'herokuapp|heroku' . --exclude-dir=node_modules --exclude-dir=.git \
     | grep -v -E 'package-lock|yarn.lock|client/README|CHANGELOG'
   ```
4. **Where is a deployed SPA's backend?** If the repo only has `import.meta.env.VITE_API_BASE_URL`,
   the value is inlined at build time, so read it from the live bundle:
   ```bash
   curl -sL https://<site>/ -o page.html
   js=$(grep -o 'src="[^"]*\.js"' page.html | head -1 | sed 's/src="//;s/"$//')
   curl -sL "https://<site>$js" | grep -o -E 'https?://[A-Za-z0-9._-]+\.[a-z]{2,}[^"'"'"' ]*' | sort -u
   ```
   Then `curl -s -o /dev/null -w '%{http_code}' <host>/<route>` tells you if it is still live.

## Verification
Step 3's grep prints file:line hits for strings that code search claimed did not exist.
On 02/09/2026 it found `chessAlly/src/api/tracker.js` pointing at a `herokuapp.com` host
and `chessAllyQueueRunner/package.json` depending on mongoose, both invisible to search.

## Notes
- The endpoint also only searches the default branch and files under 384 KB, and is rate
  limited to 10 requests per minute, so even when indexed it is a weak audit tool.
- Committed `.env` files surface during step 3. Report variable names only, never values,
  and flag them for rotation.
- Related: `ugrep-bounded-repeat-exceeds-complexity-limits` (grep on this Mac is ugrep).

## References
- [GitHub Docs: REST API endpoints for search](https://docs.github.com/en/rest/search/search?apiVersion=2026-03-10)
- [GitHub Changelog: Changes to the code search API (2023)](https://github.blog/changelog/2023-03-10-changes-to-the-code-search-api/)
- [Community: Code Search not returning results from some repositories](https://github.com/orgs/community/discussions/18624)
- [Community: search/code REST API not working for organization private repos](https://github.com/orgs/community/discussions/113651)
