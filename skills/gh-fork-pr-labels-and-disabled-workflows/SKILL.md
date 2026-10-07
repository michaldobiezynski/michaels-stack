---
name: gh-fork-pr-labels-and-disabled-workflows
description: |
  Open a PR on your own fork when the upstream repo is read-only, and get its
  CI and label checks working. Use when: (1) `gh repo view --json viewerPermission`
  says READ on the target repo, (2) `gh pr create --label X` fails because the
  fork has no such label, (3) `gh workflow enable ci.yml --repo <fork>` or
  `gh workflow run` returns "HTTP 404: workflow ci.yml not found on the default
  branch" and `gh workflow list --all` on the fork is empty, (4) a PR on a fresh
  fork shows no CI runs. Covers the fork remote, copying release labels from
  upstream, and the one-time browser step GitHub requires before any workflow runs.
author: Claude Code
version: 1.0.0
date: 2026-09-03
---

# Fork PRs: missing labels and workflows that 404

## Problem

A fresh fork has none of the upstream's custom labels, and GitHub keeps every
workflow in a fork disabled until the owner enables them in the Actions tab.
The `gh` CLI reports the second problem as a misleading 404 ("workflow not
found on the default branch") even though the file exists on the fork's main.

## Context / Trigger Conditions

- `gh repo view OWNER/REPO --json viewerPermission` prints `"READ"`.
- Upstream's PR check requires exactly one of several labels (e.g. major/minor/patch/no-release).
- `gh workflow list --repo <fork> --all` prints nothing; enable/run give HTTP 404.

## Solution

1. Fork without cloning and add it as a second remote:
   `gh repo fork OWNER/REPO --clone=false && git remote add fork https://github.com/ME/REPO.git`
   Branch from `origin/main`, push with `git push -u fork <branch>`.
2. Copy the labels the PR check needs, before `gh pr create`:
   ```bash
   gh label list --repo OWNER/REPO --json name,color,description \
     --jq '.[] | select(.name=="major" or .name=="minor" or .name=="patch" or .name=="no-release") | "\(.name)\t\(.color)\t\(.description)"' \
   | while IFS=$'\t' read -r n c d; do gh label create "$n" --repo ME/REPO --color "$c" --description "$d" --force; done
   ```
3. Open the PR against the fork's own main:
   `gh pr create --repo ME/REPO --base main --head <branch> --draft --label minor --body-file body.md`
   (a PR against upstream would be visible to its maintainer; keep it on the fork until the user decides).
4. CI: the user must open `https://github.com/ME/REPO/actions` once and click
   "Enable workflows". There is no API/CLI equivalent; until then treat CI as
   not run and say so in the PR body. After enabling, `gh workflow run ci.yml
   --repo ME/REPO --ref <branch>` works if the workflow has `workflow_dispatch`.
5. `gh` with two remotes resolves PR numbers ambiguously: always pass `--repo`.

## Verification

- `gh label list --repo ME/REPO` shows the copied labels; `gh pr create` succeeds with `--label`.
- After the browser step, `gh workflow list --repo ME/REPO` lists the workflows and runs appear under the PR.

## Notes

- A fork's CI build lacks upstream signing secrets, so a macOS app built there is
  ad-hoc signed and macOS drops TCC grants (Accessibility) on each new build.
