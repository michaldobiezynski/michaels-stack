---
name: vercel-mcp-deploy-is-cli-redirect
description: |
  Heads-up that the Vercel MCP tool `mcp__claude_ai_Vercel__deploy_to_vercel`
  is a stub that does NOT actually deploy — it returns a text message
  instructing you to run `vercel deploy` from the CLI. Use when: (1) you
  have the Vercel MCP integration installed and are about to deploy a
  project from Claude Code, (2) you see a confusingly-named MCP tool and
  want to know which one actually triggers a deploy, (3) `deploy_to_vercel`
  returns text like "To deploy this to Vercel, run the Vercel CLI command
  `vercel deploy`" instead of starting a deployment. Also covers the
  companion CLI workflow: `vercel deploy --prod --yes` from the project
  directory, and `vercel git connect` (no args) to link an existing GitHub
  origin to the Vercel project after `gh repo create --source=. --push`.
author: Claude Code
version: 1.0.0
date: 2026-05-18
---

# Vercel MCP `deploy_to_vercel` is a CLI redirect, not a deploy trigger

## Problem
The Vercel MCP integration exposes a tool named
`mcp__claude_ai_Vercel__deploy_to_vercel`. The name implies "call this and
it deploys." It does not. It returns a one-paragraph text message telling
you to use the CLI. An agent that calls it expecting a deployment will not
get one, and unless it reads the response carefully it may believe the
deploy succeeded.

## Context / Trigger Conditions

- Claude Code session with the Vercel MCP installed (tools prefixed with
  `mcp__claude_ai_Vercel__`).
- You call `mcp__claude_ai_Vercel__deploy_to_vercel` with no parameters
  (the schema accepts none).
- The tool returns text similar to:

  > To deploy this to Vercel, run the Vercel CLI command `vercel deploy`.
  > This may be run from project root which can be identified by having a
  > .vercel directory. Alternatively, if the user has the Vercel git
  > integration enabled, they may commit and push to their git origin to
  > trigger a deployment.

  No deployment has been initiated.

## Solution

Use the Vercel CLI from a Bash tool call instead. The MCP tool is purely
advisory.

### Cold first deploy (no `.vercel` directory yet)

```bash
cd /absolute/path/to/project
vercel deploy --prod --yes
```

`--yes` accepts the default scope, project name (= directory name), and
framework preset. Vite, Next, SvelteKit, Astro, etc. are auto-detected
from `package.json`. On first run this creates `.vercel/project.json`
(gitignore it) and links the local dir to a Vercel project.

If the cached token has expired, `vercel whoami` returns
"The specified token is not valid. Use `vercel login` to generate a new
token." This is interactive — the agent cannot recover automatically.
Ask the user to run `! vercel login` in the prompt (the leading `!`
streams the interactive output into the conversation).

### Wiring the Vercel project to a fresh GitHub repo

After the first `vercel deploy` has created `.vercel/project.json`, you
can hand future deploys off to GitHub:

```bash
cd /absolute/path/to/project
gh repo create <name> --public --source=. --remote=origin \
  --description "..." --push
vercel git connect   # no args — auto-detects origin from cwd
```

`vercel git connect` with no arguments reads the `origin` remote of the
git repo in the current working directory and links it to the already-
linked Vercel project. After this, every push to the production branch
auto-deploys.

## Verification

- The MCP call response is plain text, not a deployment record. If you
  expected a `dpl_…` ID, status `READY`, or a `*.vercel.app` URL and got
  prose instead, that is the symptom.
- After `vercel deploy --prod --yes`, the final JSON block in stdout
  contains `"status": "ok"`, `"readyState": "READY"`, and a
  `"deployment": { "url": "...", "id": "dpl_..." }` object — that is
  what a real deploy looks like.
- After `vercel git connect`, the CLI prints
  `> Connected` and future pushes show up under
  `vercel.com/<scope>/<project>` deployments.

## Example

From a Claude Code session where the agent had just built a Vite project:

```
1. Agent calls mcp__claude_ai_Vercel__deploy_to_vercel
   → Returns "run `vercel deploy`" text. No deploy yet.

2. Agent runs Bash: vercel whoami
   → Token expired. Asks user to run `! vercel login`.

3. After user logs in, Agent runs:
   cd /path/to/site && vercel deploy --prod --yes
   → Real deploy. URL aliased to https://site.vercel.app.

4. Agent runs: gh repo create site --public --source=. --push
   → Repo on GitHub.

5. Agent runs: cd /path/to/site && vercel git connect
   → "Connected". Auto-deploy on push wired up.
```

## Notes

- Other `mcp__claude_ai_Vercel__*` tools (e.g. `list_projects`,
  `get_deployment`, `list_deployments`, `get_deployment_build_logs`) are
  real read-only tools and behave as their schemas suggest. Only
  `deploy_to_vercel` is a redirect-to-CLI stub.
- The MCP tool reportedly does redirect for a reason: deploys need a
  scope/team selection plus uploads of the working directory, neither of
  which fits cleanly into a one-shot MCP call. Don't fight it; reach for
  the CLI immediately.
- `shell cwd` resets between Bash calls in Claude Code, so use absolute
  paths or `cd /path && cmd` rather than relying on a sticky working
  directory.
- `.vercel/` should be in `.gitignore`. Vercel CLI creates it on first
  deploy and uses it to remember the project link.

## References

- Vercel CLI docs: https://vercel.com/docs/cli/deploy
- `vercel git connect`: https://vercel.com/docs/cli/git
- gh repo create:
  https://cli.github.com/manual/gh_repo_create
